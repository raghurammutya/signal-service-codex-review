"""
Signal Repository for Database Operations
Handles all database interactions for signal data
"""
import asyncio
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
from decimal import Decimal

import logging
logger = logging.getLogger(__name__)
from common.storage.database import get_timescaledb_session
# from app.models.signal_models import SignalGreeks, SignalIndicators
# TODO: Add signal models when available


class DatabaseError(Exception):
    """Custom exception for database operation failures"""
    pass


class DatabaseConnectionWrapper:
    """
    Compatibility wrapper to adapt SQLAlchemy sessions to asyncpg-style API
    This allows existing repository code to work without major refactoring
    """
    
    def acquire(self):
        """Return a context manager for database operations"""
        return DatabaseSessionContext()


class DatabaseSessionContext:
    """Context manager that provides asyncpg-like interface over SQLAlchemy"""
    
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        from common.storage.database import get_timescaledb_session
        self.session_cm = get_timescaledb_session()
        self.session = await self.session_cm.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session_cm:
            return await self.session_cm.__aexit__(exc_type, exc_val, exc_tb)
    
    async def fetchrow(self, query, *params):
        """Execute query and return single row (asyncpg compatibility)"""
        from sqlalchemy import text
        import re
        # Convert positional params to named params for SQLAlchemy
        param_dict = {f'param_{i}': p for i, p in enumerate(params)}
        
        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        # Use regex to properly handle multi-digit parameters
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'
        
        converted_query = re.sub(r'\$(\d+)', replace_param, query)
        
        result = await self.session.execute(text(converted_query), param_dict)
        row = result.fetchone()
        return dict(row._mapping) if row else None
    
    async def fetch(self, query, *params):
        """Execute query and return all rows (asyncpg compatibility)"""
        from sqlalchemy import text
        import re
        # Convert positional params to named params  
        param_dict = {f'param_{i}': p for i, p in enumerate(params)}
        
        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'
        
        converted_query = re.sub(r'\$(\d+)', replace_param, query)
            
        result = await self.session.execute(text(converted_query), param_dict)
        return [dict(row._mapping) for row in result]
    
    async def execute(self, query, *params):
        """Execute query (asyncpg compatibility)"""
        from sqlalchemy import text
        import re
        # Convert positional params to named params
        param_dict = {f'param_{i}': p for i, p in enumerate(params)}
        
        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'
        
        converted_query = re.sub(r'\$(\d+)', replace_param, query)
            
        result = await self.session.execute(text(converted_query), param_dict)
        await self.session.commit()
        return result.rowcount
    
    async def executemany(self, query, param_list):
        """Execute query with multiple parameter sets (asyncpg compatibility)"""
        from sqlalchemy import text
        import re
        
        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'
        
        converted_query = re.sub(r'\$(\d+)', replace_param, query)
        
        for params in param_list:
            # Convert positional params to named params
            param_dict = {f'param_{i}': p for i, p in enumerate(params)}
            await self.session.execute(text(converted_query), param_dict)
        await self.session.commit()


