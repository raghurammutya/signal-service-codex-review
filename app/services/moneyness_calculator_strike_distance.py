"""
Strike Distance Based Moneyness Calculator
Calculates moneyness based on number of strikes from ATM
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


@dataclass
class MoneynessResult:
    """Result of moneyness calculation"""
    strike: float
    atm_strike: float
    strike_distance: int  # Number of strikes from ATM
    moneyness_category: str  # ATM, ITM, or OTM
    

class StrikeDistanceMoneynessCalculator:
    """
    Calculate moneyness based on strike distance from ATM
    Simple classification: ATM (0 strikes), ITM, or OTM
    """
    
    async def get_available_strikes(
        self,
        session: AsyncSession,
        underlying: str,
        expiry_date: str,
        option_type: str
    ) -> List[float]:
        """Get all available strikes from unified_symbols table"""
        try:
            # Query unified_symbols for strikes
            stmt = select(UnifiedSymbol.strike_price).where(
                and_(
                    UnifiedSymbol.underlying == underlying,
                    UnifiedSymbol.expiry_date == expiry_date,
                    UnifiedSymbol.option_type == option_type,
                    UnifiedSymbol.symbol_type == 'options'
                )
            ).order_by(UnifiedSymbol.strike_price)
            
            result = await session.execute(stmt)
            strikes = [row[0] for row in result.fetchall()]
            
            if not strikes:
                # Fallback: derive from historical data
                logger.warning(f"No strikes in unified_symbols for {underlying} {expiry_date}")
                strikes = await self._derive_strikes_from_historical(
                    session, underlying, expiry_date, option_type
                )
            
            return sorted(strikes)
            
        except Exception as e:
            logger.error(f"Error getting strikes: {e}")
            return []
    
    async def _derive_strikes_from_historical(
        self,
        session: AsyncSession,
        underlying: str,
        expiry_date: str,
        option_type: str
    ) -> List[float]:
        """Derive strikes from historical_data if unified_symbols not available"""
        stmt = select(
            func.distinct(
                func.cast(
                    func.split_part(HistoricalData.symbol, '@', 6),
                    Float
                )
            )
        ).where(
            and_(
                HistoricalData.symbol.like(f'%{underlying}%'),
                HistoricalData.symbol.like(f'%{expiry_date}%'),
                HistoricalData.symbol.like(f'%{option_type}%')
            )
        ).order_by(1)
        
        result = await session.execute(stmt)
        return [row[0] for row in result.fetchall() if row[0] is not None]
    
    def find_atm_strike(self, strikes: List[float], spot_price: float) -> float:
        """Find the ATM strike (closest to spot price)"""
        if not strikes:
            raise ValueError("No strikes available")
            
        return min(strikes, key=lambda x: abs(x - spot_price))
    
    def calculate_strike_distance(
        self,
        strike: float,
        atm_strike: float,
        strikes: List[float],
        option_type: str
    ) -> int:
        """
        Calculate number of strikes between given strike and ATM
        Returns signed distance: positive for OTM, negative for ITM
        """
        try:
            strike_idx = strikes.index(strike)
            atm_idx = strikes.index(atm_strike)
            
            # Raw distance
            distance = strike_idx - atm_idx
            
            # For calls: higher strikes are OTM (positive)
            # For puts: lower strikes are OTM (need to invert)
            if option_type.lower() == 'put':
                distance = -distance
                
            return distance
            
        except ValueError:
            logger.error(f"Strike {strike} or ATM {atm_strike} not in strike list")
            return 0
    
    def classify_moneyness(self, strike_distance: int) -> str:
        """
        Simple classification based on strike distance
        0 = ATM, positive = OTM, negative = ITM
        """
        if strike_distance == 0:
            return "ATM"
        elif strike_distance > 0:
            return "OTM"
        else:
            return "ITM"
    
    async def calculate_moneyness(
        self,
        session: AsyncSession,
        option_symbol: str,
        spot_price: float,
        timestamp: Optional[str] = None
    ) -> MoneynessResult:
        """
        Calculate moneyness for an option
        
        Args:
            session: Database session
            option_symbol: Full option symbol (e.g., EXCHANGE@SYMBOL@ASSET_TYPE@EXPIRY@TYPE@STRIKE)
            spot_price: Current spot price
            timestamp: Optional timestamp for historical calculation
            
        Returns:
            MoneynessResult with strike distance and classification
        """
        # Parse option symbol
        parts = option_symbol.split('@')
        if len(parts) < 6:
            raise ValueError(f"Invalid option symbol: {option_symbol}")
            
        underlying = parts[1]
        expiry_date = parts[3]
        option_type = parts[4]
        strike = float(parts[5])
        
        # Get available strikes
        strikes = await self.get_available_strikes(
            session, underlying, expiry_date, option_type
        )
        
        if not strikes:
            raise ValueError(f"No strikes available for {underlying} {expiry_date}")
        
        # Find ATM strike
        atm_strike = self.find_atm_strike(strikes, spot_price)
        
        # Calculate strike distance
        strike_distance = self.calculate_strike_distance(
            strike, atm_strike, strikes, option_type
        )
        
        # Classify moneyness
        moneyness = self.classify_moneyness(strike_distance)
        
        return MoneynessResult(
            strike=strike,
            atm_strike=atm_strike,
            strike_distance=strike_distance,
            moneyness_category=moneyness
        )
    
    async def calculate_moneyness_batch(
        self,
        session: AsyncSession,
        options_data: List[dict],
        spot_prices: dict
    ) -> List[MoneynessResult]:
        """
        Calculate moneyness for a batch of options
        Optimized to minimize database queries
        """
        # Group by expiry for efficiency
        from collections import defaultdict
        by_expiry = defaultdict(list)
        
        for option in options_data:
            parts = option['symbol'].split('@')
            expiry = parts[3]
            by_expiry[expiry].append(option)
        
        results = []
        
        for expiry, options in by_expiry.items():
            # Get strikes once per expiry
            underlying = options[0]['symbol'].split('@')[1]
            option_type = options[0]['symbol'].split('@')[4]
            
            strikes = await self.get_available_strikes(
                session, underlying, expiry, option_type
            )
            
            if not strikes:
                continue
            
            for option in options:
                timestamp = option.get('timestamp')
                spot_price = spot_prices.get(timestamp, spot_prices.get('default'))
                
                if not spot_price:
                    continue
                
                # Find ATM for this spot price
                atm_strike = self.find_atm_strike(strikes, spot_price)
                
                # Calculate distance
                strike = float(option['symbol'].split('@')[5])
                strike_distance = self.calculate_strike_distance(
                    strike, atm_strike, strikes, option_type
                )
                
                # Classify
                moneyness = self.classify_moneyness(strike_distance)
                
                results.append(MoneynessResult(
                    strike=strike,
                    atm_strike=atm_strike,
                    strike_distance=strike_distance,
                    moneyness_category=moneyness
                ))
        
        return results


# For backward compatibility
def calculate_moneyness_simple(spot_price: float, strike: float, option_type: str) -> str:
    """
    Simple moneyness calculation when strike list not available
    Falls back to ratio-based classification
    """
    ratio = spot_price / strike
    
    if 0.98 <= ratio <= 1.02:
        return "ATM"
    elif option_type.lower() == 'call':
        return "ITM" if ratio > 1.02 else "OTM"
    else:  # put
        return "OTM" if ratio > 1.02 else "ITM"