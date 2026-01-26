#!/usr/bin/env python3
"""
Moneyness Cache Refresh Service

Session 5B: Manages moneyness cache refresh logic with registry event triggers
and intelligent invalidation based on spot price movements and option chain changes.
"""

import asyncio
import logging
import time
import json
import math
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .enhanced_cache_invalidation_service import (
    InvalidationRequest,
    InvalidationType,
    get_enhanced_cache_service
)

logger = logging.getLogger(__name__)

class MoneynessCategory(Enum):
    DEEP_OTM = "deep_otm"      # < 0.8 or > 1.2
    OTM = "otm"                # 0.8-0.95 or 1.05-1.2
    ATM = "atm"                # 0.95-1.05
    ITM = "itm"                # Same as OTM but inverted
    DEEP_ITM = "deep_itm"      # Same as DEEP_OTM but inverted

class RefreshTrigger(Enum):
    SPOT_PRICE_CHANGE = "spot_price_change"
    CHAIN_REBALANCE = "chain_rebalance"
    EXPIRY_APPROACHING = "expiry_approaching"
    VOLATILITY_SPIKE = "volatility_spike"
    SCHEDULED_REFRESH = "scheduled_refresh"

@dataclass
class MoneynessRefreshContext:
    """Context for moneyness cache refresh operations"""
    underlying: str
    trigger: RefreshTrigger
    spot_price: float
    spot_price_change_pct: Optional[float] = None
    affected_strikes: Set[float] = None
    affected_expiries: Set[str] = None
    refresh_priority: str = "normal"  # high, normal, low
    full_chain_refresh: bool = False
    timestamp: datetime = None

@dataclass
class MoneynessCalculationResult:
    """Result of moneyness calculation"""
    strike_price: float
    spot_price: float
    moneyness: float
    category: MoneynessCategory
    time_to_expiry: float
    intrinsic_value: float
    time_value: float
    option_type: str  # call or put
    
class MoneynessClassifier:
    """Classifies options by moneyness levels"""
    
    @staticmethod
    def classify_moneyness(moneyness: float) -> MoneynessCategory:
        """Classify moneyness into categories"""
        if moneyness < 0.8:
            return MoneynessCategory.DEEP_OTM
        elif moneyness < 0.95:
            return MoneynessCategory.OTM
        elif moneyness <= 1.05:
            return MoneynessCategory.ATM
        elif moneyness <= 1.2:
            return MoneynessCategory.ITM
        else:
            return MoneynessCategory.DEEP_ITM
    
    @staticmethod
    def calculate_moneyness(spot_price: float, strike_price: float) -> float:
        """Calculate moneyness ratio"""
        if strike_price <= 0:
            return 0.0
        return spot_price / strike_price
    
    @staticmethod
    def calculate_intrinsic_value(spot_price: float, strike_price: float, option_type: str) -> float:
        """Calculate intrinsic value"""
        if option_type.lower() == "call":
            return max(0, spot_price - strike_price)
        else:  # put
            return max(0, strike_price - spot_price)

