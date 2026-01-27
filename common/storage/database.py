"""
Production TimescaleDB integration module.
Provides real database connections and session management for production deployment.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Exception raised when database connection fails"""


class ProductionTimescaleDB:
    """Production TimescaleDB connection manager."""

    def __init__(self, database_url: str = None):
        if database_url:
            self.database_url = database_url
        else:
            # Must use database URL from config service settings only - no environment variable fallbacks
            raise DatabaseConnectionError("Database URL must be provided explicitly - no environment variable fallbacks allowed")

        if not self.database_url:
            logger.critical("DATABASE_URL not configured - TimescaleDB connection required")
            raise DatabaseConnectionError("Database URL is required for production deployment")

        self.pool: Pool | None = None
        logger.info("TimescaleDB connection manager initialized")

    async def connect(self):
        """Establish connection pool to TimescaleDB."""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            logger.info("TimescaleDB connection pool established")

        except Exception as e:
            logger.error(f"Failed to connect to TimescaleDB: {e}")
            raise DatabaseConnectionError(f"TimescaleDB connection failed: {e}") from e

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("TimescaleDB connection pool closed")

    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool."""
        if not self.pool:
            raise DatabaseConnectionError("Connection pool not initialized - call connect() first")

        async with self.pool.acquire() as conn:
            try:
                yield conn
            except Exception as e:
                logger.error(f"Database operation failed: {e}")
                raise DatabaseConnectionError(f"Database operation failed: {e}") from e

    async def execute_query(self, query: str, *args):
        """Execute query and return results."""
        async with self.get_connection() as conn:
            try:
                return await conn.fetch(query, *args)
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise DatabaseConnectionError(f"Query execution failed: {e}") from e

    async def execute_command(self, command: str, *args):
        """Execute command (INSERT, UPDATE, DELETE)."""
        async with self.get_connection() as conn:
            try:
                result = await conn.execute(command, *args)
                logger.debug(f"Command executed: {result}")
                return result
            except Exception as e:
                logger.error(f"Command execution failed: {e}")
                raise DatabaseConnectionError(f"Command execution failed: {e}") from e

    async def health_check(self) -> dict[str, Any]:
        """Check database connection health."""
        try:
            start_time = asyncio.get_event_loop().time()
            async with self.get_connection() as conn:
                await conn.fetchval("SELECT 1")
            connection_time_ms = round((asyncio.get_event_loop().time() - start_time) * 1000, 2)

            return {
                "status": "up",
                "connection_time_ms": connection_time_ms,
                "pool_size": self.pool.get_size() if self.pool else 0,
                "pool_idle": self.pool.get_idle_size() if self.pool else 0
            }

        except Exception as e:
            return {
                "status": "down",
                "error": str(e),
                "connection_time_ms": None
            }


# Mock database for testing ONLY - NO PRODUCTION USE
class MockDatabase:
    """Mock database for testing ONLY - NO PRODUCTION USE."""

    def __init__(self):
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database cannot be used in production environment")
        logger.warning("MockDatabase initialized - FOR TESTING ONLY")

    async def connect(self):
        """Mock connect - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")

    async def disconnect(self):
        """Mock disconnect - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")


# Mock session for testing ONLY
class MockSession:
    """Mock database session for testing ONLY - NO PRODUCTION USE."""

    def __init__(self):
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock session cannot be used in production environment")

    async def execute(self, query: str, params: dict[str, Any] = None):
        """Mock execute - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")

    async def commit(self):
        """Mock commit - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")

    async def rollback(self):
        """Mock rollback - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")

    async def close(self):
        """Mock close - DISABLED IN PRODUCTION."""
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock database operations not allowed in production")


# Mock results for testing ONLY
class MockQueryResult:
    """Mock query result."""

    def __init__(self, data: list = None):
        if os.getenv('ENVIRONMENT') == 'production':
            raise DatabaseConnectionError("Mock query results not allowed in production")
        self.data = data or []

    def fetchall(self):
        return self.data

    def fetchone(self):
        return self.data[0] if self.data else None


def get_database_connection():
    """Get database connection based on environment."""
    environment = os.getenv('ENVIRONMENT', 'development')

    if environment == 'production':
        # Production must use real TimescaleDB - no mocking allowed
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise DatabaseConnectionError("DATABASE_URL must be configured for production deployment")
        return ProductionTimescaleDB(database_url)
    # Development and testing can use mock database
    logger.warning("Using mock database for non-production environment")
    return MockDatabase()


@asynccontextmanager
async def get_timescale_session(database_url: str):
    """Get TimescaleDB session with proper error handling."""
    db = ProductionTimescaleDB(database_url)

    try:
        await db.connect()
        yield db
    except Exception as e:
        logger.error(f"TimescaleDB session error: {e}")
        raise DatabaseConnectionError(f"Database session failed: {e}") from e
    finally:
        try:
            await db.disconnect()
        except Exception as e:
            logger.warning(f"Error during database disconnect: {e}")


async def create_timescale_pool(database_url: str, **kwargs):
    """Create TimescaleDB connection pool with custom parameters."""
    if not database_url:
        raise DatabaseConnectionError("Database URL must be provided explicitly - no environment variable fallbacks allowed")

    try:
        pool = await asyncpg.create_pool(database_url, **kwargs)
        logger.info("Custom TimescaleDB connection pool created")
        return pool
    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        raise DatabaseConnectionError(f"Connection pool creation failed: {e}") from e


def get_database_url():
    """Get database URL from config service settings - no environment variable access."""
    raise DatabaseConnectionError("Direct environment variable access not allowed - use config service settings instead")
