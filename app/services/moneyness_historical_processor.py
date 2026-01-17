"""
Moneyness Historical Processor
Handles moneyness-based Greeks calculations with time series support
Makes moneyness transparent to the execution engine
"""
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import defaultdict

from app.utils.logging_utils import log_info, log_error, log_exception
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
from app.services.instrument_service_client import InstrumentServiceClient
from app.repositories.signal_repository import SignalRepository
from app.clients.historical_data_client import get_historical_data_client
from app.services.flexible_timeframe_manager import FlexibleTimeframeManager
# from app.models.signal_models import SignalGreeks, SignalIndicator


class MoneynessHistoricalProcessor:
    """
    Processes moneyness-based Greeks with historical support
    Provides seamless interface for execution engine
    """
    
    def __init__(
        self,
        moneyness_calculator: MoneynessAwareGreeksCalculator,
        repository: SignalRepository,
        instrument_client: Optional[InstrumentServiceClient] = None,
        timeframe_manager: Optional[FlexibleTimeframeManager] = None
    ):
        self.moneyness_calculator = moneyness_calculator
        self.repository = repository
        self.historical_client = get_historical_data_client()  # Unified historical data client
        self.instrument_client = instrument_client or InstrumentServiceClient()
        # Use FlexibleTimeframeManager to eliminate duplication
        self.timeframe_manager = timeframe_manager or FlexibleTimeframeManager()
        self._processing_cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def initialize(self):
        """Initialize the processor and timeframe manager"""
        if self.timeframe_manager and not hasattr(self.timeframe_manager, 'session'):
            await self.timeframe_manager.initialize()
        log_info("MoneynessHistoricalProcessor initialized with unified timeframe manager")
        
    async def get_moneyness_greeks_like_strike(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "5m"
    ) -> List[Dict[str, Any]]:
        """
        Get moneyness-based Greeks as if querying by strike
        Makes moneyness transparent to execution engine
        
        Args:
            underlying: Underlying symbol (e.g., "NIFTY")
            moneyness_level: Moneyness level (e.g., "ATM", "OTM5delta")
            expiry_date: Option expiry date
            start_time: Start of historical period
            end_time: End of historical period
            timeframe: Time interval
            
        Returns:
            Time series data formatted like strike-based Greeks
        """
        try:
            # Create a virtual instrument key for moneyness
            virtual_key = f"MONEYNESS@{underlying}@{moneyness_level}@{expiry_date}"
            
            # Check cache first
            cache_key = f"{virtual_key}:{timeframe}:{start_time}:{end_time}"
            if cache_key in self._processing_cache:
                cache_entry = self._processing_cache[cache_key]
                if datetime.utcnow() - cache_entry['timestamp'] < timedelta(seconds=self._cache_ttl):
                    log_info(f"Returning cached moneyness Greeks for {cache_key}")
                    return cache_entry['data']
                    
            # Process historical moneyness Greeks
            time_series = await self._process_historical_moneyness(
                underlying,
                moneyness_level,
                expiry_date,
                start_time,
                end_time,
                timeframe
            )
            
            # Format as strike-based response
            formatted_series = self._format_as_strike_response(
                time_series,
                underlying,
                moneyness_level,
                expiry_date
            )
            
            # Cache the result
            self._processing_cache[cache_key] = {
                'data': formatted_series,
                'timestamp': datetime.utcnow()
            }
            
            return formatted_series
            
        except Exception as e:
            log_exception(f"Error getting moneyness Greeks: {e}")
            return []
            
    async def _process_historical_moneyness(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> List[Dict[str, Any]]:
        """Process historical moneyness Greeks using FlexibleTimeframeManager - eliminates duplication"""
        
        # Create virtual instrument key for moneyness
        virtual_instrument_key = f"MONEYNESS@{underlying}@{moneyness_level}@{expiry_date}"
        
        # Delegate to FlexibleTimeframeManager to eliminate historical data retrieval duplication
        try:
            # Initialize timeframe manager if not already done
            if not hasattr(self.timeframe_manager, 'session') or not self.timeframe_manager.session:
                await self.timeframe_manager.initialize()
            
            # Use unified timeframe manager for all historical data retrieval
            aggregated_data = await self.timeframe_manager.get_aggregated_data(
                instrument_key=virtual_instrument_key,
                signal_type="moneyness_greeks",
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                fields=['delta', 'gamma', 'theta', 'vega', 'rho', 'iv']
            )
            
            return aggregated_data
            
        except Exception as e:
            log_error(f"Failed to get aggregated moneyness data through timeframe manager: {e}")
            
            # Fallback to manual processing only if timeframe manager fails
            base_data = await self._get_base_moneyness_data(
                underlying,
                moneyness_level,
                expiry_date,
                start_time,
                end_time
            )
            
            if not base_data:
                # No historical data - compute live
                return await self._compute_live_moneyness_series(
                    underlying,
                    moneyness_level,
                    expiry_date,
                    start_time,
                    end_time,
                    timeframe
                )
                
            # Manual aggregation as fallback (simplified to avoid duplication)
            return self._manual_aggregate(base_data, timeframe)
        
    async def _get_base_moneyness_data(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get base moneyness data from repository"""
        
        # Check if we have stored moneyness data
        stored_data = await self.repository.get_moneyness_history(
            underlying=underlying,
            moneyness_level=moneyness_level,
            expiry_date=expiry_date,
            start_time=start_time,
            end_time=end_time
        )
        
        if stored_data:
            return stored_data
            
        # Otherwise, reconstruct from individual option Greeks
        return await self._reconstruct_from_options(
            underlying,
            moneyness_level,
            expiry_date,
            start_time,
            end_time
        )
        
    async def _reconstruct_from_options(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Reconstruct moneyness Greeks from individual options"""
        
        # Get historical spot prices
        spot_prices = await self._get_historical_spot_prices(
            underlying,
            start_time,
            end_time
        )
        
        if not spot_prices:
            return []
            
        # For each timestamp, calculate moneyness Greeks
        results = []
        for spot_data in spot_prices:
            timestamp = spot_data['timestamp']
            spot_price = spot_data['price']
            
            # Get options at this moneyness level for this timestamp
            options = await self._get_historical_moneyness_options(
                underlying,
                spot_price,
                moneyness_level,
                expiry_date,
                timestamp
            )
            
            if options:
                # Calculate aggregated Greeks
                greeks = await self._calculate_historical_greeks(
                    options,
                    spot_price,
                    timestamp
                )
                
                results.append({
                    'timestamp': timestamp,
                    'spot_price': spot_price,
                    'moneyness_level': moneyness_level,
                    'greeks': greeks,
                    'options_count': len(options)
                })
                
        return results
        
    async def _compute_live_moneyness_series(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> List[Dict[str, Any]]:
        """Compute moneyness series live when no historical data exists"""
        
        # Generate timestamps based on timeframe
        timestamps = self._generate_timestamps(start_time, end_time, timeframe)
        
        results = []
        for timestamp in timestamps:
            # Get spot price at timestamp
            spot_price = await self._get_spot_at_timestamp(underlying, timestamp)
            
            if spot_price:
                # Calculate moneyness Greeks
                greeks = await self.moneyness_calculator.calculate_moneyness_greeks(
                    underlying_symbol=underlying,
                    spot_price=spot_price,
                    moneyness_level=moneyness_level,
                    expiry_date=expiry_date
                )
                
                results.append({
                    'timestamp': timestamp,
                    'value': greeks
                })
                
        return results
        
    def _format_as_strike_response(
        self,
        time_series: List[Dict[str, Any]],
        underlying: str,
        moneyness_level: str,
        expiry_date: str
    ) -> List[Dict[str, Any]]:
        """Format moneyness data to look like strike-based Greeks response"""
        
        formatted_series = []
        
        for point in time_series:
            # Extract Greeks from moneyness data
            if 'greeks' in point:
                greeks_data = point['greeks']
            elif 'value' in point and 'aggregated_greeks' in point['value']:
                greeks_data = point['value']['aggregated_greeks']['all']
            else:
                continue
                
            # Format as standard Greeks response
            formatted_point = {
                'timestamp': point['timestamp'],
                'instrument_key': f"MONEYNESS@{underlying}@{moneyness_level}@{expiry_date}",
                'value': {
                    'delta': greeks_data.get('delta', 0),
                    'gamma': greeks_data.get('gamma', 0),
                    'theta': greeks_data.get('theta', 0),
                    'vega': greeks_data.get('vega', 0),
                    'rho': greeks_data.get('rho', 0),
                    'iv': greeks_data.get('iv', 0),
                    'theoretical_value': greeks_data.get('theoretical_value', 0),
                    # Additional moneyness metadata
                    'moneyness_level': moneyness_level,
                    'options_aggregated': greeks_data.get('count', 0),
                    'calculation_method': 'moneyness_aggregation'
                }
            }
            
            # Add IV components if available
            if 'call_iv' in greeks_data:
                formatted_point['value']['call_iv'] = greeks_data['call_iv']
            if 'put_iv' in greeks_data:
                formatted_point['value']['put_iv'] = greeks_data['put_iv']
            if 'iv_skew' in greeks_data:
                formatted_point['value']['iv_skew'] = greeks_data['iv_skew']
                
            formatted_series.append(formatted_point)
            
        return formatted_series
        
    async def get_atm_iv_history(
        self,
        underlying: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "5m"
    ) -> Dict[str, Any]:
        """
        Get ATM IV history in standard format
        Special case of moneyness Greeks for ATM
        """
        # Get moneyness Greeks for ATM
        atm_greeks = await self.get_moneyness_greeks_like_strike(
            underlying=underlying,
            moneyness_level="ATM",
            expiry_date=expiry_date,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe
        )
        
        # Extract IV time series
        iv_series = []
        for point in atm_greeks:
            iv_series.append({
                'timestamp': point['timestamp'],
                'iv': point['value']['iv'],
                'call_iv': point['value'].get('call_iv'),
                'put_iv': point['value'].get('put_iv'),
                'iv_skew': point['value'].get('iv_skew'),
                'spot_price': point['value'].get('spot_price')
            })
            
        return {
            'underlying': underlying,
            'expiry_date': expiry_date,
            'moneyness': 'ATM',
            'timeframe': timeframe,
            'time_series': iv_series,
            'statistics': self._calculate_iv_statistics(iv_series)
        }
        
    def _calculate_iv_statistics(self, iv_series: List[Dict]) -> Dict[str, float]:
        """Calculate statistics for IV time series"""
        if not iv_series:
            return {}
            
        iv_values = [p['iv'] for p in iv_series if p.get('iv')]
        
        if not iv_values:
            return {}
            
        return {
            'mean': np.mean(iv_values),
            'std': np.std(iv_values),
            'min': np.min(iv_values),
            'max': np.max(iv_values),
            'current': iv_values[-1],
            'change': iv_values[-1] - iv_values[0] if len(iv_values) > 1 else 0,
            'change_pct': ((iv_values[-1] / iv_values[0]) - 1) * 100 if len(iv_values) > 1 and iv_values[0] != 0 else 0
        }
        
    async def get_moneyness_distribution_history(
        self,
        underlying: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "5m",
        moneyness_levels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get historical moneyness distribution across levels"""
        
        if not moneyness_levels:
            moneyness_levels = ["DITM", "ITM", "ATM", "OTM", "DOTM"]
            
        distribution_history = {}
        
        # Get data for each moneyness level
        tasks = []
        for level in moneyness_levels:
            task = self.get_moneyness_greeks_like_strike(
                underlying=underlying,
                moneyness_level=level,
                expiry_date=expiry_date,
                start_time=start_time,
                end_time=end_time,
                timeframe=timeframe
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for level, result in zip(moneyness_levels, results):
            if isinstance(result, Exception):
                log_error(f"Error getting {level} data: {result}")
                distribution_history[level] = []
            else:
                distribution_history[level] = result
                
        return {
            'underlying': underlying,
            'expiry_date': expiry_date,
            'timeframe': timeframe,
            'time_range': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            },
            'distribution': distribution_history,
            'analysis': self._analyze_distribution_changes(distribution_history)
        }
        
    def _analyze_distribution_changes(self, distribution: Dict[str, List]) -> Dict[str, Any]:
        """Analyze changes in moneyness distribution over time"""
        analysis = {
            'skew_evolution': [],
            'volatility_smile': [],
            'moneyness_shifts': {}
        }
        
        # Analyze how Greeks change across moneyness levels
        timestamps = set()
        for level_data in distribution.values():
            for point in level_data:
                timestamps.add(point['timestamp'])
                
        for timestamp in sorted(timestamps):
            # Get Greeks at this timestamp for all levels
            timestamp_greeks = {}
            for level, data in distribution.items():
                for point in data:
                    if point['timestamp'] == timestamp:
                        timestamp_greeks[level] = point['value']
                        break
                        
            # Calculate skew and smile metrics
            if len(timestamp_greeks) >= 3:
                analysis['skew_evolution'].append({
                    'timestamp': timestamp,
                    'metrics': self._calculate_skew_metrics(timestamp_greeks)
                })
                
        return analysis
        
    def _calculate_skew_metrics(self, greeks_by_level: Dict[str, Dict]) -> Dict[str, float]:
        """Calculate volatility skew metrics"""
        metrics = {}
        
        # Extract IVs
        ivs = {level: data.get('iv', 0) for level, data in greeks_by_level.items()}
        
        # Calculate skew
        if 'ATM' in ivs and 'OTM' in ivs:
            metrics['otm_skew'] = ivs['OTM'] - ivs['ATM']
            
        if 'ATM' in ivs and 'ITM' in ivs:
            metrics['itm_skew'] = ivs['ITM'] - ivs['ATM']
            
        if 'OTM' in ivs and 'ITM' in ivs:
            metrics['put_call_skew'] = ivs['OTM'] - ivs['ITM']
            
        # Risk reversal (25-delta)
        if 'OTM25delta' in ivs and 'ITM25delta' in ivs:
            metrics['risk_reversal_25d'] = ivs['OTM25delta'] - ivs['ITM25delta']
            
        return metrics
        
    def _manual_aggregate(self, base_data: List[Dict[str, Any]], timeframe: str) -> List[Dict[str, Any]]:
        """Manual aggregation fallback - simplified to avoid duplication with FlexibleTimeframeManager"""
        # Simple fallback that just passes through data - timeframe manager should handle aggregation
        log_info(f"Using simplified manual aggregation for {len(base_data)} data points")
        return base_data
        
    def _generate_timestamps(
        self,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> List[datetime]:
        """Generate timestamps based on timeframe - using timeframe manager"""
        # Parse timeframe using FlexibleTimeframeManager (eliminates duplication)
        try:
            _, timeframe_minutes = self.timeframe_manager.parse_timeframe(timeframe)
            interval = timedelta(minutes=timeframe_minutes)
        except Exception as e:
            log_error(f"Failed to parse timeframe {timeframe}: {e}")
            interval = timedelta(minutes=5)  # Default to 5 minutes
        
        timestamps = []
        current = start_time
        
        while current <= end_time:
            timestamps.append(current)
            current += interval
            
        return timestamps
        
    async def _get_spot_at_timestamp(
        self,
        underlying: str,
        timestamp: datetime
    ) -> Optional[float]:
        """Get spot price at specific timestamp"""
        # Production requires ticker_service integration - no direct database access
        try:
            raise RuntimeError(
                f"Historical spot price lookup requires ticker_service integration - "
                f"cannot query market_data table directly for {underlying} at {timestamp}. "
                f"Must route through ticker_service historical price API."
            )
        except Exception as e:
            log_error(f"Failed to get historical spot price for {underlying}: {e}")
            return None
        
    async def _get_historical_spot_prices(
        self,
        underlying: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get historical spot prices"""
        # Production requires ticker_service integration - no direct database access
        try:
            from app.errors import DataAccessError
            raise DataAccessError(
                f"Historical price range lookup requires ticker_service integration - "
                f"cannot query market_data table directly for {underlying} "
                f"from {start_time} to {end_time}. "
                f"Must route through ticker_service historical price range API."
            )
        except Exception as e:
            from app.errors import DataAccessError
            log_error(f"Failed to get historical prices for {underlying}: {e}")
            raise DataAccessError(f"Failed to retrieve historical prices for {underlying}: {e}") from e
        
    async def _get_historical_moneyness_options(
        self,
        underlying: str,
        spot_price: float,
        moneyness_level: str,
        expiry_date: str,
        timestamp: datetime
    ) -> List[Dict[str, Any]]:
        """Get options at moneyness level for historical timestamp"""
        # Production implementation must query real historical option data from database
        from app.errors import DataAccessError
        raise DataAccessError(f"Historical option data retrieval requires database implementation - cannot provide moneyness data for {underlying} at {moneyness_level} without complete database integration")
        
    async def _calculate_historical_greeks(
        self,
        options: List[Dict[str, Any]],
        spot_price: float,
        timestamp: datetime
    ) -> Dict[str, float]:
        """Calculate Greeks for historical options"""
        # Production implementation must use real pricing models and market data
        from app.errors import ComputationError
        raise ComputationError(f"Historical Greeks calculation requires pricing model implementation - cannot compute Greeks without Black-Scholes or equivalent pricing engine integration")