class MoneynessCalculationEngine:
    """Engine for moneyness calculations"""
    
    def __init__(self):
        self.classifier = MoneynessClassifier()
    
    async def calculate_option_moneyness(self, spot_price: float, strike_price: float, 
                                       time_to_expiry: float, option_type: str,
                                       premium: Optional[float] = None) -> MoneynessCalculationResult:
        """Calculate comprehensive moneyness data for an option"""
        
        # Basic moneyness calculation
        moneyness = self.classifier.calculate_moneyness(spot_price, strike_price)
        category = self.classifier.classify_moneyness(moneyness)
        
        # Intrinsic value calculation
        intrinsic_value = self.classifier.calculate_intrinsic_value(spot_price, strike_price, option_type)
        
        # Time value calculation (if premium is available)
        time_value = 0.0
        if premium is not None:
            time_value = max(0, premium - intrinsic_value)
        
        return MoneynessCalculationResult(
            strike_price=strike_price,
            spot_price=spot_price,
            moneyness=moneyness,
            category=category,
            time_to_expiry=time_to_expiry,
            intrinsic_value=intrinsic_value,
            time_value=time_value,
            option_type=option_type.lower()
        )
    
    async def calculate_chain_moneyness(self, spot_price: float, chain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate moneyness for entire option chain"""
        
        results = {}
        
        for strike_str, option_data in chain_data.items():
            try:
                strike_price = float(strike_str)
                option_type = option_data.get("option_type", "call")
                time_to_expiry = float(option_data.get("time_to_expiry", 0))
                premium = option_data.get("premium")
                
                moneyness_result = await self.calculate_option_moneyness(
                    spot_price, strike_price, time_to_expiry, option_type, premium
                )
                
                results[strike_str] = {
                    "moneyness": moneyness_result.moneyness,
                    "category": moneyness_result.category.value,
                    "intrinsic_value": moneyness_result.intrinsic_value,
                    "time_value": moneyness_result.time_value,
                    "strike_price": strike_price,
                    "spot_price": spot_price,
                    "option_type": option_type,
                    "calculation_timestamp": datetime.now().isoformat()
                }
                
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to calculate moneyness for strike {strike_str}: {e}")
                continue
        
        return results

class MoneynessCache:
    """Manages moneyness cache storage and retrieval"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        
        # Cache TTL configuration
        self.cache_ttls = {
            "live_moneyness": 60,          # 1 minute for live calculations
            "chain_moneyness": 300,        # 5 minutes for chain-wide data
            "historical_moneyness": 3600,  # 1 hour for historical data
            "category_lookup": 1800        # 30 minutes for category mappings
        }
    
    async def store_moneyness_result(self, underlying: str, strike_price: float, 
                                   result: MoneynessCalculationResult, cache_type: str = "live"):
        """Store moneyness calculation result in cache"""
        
        try:
            cache_data = {
                "underlying": underlying,
                "strike_price": strike_price,
                "spot_price": result.spot_price,
                "moneyness": result.moneyness,
                "category": result.category.value,
                "intrinsic_value": result.intrinsic_value,
                "time_value": result.time_value,
                "option_type": result.option_type,
                "time_to_expiry": result.time_to_expiry,
                "cached_at": datetime.now().isoformat()
            }
            
            # Multiple cache keys for different access patterns
            cache_keys = [
                f"moneyness:{underlying}:{strike_price}:latest",
                f"moneyness:{underlying}:{strike_price}:{cache_type}",
                f"moneyness:{underlying}:{result.category.value}:{strike_price}",
                f"moneyness_lookup:{underlying}:{strike_price}"
            ]
            
            ttl = self.cache_ttls.get(f"{cache_type}_moneyness", self.cache_ttls["live_moneyness"])
            
            # Store in all cache locations
            for cache_key in cache_keys:
                await self.redis_client.setex(cache_key, ttl, json.dumps(cache_data))
            
            logger.debug(f"Stored moneyness result for {underlying}:{strike_price} with TTL {ttl}s")
            
        except Exception as e:
            logger.error(f"Failed to store moneyness result for {underlying}:{strike_price}: {e}")
    
    async def store_chain_moneyness(self, underlying: str, chain_results: Dict[str, Any], 
                                  expiry_date: str = "latest"):
        """Store moneyness results for entire option chain"""
        
        try:
            chain_summary = {
                "underlying": underlying,
                "expiry_date": expiry_date,
                "total_strikes": len(chain_results),
                "moneyness_distribution": self._calculate_moneyness_distribution(chain_results),
                "cached_at": datetime.now().isoformat()
            }
            
            # Store individual strike results
            for strike_str, moneyness_data in chain_results.items():
                strike_key = f"moneyness:{underlying}:{expiry_date}:{strike_str}"
                await self.redis_client.setex(
                    strike_key, 
                    self.cache_ttls["chain_moneyness"], 
                    json.dumps(moneyness_data)
                )
            
            # Store chain summary
            summary_key = f"moneyness_summary:{underlying}:{expiry_date}"
            await self.redis_client.setex(
                summary_key, 
                self.cache_ttls["chain_moneyness"], 
                json.dumps(chain_summary)
            )
            
            # Store category-based lookups
            await self._store_category_lookups(underlying, expiry_date, chain_results)
            
            logger.info(f"Stored moneyness data for {len(chain_results)} strikes in {underlying} chain")
            
        except Exception as e:
            logger.error(f"Failed to store chain moneyness for {underlying}: {e}")
    
    def _calculate_moneyness_distribution(self, chain_results: Dict[str, Any]) -> Dict[str, int]:
        """Calculate distribution of options by moneyness category"""
        
        distribution = {category.value: 0 for category in MoneynessCategory}
        
        for moneyness_data in chain_results.values():
            category = moneyness_data.get("category", "unknown")
            if category in distribution:
                distribution[category] += 1
        
        return distribution
    
    async def _store_category_lookups(self, underlying: str, expiry_date: str, chain_results: Dict[str, Any]):
        """Store category-based lookup indexes"""
        
        category_lookups = {}
        
        for strike_str, moneyness_data in chain_results.items():
            category = moneyness_data.get("category", "unknown")
            if category not in category_lookups:
                category_lookups[category] = []
            
            category_lookups[category].append({
                "strike": float(strike_str),
                "moneyness": moneyness_data.get("moneyness"),
                "intrinsic_value": moneyness_data.get("intrinsic_value")
            })
        
        # Store category lookups
        for category, strikes in category_lookups.items():
            lookup_key = f"moneyness_category:{underlying}:{expiry_date}:{category}"
            await self.redis_client.setex(
                lookup_key, 
                self.cache_ttls["category_lookup"], 
                json.dumps(strikes)
            )
    
    async def get_moneyness_result(self, underlying: str, strike_price: float) -> Optional[Dict[str, Any]]:
        """Retrieve moneyness result from cache"""
        
        try:
            cache_key = f"moneyness:{underlying}:{strike_price}:latest"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get moneyness result for {underlying}:{strike_price}: {e}")
            return None

class MoneynessRefreshService:
    """Main service for moneyness cache refresh operations"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.calculation_engine = MoneynessCalculationEngine()
        self.cache = MoneynessCache(redis_client)
        self.cache_service = get_enhanced_cache_service(redis_client)
        
        # Refresh configuration
        self.refresh_thresholds = {
            "spot_price_change_pct": 0.5,    # 0.5% spot price change
            "moneyness_change": 0.02,         # 2% moneyness change threshold
            "atm_sensitivity": 0.25,          # ATM options are 25% more sensitive
            "time_decay_hours": 24,           # Daily refresh for expiry approaching
            "volatility_spike_pct": 10.0      # 10% volatility spike
        }
        
        # Performance tracking
        self.performance_metrics = {
            "total_refreshes": 0,
            "strikes_calculated": 0,
            "cache_invalidations": 0,
            "full_chain_refreshes": 0,
            "selective_refreshes": 0,
            "avg_refresh_time_ms": 0.0
        }
    
    async def handle_spot_price_update(self, underlying: str, new_spot_price: float, 
                                     previous_spot_price: Optional[float] = None) -> Dict[str, Any]:
        """Handle spot price update with intelligent moneyness cache refresh"""
        
        logger.info(f"Handling spot price update for {underlying}: {new_spot_price}")
        
        start_time = time.time()
        result = {
            "underlying": underlying,
            "new_spot_price": new_spot_price,
            "refresh_type": "none",
            "strikes_refreshed": 0,
            "refresh_success": False,
            "performance": {}
        }
        
        try:
            # Calculate price change if previous price is available
            price_change_pct = 0.0
            if previous_spot_price and previous_spot_price > 0:
                price_change_pct = abs(new_spot_price - previous_spot_price) / previous_spot_price * 100
            
            # Create refresh context
            refresh_context = MoneynessRefreshContext(
                underlying=underlying,
                trigger=RefreshTrigger.SPOT_PRICE_CHANGE,
                spot_price=new_spot_price,
                spot_price_change_pct=price_change_pct,
                timestamp=datetime.now()
            )
            
            # Determine refresh strategy based on price change magnitude
            if price_change_pct > self.refresh_thresholds["spot_price_change_pct"]:
                if price_change_pct > 2.0:  # Large price change
                    refresh_context.full_chain_refresh = True
                    refresh_context.refresh_priority = "high"
                    result["refresh_type"] = "full_chain"
                else:  # Moderate price change
                    refresh_context.affected_strikes = await self._identify_affected_strikes(
                        underlying, new_spot_price, price_change_pct
                    )
                    refresh_context.refresh_priority = "normal"
                    result["refresh_type"] = "selective"
                
                # Perform the refresh
                refresh_result = await self._execute_moneyness_refresh(refresh_context)
                result.update(refresh_result)
                result["refresh_success"] = refresh_result.get("success", False)
                result["strikes_refreshed"] = refresh_result.get("strikes_calculated", 0)
                
                self.performance_metrics["total_refreshes"] += 1
                if refresh_context.full_chain_refresh:
                    self.performance_metrics["full_chain_refreshes"] += 1
                else:
                    self.performance_metrics["selective_refreshes"] += 1
            else:
                logger.debug(f"Price change {price_change_pct:.2f}% below threshold, no refresh needed")
                result["refresh_type"] = "threshold_not_met"
            
            # Record performance metrics
            refresh_time = (time.time() - start_time) * 1000
            result["performance"] = {
                "refresh_time_ms": refresh_time,
                "price_change_pct": price_change_pct,
                "threshold_met": price_change_pct > self.refresh_thresholds["spot_price_change_pct"]
            }
            
            # Update average refresh time
            current_avg = self.performance_metrics["avg_refresh_time_ms"]
            total_refreshes = max(1, self.performance_metrics["total_refreshes"])
            self.performance_metrics["avg_refresh_time_ms"] = (
                (current_avg * (total_refreshes - 1) + refresh_time) / total_refreshes
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Spot price update handling failed for {underlying}: {e}")
            result["error"] = str(e)
            result["performance"]["refresh_time_ms"] = (time.time() - start_time) * 1000
            return result
    
    async def handle_chain_rebalance_refresh(self, underlying: str, rebalance_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle option chain rebalance with full moneyness refresh"""
        
        logger.info(f"Handling chain rebalance refresh for {underlying}")
        
        start_time = time.time()
        result = {
            "underlying": underlying,
            "refresh_type": "chain_rebalance",
            "strikes_refreshed": 0,
            "expiries_refreshed": 0,
            "refresh_success": False
        }
        
        try:
            # Get current spot price
            spot_price = await self._get_current_spot_price(underlying)
            if not spot_price:
                raise ValueError(f"No spot price available for {underlying}")
            
            # Create refresh context for chain rebalance
            refresh_context = MoneynessRefreshContext(
                underlying=underlying,
                trigger=RefreshTrigger.CHAIN_REBALANCE,
                spot_price=spot_price,
                full_chain_refresh=True,
                refresh_priority="high",
                affected_expiries=set(rebalance_data.get("affected_expiries", [])),
                timestamp=datetime.now()
            )
            
            # Get affected expiries or refresh all
            expiry_dates = list(refresh_context.affected_expiries) if refresh_context.affected_expiries else ["latest"]
            
            total_strikes_refreshed = 0
            for expiry_date in expiry_dates:
                # Execute moneyness refresh for this expiry
                expiry_refresh_result = await self._execute_expiry_moneyness_refresh(
                    refresh_context, expiry_date
                )
                
                if expiry_refresh_result.get("success"):
                    total_strikes_refreshed += expiry_refresh_result.get("strikes_calculated", 0)
            
            result["strikes_refreshed"] = total_strikes_refreshed
            result["expiries_refreshed"] = len(expiry_dates)
            result["refresh_success"] = total_strikes_refreshed > 0
            
            # Update performance metrics
            self.performance_metrics["total_refreshes"] += 1
            self.performance_metrics["full_chain_refreshes"] += 1
            self.performance_metrics["strikes_calculated"] += total_strikes_refreshed
            
            result["performance"] = {
                "refresh_time_ms": (time.time() - start_time) * 1000,
                "strikes_per_second": total_strikes_refreshed / max(1, (time.time() - start_time))
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Chain rebalance refresh failed for {underlying}: {e}")
            result["error"] = str(e)
            result["performance"] = {"refresh_time_ms": (time.time() - start_time) * 1000}
            return result
    
    async def _execute_moneyness_refresh(self, context: MoneynessRefreshContext) -> Dict[str, Any]:
        """Execute moneyness cache refresh based on context"""
        
        result = {
            "success": False,
            "strikes_calculated": 0,
            "cache_invalidations": 0,
            "refresh_strategy": "unknown"
        }
        
        try:
            if context.full_chain_refresh:
                # Full chain refresh
                result["refresh_strategy"] = "full_chain"
                chain_refresh_result = await self._refresh_full_chain(context.underlying, context.spot_price)
                result.update(chain_refresh_result)
                
            elif context.affected_strikes:
                # Selective strike refresh
                result["refresh_strategy"] = "selective_strikes"
                selective_result = await self._refresh_selective_strikes(
                    context.underlying, context.spot_price, context.affected_strikes
                )
                result.update(selective_result)
                
            else:
                # Default to ATM strikes refresh
                result["refresh_strategy"] = "atm_focused"
                atm_result = await self._refresh_atm_strikes(context.underlying, context.spot_price)
                result.update(atm_result)
            
            return result
            
        except Exception as e:
            logger.error(f"Moneyness refresh execution failed: {e}")
            result["error"] = str(e)
            return result
    
    async def _refresh_full_chain(self, underlying: str, spot_price: float) -> Dict[str, Any]:
        """Refresh moneyness for entire option chain"""
        
        start_time = time.time()
        result = {"success": False, "strikes_calculated": 0}
        
        try:
            # Get current chain data
            chain_data = await self._get_chain_data(underlying)
            if not chain_data:
                raise ValueError(f"No chain data available for {underlying}")
            
            # Calculate moneyness for entire chain
            chain_moneyness = await self.calculation_engine.calculate_chain_moneyness(spot_price, chain_data)
            
            if chain_moneyness:
                # Store results in cache
                await self.cache.store_chain_moneyness(underlying, chain_moneyness)
                
                result["success"] = True
                result["strikes_calculated"] = len(chain_moneyness)
                result["calculation_time_ms"] = (time.time() - start_time) * 1000
                
                logger.info(f"Refreshed moneyness for {len(chain_moneyness)} strikes in {underlying} chain")
            
            return result
            
        except Exception as e:
            logger.error(f"Full chain refresh failed for {underlying}: {e}")
            result["error"] = str(e)
            return result
    
    async def _refresh_selective_strikes(self, underlying: str, spot_price: float, 
                                       affected_strikes: Set[float]) -> Dict[str, Any]:
        """Refresh moneyness for selective strikes"""
        
        result = {"success": False, "strikes_calculated": 0}
        
        try:
            # Get option data for affected strikes
            chain_data = await self._get_chain_data(underlying)
            if not chain_data:
                raise ValueError(f"No chain data available for {underlying}")
            
            strikes_calculated = 0
            for strike_price in affected_strikes:
                strike_str = str(strike_price)
                if strike_str in chain_data:
                    option_data = chain_data[strike_str]
                    
                    # Calculate moneyness for this strike
                    moneyness_result = await self.calculation_engine.calculate_option_moneyness(
                        spot_price=spot_price,
                        strike_price=strike_price,
                        time_to_expiry=float(option_data.get("time_to_expiry", 0)),
                        option_type=option_data.get("option_type", "call"),
                        premium=option_data.get("premium")
                    )
                    
                    # Store in cache
                    await self.cache.store_moneyness_result(underlying, strike_price, moneyness_result)
                    strikes_calculated += 1
            
            result["success"] = strikes_calculated > 0
            result["strikes_calculated"] = strikes_calculated
            
            logger.info(f"Selectively refreshed {strikes_calculated} strikes for {underlying}")
            return result
            
        except Exception as e:
            logger.error(f"Selective strikes refresh failed for {underlying}: {e}")
            result["error"] = str(e)
            return result
    
    async def _refresh_atm_strikes(self, underlying: str, spot_price: float) -> Dict[str, Any]:
        """Refresh moneyness for ATM and near-ATM strikes"""
        
        result = {"success": False, "strikes_calculated": 0}
        
        try:
            # Get ATM-focused strikes (within 5% of spot price)
            atm_strikes = await self._get_atm_strikes(underlying, spot_price, tolerance_pct=5.0)
            
            if atm_strikes:
                atm_result = await self._refresh_selective_strikes(underlying, spot_price, atm_strikes)
                result.update(atm_result)
            else:
                logger.warning(f"No ATM strikes found for {underlying}")
            
            return result
            
        except Exception as e:
            logger.error(f"ATM strikes refresh failed for {underlying}: {e}")
            result["error"] = str(e)
            return result
    
    async def _identify_affected_strikes(self, underlying: str, new_spot_price: float, 
                                       price_change_pct: float) -> Set[float]:
        """Identify strikes affected by spot price change"""
        
        affected_strikes = set()
        
        try:
            # Get current chain data
            chain_data = await self._get_chain_data(underlying)
            if not chain_data:
                return affected_strikes
            
            # Calculate range of affected strikes based on price change
            price_tolerance = price_change_pct * 0.5  # Half the price change as tolerance
            lower_bound = new_spot_price * (1 - price_tolerance / 100)
            upper_bound = new_spot_price * (1 + price_tolerance / 100)
            
            for strike_str in chain_data.keys():
                try:
                    strike_price = float(strike_str)
                    
                    # Include strikes within tolerance range
                    if lower_bound <= strike_price <= upper_bound:
                        affected_strikes.add(strike_price)
                    
                    # Always include ATM strikes for high sensitivity
                    moneyness = new_spot_price / strike_price
                    if 0.95 <= moneyness <= 1.05:  # ATM range
                        affected_strikes.add(strike_price)
                        
                except ValueError:
                    continue
            
            logger.debug(f"Identified {len(affected_strikes)} affected strikes for {underlying}")
            return affected_strikes
            
        except Exception as e:
            logger.error(f"Failed to identify affected strikes for {underlying}: {e}")
            return affected_strikes
    
    async def _get_atm_strikes(self, underlying: str, spot_price: float, tolerance_pct: float = 5.0) -> Set[float]:
        """Get ATM and near-ATM strike prices"""
        
        atm_strikes = set()
        
        try:
            chain_data = await self._get_chain_data(underlying)
            if not chain_data:
                return atm_strikes
            
            tolerance = tolerance_pct / 100
            lower_bound = spot_price * (1 - tolerance)
            upper_bound = spot_price * (1 + tolerance)
            
            for strike_str in chain_data.keys():
                try:
                    strike_price = float(strike_str)
                    if lower_bound <= strike_price <= upper_bound:
                        atm_strikes.add(strike_price)
                except ValueError:
                    continue
            
            return atm_strikes
            
        except Exception as e:
            logger.error(f"Failed to get ATM strikes for {underlying}: {e}")
            return atm_strikes
    
    async def _execute_expiry_moneyness_refresh(self, context: MoneynessRefreshContext, expiry_date: str) -> Dict[str, Any]:
        """Execute moneyness refresh for specific expiry"""
        
        result = {"success": False, "strikes_calculated": 0}
        
        try:
            # Get chain data for specific expiry
            chain_key = f"raw_chain:{context.underlying}:{expiry_date}" if expiry_date != "latest" else f"raw_chain:{context.underlying}"
            chain_data_str = await self.redis_client.get(chain_key)
            
            if chain_data_str:
                chain_data = json.loads(chain_data_str)
                chain_moneyness = await self.calculation_engine.calculate_chain_moneyness(
                    context.spot_price, chain_data
                )
                
                if chain_moneyness:
                    await self.cache.store_chain_moneyness(context.underlying, chain_moneyness, expiry_date)
                    result["success"] = True
                    result["strikes_calculated"] = len(chain_moneyness)
            
            return result
            
        except Exception as e:
            logger.error(f"Expiry moneyness refresh failed for {context.underlying}:{expiry_date}: {e}")
            result["error"] = str(e)
            return result
    
    async def _get_chain_data(self, underlying: str) -> Optional[Dict[str, Any]]:
        """Get option chain data for calculations"""
        
        try:
            chain_key = f"raw_chain:{underlying}"
            chain_data_str = await self.redis_client.get(chain_key)
            
            if chain_data_str:
                return json.loads(chain_data_str)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chain data for {underlying}: {e}")
            return None
    
    async def _get_current_spot_price(self, underlying: str) -> Optional[float]:
        """Get current spot price for underlying"""
        
        try:
            spot_key = f"spot_price:{underlying}"
            spot_price_str = await self.redis_client.get(spot_key)
            
            if spot_price_str:
                return float(spot_price_str)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get spot price for {underlying}: {e}")
            return None
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get moneyness refresh performance metrics"""
        return self.performance_metrics.copy()

# Factory function
def create_moneyness_refresh_service(redis_client=None):
    """Create moneyness cache refresh service instance"""
    if redis_client is None:
        from ..utils.redis import get_redis_client
        redis_client = get_redis_client()
    
    return MoneynessRefreshService(redis_client)