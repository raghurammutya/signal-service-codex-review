"""
Production database module with fallback to mock for testing
"""
import os
import logging
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager, contextmanager
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Global database connections
_engine = None
_async_session_factory = None


class DatabaseConnectionError(Exception):
    """Database connection error."""
    pass


class ProductionDatabase:
    """Production database with TimescaleDB support."""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.engine = None
        self.session_factory = None
        
    async def connect(self):
        """Connect to database."""
        try:
            # Create async engine for TimescaleDB (PostgreSQL)
            self.engine = create_async_engine(
                self.connection_string,
                poolclass=NullPool,
                echo=False,
                future=True
            )
            
            # Create session factory
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                
            logger.info("Connected to TimescaleDB successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}")
    
    async def disconnect(self):
        """Disconnect from database."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")


class MockDatabase:
    """Mock database for testing ONLY - NO PRODUCTION USE."""
    
    def __init__(self):
        raise RuntimeError(
            "MockDatabase is for testing only. "
            "Production code must use ProductionDatabase with config_service configuration. "
            "No mock fallbacks allowed per architecture compliance."
        )
    
    async def connect(self):
        """Mock connect - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database connections are disabled in all environments.")
    
    async def disconnect(self):
        """Mock disconnect - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database connections are disabled in all environments.")


class MockSession:
    """Mock database session for testing ONLY - NO PRODUCTION USE."""
    def __init__(self):
        raise RuntimeError(
            "MockSession is for testing only. "
            "Production code must use real database sessions via ProductionDatabase. "
            "No mock fallbacks allowed per architecture compliance."
        )
    
    async def execute(self, query, params=None):
        """Mock execute - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database sessions are disabled in all environments.")
        
    async def commit(self):
        """Mock commit - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database sessions are disabled in all environments.")
        
    async def rollback(self):
        """Mock rollback - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database sessions are disabled in all environments.")
        
    async def close(self):
        """Mock close - DISABLED IN PRODUCTION."""
        raise RuntimeError("Mock database sessions are disabled in all environments.")

    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class MockResult:
    """Mock query result."""
    def fetchall(self):
        return []
    
    def fetchone(self):
        return None
        
    def rowcount(self):
        return 0


async def get_database_connection():
    """Get database connection based on environment."""
    global _engine, _async_session_factory
    
    # Check if we already have a connection
    if _engine and _async_session_factory:
        return _engine, _async_session_factory
    
    # Get database URL from config_service (Architecture Principle #1: Config service exclusivity)
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from common.config_service.client import ConfigServiceClient
        
        # ARCHITECTURE COMPLIANCE: Environment MUST be provided externally (no defaults)
        environment = os.getenv("ENVIRONMENT")
        if not environment:
            raise ValueError("ENVIRONMENT variable not set. Config service requires explicit environment - no defaults allowed per architecture.")
            
        client = ConfigServiceClient(
            service_name="signal_service",
            environment=environment,
            timeout=5
        )
        database_url = client.get_secret("DATABASE_URL")
        # Use the same environment (no additional config call needed)
    except Exception as e:
        logger.error(f"Failed to get database URL from config_service: {e}")
        raise ValueError(f"Config service failure: {e}. No fallbacks allowed per architecture.")
    
    if not database_url:
        # ARCHITECTURE COMPLIANCE: No silent fallbacks (fail-fast per Architecture Principle #1)
        raise DatabaseConnectionError(
            f"Database URL not configured in config_service for {environment} environment. "
            "Config service is mandatory - no fallbacks allowed."
        )
    
    try:
        # Create production database connection
        db = ProductionDatabase(database_url)
        await db.connect()
        
        _engine = db.engine
        _async_session_factory = db.session_factory
        
        return _engine, _async_session_factory
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        
        # ARCHITECTURE COMPLIANCE: No environment-based fallbacks (fail-fast per Architecture Principle #1)
        raise DatabaseConnectionError(f"Database connection failed for {environment} environment: {e}. No fallbacks allowed per architecture.")


@asynccontextmanager
async def get_timescaledb_session():
    """Get TimescaleDB session with proper error handling."""
    # ARCHITECTURE COMPLIANCE: No environment-based fallbacks (fail-fast per Architecture Principle #1)
    try:
        engine, session_factory = await get_database_connection()
        
        if session_factory is None:
            raise DatabaseConnectionError(
                "Database connection failed - no session factory available. "
                "Config service must be properly configured. No fallbacks allowed per architecture."
            )
        
        # Use real session only
        async with session_factory() as session:
            yield session
                
    except Exception as e:
        logger.error(f"Database session error: {e}")
        # ARCHITECTURE COMPLIANCE: No mock fallbacks for any environment
        raise DatabaseConnectionError(
            f"Critical database error: {e}. "
            "Service cannot continue without proper database connection. No fallbacks allowed per architecture."
        ) from e


@contextmanager  
def get_timescaledb_session_sync():
    """Synchronous version - deprecated, use async version."""
    # ARCHITECTURE COMPLIANCE: No mock fallbacks allowed per Architecture Principle #1
    raise DatabaseConnectionError(
        "Synchronous database sessions are not supported. "
        "Use async version with proper config_service configuration. No mock fallbacks allowed per architecture."
    )


def get_database():
    """Get database instance - deprecated, use get_database_connection."""
    # ARCHITECTURE COMPLIANCE: No mock fallbacks allowed per Architecture Principle #1
    raise DatabaseConnectionError(
        "Legacy get_database function is not supported. "
        "Use get_database_connection with proper config_service configuration. No mock fallbacks allowed per architecture."
    )


class DatabaseHealthChecker:
    """Database health checker."""
    
    @staticmethod
    async def check_health() -> Dict[str, Any]:
        """Check database health."""
        try:
            engine, _ = await get_database_connection()
            
            if engine is None:
                # ARCHITECTURE COMPLIANCE: No mock database status allowed
                raise DatabaseConnectionError(
                    "Database engine not available. Config service must be properly configured. "
                    "No mock database allowed per architecture."
                )
            
            # Test connection
            import time
            start_time = time.time()
            
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                
            connection_time = (time.time() - start_time) * 1000
            
            return {
                "status": "up",
                "connection_time_ms": round(connection_time, 2),
                "engine_pool_size": engine.pool.size(),
                "engine_checked_in": engine.pool.checkedin(),
                "engine_checked_out": engine.pool.checkedout()
            }
            
        except Exception as e:
            return {
                "status": "down", 
                "error": str(e),
                "connection_time_ms": None
            }