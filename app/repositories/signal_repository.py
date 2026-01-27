"""
Signal Repository for Database Operations
Handles all database interactions for signal data

Updated for consolidation: Historical data queries now route through ticker_service
for consistent data sourcing. Only current/live signal data is stored locally.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from app.services.historical_data_manager import get_historical_data_manager
from common.storage.database import get_timescaledb_session

logger = logging.getLogger(__name__)

# from app.models.signal_models import SignalGreeks, SignalIndicators


class DatabaseError(Exception):
    """Custom exception for database operation failures"""


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
        self.session_cm = get_timescaledb_session()
        self.session = await self.session_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session_cm:
            return await self.session_cm.__aexit__(exc_type, exc_val, exc_tb)
        return None

    async def fetchrow(self, query, *params):
        """Execute query and return single row (asyncpg compatibility)"""
        import re

        from sqlalchemy import text
        # Convert positional params to named params for SQLAlchemy
        param_dict = {f'param_{i}': p for i, p in enumerate(params)}

        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        # Use regex to properly handle multi-digit parameters
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'

        converted_query = re.sub(r'\$(\d+)', replace_param, query)

        result = await self.session.execute(text(converted_query), param_dict)

        # Fetch the row first (especially important for RETURNING clauses)
        row = result.fetchone()

        # Commit after fetching to avoid ResourceClosedError
        query_upper = query.strip().upper()
        if query_upper.startswith(('INSERT', 'UPDATE', 'DELETE')):
            await self.session.commit()

        return dict(row._mapping) if row else None

    async def fetch(self, query, *params):
        """Execute query and return all rows (asyncpg compatibility)"""
        import re

        from sqlalchemy import text
        # Convert positional params to named params
        param_dict = {f'param_{i}': p for i, p in enumerate(params)}

        # Convert $1, $2, $10, etc. style to :param_0, :param_1, :param_9 etc.
        def replace_param(match):
            param_num = int(match.group(1)) - 1  # Convert to 0-based index
            return f':param_{param_num}'

        converted_query = re.sub(r'\$(\d+)', replace_param, query)

        result = await self.session.execute(text(converted_query), param_dict)

        # Fetch all rows first (especially important for RETURNING clauses)
        rows = [dict(row._mapping) for row in result]

        # Commit after fetching to avoid ResourceClosedError
        query_upper = query.strip().upper()
        if query_upper.startswith(('INSERT', 'UPDATE', 'DELETE')):
            await self.session.commit()

        return rows

    async def execute(self, query, *params):
        """Execute query (asyncpg compatibility)"""
        import re

        from sqlalchemy import text
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
        import re

        from sqlalchemy import text

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

    async def get_latest_greeks(self, instrument_key: str) -> dict[str, Any] | None:
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
    ) -> list[dict[str, Any]]:
        """
        Get historical Greeks data - routes through ticker_service (CONSOLIDATED)

        Args:
            instrument_key: Instrument identifier
            start_time: Start of time range
            end_time: End of time range
            interval_minutes: Aggregation interval in minutes

        Returns:
            list of Greeks data points from ticker_service
        """
        try:
            # Route through ticker_service for historical data
            historical_manager = await get_historical_data_manager()
            if not historical_manager:
                logger.error("Historical data manager not available for Greeks data")
                return []

            # Calculate timeframe from interval
            timeframe_map = {
                1: "1minute",
                5: "5minute",
                15: "15minute",
                30: "30minute",
                60: "1hour"
            }
            timeframe = timeframe_map.get(interval_minutes, "5minute")

            # Calculate periods needed
            time_diff = end_time - start_time
            periods_needed = max(int(time_diff.total_seconds() / (interval_minutes * 60)), 1)

            # Request from ticker_service
            result = await historical_manager.get_historical_data_for_indicator(
                symbol=instrument_key,
                timeframe=timeframe,
                periods_required=periods_needed,
                indicator_name="greeks"
            )

            if result.get("success") and result.get("data"):
                # Transform ticker_service data to expected format
                historical_data = []
                for data_point in result["data"]:
                    # Convert ticker_service format to repository format
                    historical_data.append({
                        "id": f"historical_{len(historical_data)}",
                        "signal_id": None,
                        "instrument_key": instrument_key,
                        "timestamp": datetime.fromisoformat(data_point.get("timestamp", start_time.isoformat())),
                        "delta": data_point.get("delta", 0.0),
                        "gamma": data_point.get("gamma", 0.0),
                        "theta": data_point.get("theta", 0.0),
                        "vega": data_point.get("vega", 0.0),
                        "rho": data_point.get("rho", 0.0),
                        "implied_volatility": data_point.get("iv", 0.0),
                        "theoretical_value": data_point.get("theoretical_value", 0.0),
                        "underlying_price": data_point.get("underlying_price", 0.0),
                        "strike_price": data_point.get("strike_price", 0.0),
                        "time_to_expiry": data_point.get("time_to_expiry", 0.0),
                        "source": "ticker_service"
                    })

                # Filter to exact time range
                filtered_data = [
                    item for item in historical_data
                    if start_time <= item["timestamp"] <= end_time
                ]

                logger.info(f"Retrieved {len(filtered_data)} historical Greeks from ticker_service")
                return filtered_data

            # STRICT COMPLIANCE: No TimescaleDB fallback - ticker_service is the only source
            logger.error(f"ticker_service unavailable for {instrument_key}, no historical data available")
            return []

        except Exception as e:
            logger.error(f"Error getting historical Greeks from ticker_service: {e}")
            # STRICT COMPLIANCE: Fail without TimescaleDB fallback
            return []


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
    ) -> dict[str, Any] | None:
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

    async def save_moneyness_greeks(self, moneyness_data: dict[str, Any]) -> int:
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
        data: list[dict[str, Any]]
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
    ) -> list[dict[str, Any]]:
        """Get custom timeframe data"""
        await self.ensure_initialized()

        try:
            # Use compatibility wrapper for asyncpg-style API
            async with self.db_connection.acquire() as conn:
                # Index on instrument_key should be verified during deployment
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
    ) -> dict[str, Any]:
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

    async def get_moneyness_history(
        self,
        underlying: str,
        moneyness_level: str,
        expiry_date: str,
        start_time: datetime,
        end_time: datetime
    ) -> list[dict[str, Any]]:
        """
        Get moneyness historical data - routes through ticker_service (CONSOLIDATED)

        Args:
            underlying: Underlying symbol
            moneyness_level: Moneyness level (ATM, OTM, etc.)
            expiry_date: Option expiry date
            start_time: Start time
            end_time: End time

        Returns:
            list of moneyness historical data from ticker_service
        """
        try:
            # Route through ticker_service for moneyness historical data
            historical_manager = await get_historical_data_manager()
            if not historical_manager:
                logger.error("Historical data manager not available for moneyness data")
                return []

            # Create virtual symbol for moneyness data
            symbol = f"{underlying}_{moneyness_level}_{expiry_date}"

            # Calculate periods needed
            time_diff = end_time - start_time
            periods_needed = max(int(time_diff.total_seconds() / 300), 1)  # 5-minute intervals

            # Request from ticker_service
            result = await historical_manager.get_historical_data_for_indicator(
                symbol=symbol,
                timeframe="5minute",
                periods_required=periods_needed,
                indicator_name="moneyness_greeks"
            )

            if result.get("success") and result.get("data"):
                # Transform ticker_service data to expected format
                moneyness_data = []
                for data_point in result["data"]:
                    moneyness_data.append({
                        "timestamp": datetime.fromisoformat(data_point.get("timestamp", start_time.isoformat())),
                        "underlying": underlying,
                        "moneyness_level": moneyness_level,
                        "expiry_date": expiry_date,
                        "greeks": {
                            "delta": data_point.get("delta", 0.0),
                            "gamma": data_point.get("gamma", 0.0),
                            "theta": data_point.get("theta", 0.0),
                            "vega": data_point.get("vega", 0.0),
                            "rho": data_point.get("rho", 0.0),
                            "iv": data_point.get("iv", 0.0)
                        },
                        "source": "ticker_service"
                    })

                # Filter to time range
                filtered_data = [
                    item for item in moneyness_data
                    if start_time <= item["timestamp"] <= end_time
                ]

                logger.info(f"Retrieved {len(filtered_data)} moneyness historical points from ticker_service")
                return filtered_data

            # If ticker_service unavailable, return empty (no local fallback for moneyness)
            logger.warning(f"ticker_service unavailable for moneyness data: {underlying}_{moneyness_level}")
            return []

        except Exception as e:
            logger.error(f"Error getting moneyness history from ticker_service: {e}")
            return []