class SignalRepository:
    """
    Repository for signal data persistence and retrieval
    Uses TimescaleDB for time-series optimization
    """
    
    def __init__(self):
        self.db_connection = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize database connection"""
        if not self._initialized:
            # For now, create a compatibility wrapper
            self.db_connection = DatabaseConnectionWrapper()
            self._initialized = True
            logger.info("SignalRepository initialized")
            
    async def ensure_initialized(self):
        """Ensure repository is initialized"""
        if not self._initialized:
            await self.initialize()
    
    def _get_session(self):
        """Get database session context manager"""
        from common.storage.database import get_timescaledb_session
        return get_timescaledb_session()
            
    # Greeks Operations
    
    async def save_greeks(self, greeks: Any) -> int:  # SignalGreeks model not yet available
        """
        Save Greeks calculation to database
        
        Args:
            greeks: SignalGreeks model instance
            
        Returns:
            Record ID
        """
        await self.ensure_initialized()
        
        try:
            # Use compatibility wrapper for asyncpg-style API
            async with self.db_connection.acquire() as conn:
                result = await conn.fetchrow("""
                    INSERT INTO signal_greeks (
                        signal_id, instrument_key, timestamp,
                        delta, gamma, theta, vega, rho,
                        implied_volatility, theoretical_value,
                        underlying_price, strike_price, time_to_expiry,
                        created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING id
                """, 
                greeks.signal_id, greeks.instrument_key, greeks.timestamp,
                greeks.delta, greeks.gamma, greeks.theta, greeks.vega, greeks.rho,
                greeks.implied_volatility, greeks.theoretical_value,
                greeks.underlying_price, greeks.strike_price, greeks.time_to_expiry,
                datetime.utcnow()
                )
                
                return result['id'] if result else None
                
        except Exception as e:
            logger.exception(f"Error saving Greeks: {e}")
            raise
            
    async def get_latest_greeks(self, instrument_key: str) -> Optional[Dict[str, Any]]:
        """
        Get latest Greeks for an instrument
        
        Args:
            instrument_key: Instrument identifier
            
        Returns:
            Latest Greeks data or None
        """
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        signal_id,
                        instrument_key,
                        timestamp,
                        delta,
                        gamma,
                        theta,
                        vega,
                        rho,
                        implied_volatility,
                        theoretical_value,
                        underlying_price,
                        strike_price,
                        time_to_expiry
                    FROM signal_greeks
                    WHERE instrument_key = $1
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    instrument_key,
                )
                
                return dict(result) if result else None
                
        except Exception as e:
            logger.exception(f"Error getting latest Greeks: {e}")
            raise DatabaseError(f"Failed to fetch latest Greeks for {instrument_key}: {e}") from e
            
    async def get_historical_greeks(
        self,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get historical Greeks data with optional aggregation
        
        Args:
            instrument_key: Instrument identifier
            start_time: Start of time range
            end_time: End of time range
            interval_minutes: Aggregation interval in minutes
            
        Returns:
            List of Greeks data points
        """
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                if interval_minutes == 1:
                    # Raw data
                    results = await conn.fetch(
                        """
                        SELECT
                            id,
                            signal_id,
                            instrument_key,
                            timestamp,
                            delta,
                            gamma,
                            theta,
                            vega,
                            rho,
                            implied_volatility,
                            theoretical_value,
                            underlying_price,
                            strike_price,
                            time_to_expiry
                        FROM signal_greeks
                        WHERE instrument_key = $1
                          AND timestamp >= $2
                          AND timestamp <= $3
                        ORDER BY timestamp
                        """,
                        instrument_key,
                        start_time,
                        end_time,
                    )
                else:
                    # Aggregated data
                    results = await conn.fetch("""
                        SELECT 
                            time_bucket($4::interval, timestamp) as bucket,
                            instrument_key,
                            AVG(delta) as delta,
                            AVG(gamma) as gamma,
                            AVG(theta) as theta,
                            AVG(vega) as vega,
                            AVG(rho) as rho,
                            AVG(implied_volatility) as implied_volatility,
                            AVG(theoretical_value) as theoretical_value,
                            AVG(underlying_price) as underlying_price,
                            LAST(strike_price, timestamp) as strike_price,
                            COUNT(*) as data_points
                        FROM signal_greeks
                        WHERE instrument_key = $1
                          AND timestamp >= $2
                          AND timestamp <= $3
                        GROUP BY bucket, instrument_key
                        ORDER BY bucket
                    """, instrument_key, start_time, end_time, f'{interval_minutes} minutes')
                    
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.exception(f"Error getting historical Greeks: {e}")
            raise DatabaseError(f"Failed to fetch historical Greeks for {instrument_key}: {e}") from e
            
    # Indicators Operations
    
    async def save_indicator(self, indicator: Any) -> int:  # SignalIndicators model not yet available
        """Save indicator calculation to database"""
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                result = await conn.fetchrow("""
                    INSERT INTO signal_indicators (
                        signal_id, instrument_key, timestamp,
                        indicator_name, parameters, values,
                        created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """,
                indicator.signal_id, indicator.instrument_key, indicator.timestamp,
                indicator.indicator_name, json.dumps(indicator.parameters),
                json.dumps(indicator.values), datetime.utcnow()
                )
                
                return result['id']
                
        except Exception as e:
            logger.exception(f"Error saving indicator: {e}")
            raise
            
    async def get_latest_indicator(
        self,
        instrument_key: str,
        indicator_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest indicator value"""
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        signal_id,
                        instrument_key,
                        timestamp,
                        indicator_name,
                        parameters,
                        values
                    FROM signal_indicators
                    WHERE instrument_key = $1
                      AND indicator_name = $2
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    instrument_key,
                    indicator_name,
                )
                
                if result:
                    data = dict(result)
                    # Parse JSON fields
                    data['parameters'] = json.loads(data['parameters'])
                    data['values'] = json.loads(data['values'])
                    return data
                    
                return None
                
        except Exception as e:
            logger.exception(f"Error getting latest indicator: {e}")
            raise DatabaseError(f"Failed to fetch latest indicator {indicator_name} for {instrument_key}: {e}") from e
            
    # Moneyness Greeks Operations
    
    async def save_moneyness_greeks(self, moneyness_data: Dict[str, Any]) -> int:
        """Save aggregated moneyness Greeks"""
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                result = await conn.fetchrow("""
                    INSERT INTO signal_moneyness_greeks (
                        underlying_symbol, moneyness_level, expiry_date,
                        timestamp, spot_price,
                        all_delta, all_gamma, all_theta, all_vega, all_rho, all_iv, all_count,
                        calls_delta, calls_gamma, calls_theta, calls_vega, calls_rho, calls_iv, calls_count,
                        puts_delta, puts_gamma, puts_theta, puts_vega, puts_rho, puts_iv, puts_count,
                        min_strike, max_strike, strike_count,
                        created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19,
                        $20, $21, $22, $23, $24, $25, $26,
                        $27, $28, $29, $30
                    )
                    RETURNING id
                """,
                moneyness_data['underlying_symbol'],
                moneyness_data['moneyness_level'],
                moneyness_data.get('expiry_date'),
                moneyness_data['timestamp'],
                moneyness_data['spot_price'],
                # All Greeks
                moneyness_data['aggregated_greeks']['all'].get('delta'),
                moneyness_data['aggregated_greeks']['all'].get('gamma'),
                moneyness_data['aggregated_greeks']['all'].get('theta'),
                moneyness_data['aggregated_greeks']['all'].get('vega'),
                moneyness_data['aggregated_greeks']['all'].get('rho'),
                moneyness_data['aggregated_greeks']['all'].get('iv'),
                moneyness_data['aggregated_greeks']['all'].get('count'),
                # Calls Greeks
                moneyness_data['aggregated_greeks']['calls'].get('delta') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('gamma') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('theta') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('vega') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('rho') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('iv') if moneyness_data['aggregated_greeks'].get('calls') else None,
                moneyness_data['aggregated_greeks']['calls'].get('count') if moneyness_data['aggregated_greeks'].get('calls') else None,
                # Puts Greeks
                moneyness_data['aggregated_greeks']['puts'].get('delta') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('gamma') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('theta') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('vega') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('rho') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('iv') if moneyness_data['aggregated_greeks'].get('puts') else None,
                moneyness_data['aggregated_greeks']['puts'].get('count') if moneyness_data['aggregated_greeks'].get('puts') else None,
                # Strike info
                moneyness_data['strikes'].get('min'),
                moneyness_data['strikes'].get('max'),
                moneyness_data['strikes'].get('count'),
                datetime.utcnow()
                )
                
                return result['id']
                
        except Exception as e:
            logger.exception(f"Error saving moneyness Greeks: {e}")
            raise
            
    # Custom Timeframe Operations
    
    async def save_custom_timeframe_data(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe_minutes: int,
        data: List[Dict[str, Any]]
    ):
        """Save custom timeframe aggregated data"""
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                # Batch insert
                await conn.executemany("""
                    INSERT INTO signal_custom_timeframes (
                        instrument_key, signal_type, timeframe_minutes,
                        timestamp, data, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (instrument_key, signal_type, timeframe_minutes, timestamp)
                    DO UPDATE SET data = $5, updated_at = CURRENT_TIMESTAMP
                """,
                [(instrument_key, signal_type, timeframe_minutes,
                  record['timestamp'], json.dumps(record), datetime.utcnow())
                 for record in data]
                )
                
                logger.info(f"Saved {len(data)} custom timeframe records")
                
        except Exception as e:
            logger.exception(f"Error saving custom timeframe data: {e}")
            raise
            
    async def get_custom_timeframe_data(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe_minutes: int,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get custom timeframe data"""
        await self.ensure_initialized()
        
        try:
            # Use compatibility wrapper for asyncpg-style API
            async with self.db_connection.acquire() as conn:
                # TODO: Ensure index on instrument_key for better performance
                results = await conn.fetch("""
                    SELECT timestamp, data
                    FROM signal_custom_timeframes
                    WHERE instrument_key = $1
                      AND signal_type = $2
                      AND timeframe_minutes = $3
                      AND timestamp >= $4
                      AND timestamp <= $5
                    ORDER BY timestamp
                """, instrument_key, signal_type, timeframe_minutes,
                start_time, end_time)
                
                return [
                    {**json.loads(row['data']), 'timestamp': row['timestamp']}
                    for row in results
                ]
                
        except Exception as e:
            logger.exception(f"Error getting custom timeframe data: {e}")
            raise DatabaseError(f"Failed to fetch custom timeframe data for {instrument_key}: {e}") from e
            
    # Metrics and Analytics
    
    async def get_computation_metrics(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Get computation metrics for monitoring"""
        await self.ensure_initialized()
        
        try:
            async with self.db_connection.acquire() as conn:
                # Greeks metrics
                greeks_metrics = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_computations,
                        COUNT(DISTINCT instrument_key) as unique_instruments,
                        AVG(EXTRACT(EPOCH FROM (created_at - timestamp))) as avg_latency_seconds
                    FROM signal_greeks
                    WHERE timestamp >= $1 AND timestamp <= $2
                """, start_time, end_time)
                
                # Indicators metrics
                indicators_metrics = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_computations,
                        COUNT(DISTINCT indicator_name) as unique_indicators,
                        COUNT(DISTINCT instrument_key) as unique_instruments
                    FROM signal_indicators
                    WHERE timestamp >= $1 AND timestamp <= $2
                """, start_time, end_time)
                
                return {
                    'greeks': dict(greeks_metrics) if greeks_metrics else {},
                    'indicators': dict(indicators_metrics) if indicators_metrics else {},
                    'time_range': {
                        'start': start_time.isoformat(),
                        'end': end_time.isoformat()
                    }
                }
                
        except Exception as e:
            logger.exception(f"Error getting computation metrics: {e}")
            raise DatabaseError(f"Failed to fetch computation metrics: {e}") from e
            
    async def cleanup_old_data(self, retention_days: int = 90):
        """Clean up old data based on retention policy"""
        await self.ensure_initialized()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            async with self.db_connection.acquire() as conn:
                # Clean Greeks
                greeks_deleted = await conn.execute("""
                    DELETE FROM signal_greeks
                    WHERE timestamp < $1
                """, cutoff_date)
                
                # Clean indicators
                indicators_deleted = await conn.execute(
                    """
                    DELETE FROM signal_indicators
                    WHERE timestamp < $1
                    """,
                    cutoff_date,
                )

                logger.info(
                    "Cleaned up old data: %s Greeks, %s indicators",
                    greeks_deleted,
                    indicators_deleted,
                )

        except Exception as e:
            logger.exception("Error cleaning up old data: %s", e)
