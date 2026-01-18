"""
<<<<<<< HEAD
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
=======
Production TimescaleDB integration module.
Provides real database connections and session management for production deployment.
"""
import logging
import os
import asyncio
from typing import Any, Dict, Optional, AsyncContextManager
from contextlib import asynccontextmanager
import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Exception raised when database connection fails"""
    pass


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
            
        self.pool: Optional[Pool] = None
        logger.info("TimescaleDB connection manager initialized")
>>>>>>> compliance-violations-fixed
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.engine = None
        self.session_factory = None
        
    async def connect(self):
<<<<<<< HEAD
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
=======
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
            raise DatabaseConnectionError(f"TimescaleDB connection failed: {e}")
    
    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("TimescaleDB connection pool closed")


class ProductionSession:
    """Production TimescaleDB session with proper transaction management."""
    
    def __init__(self, connection):
        self.connection = connection
        self.transaction = None
        
    async def execute(self, query: str, *args):
        """Execute query with proper error handling."""
        try:
            if self.transaction:
                return await self.connection.execute(query, *args)
            else:
                return await self.connection.execute(query, *args)
        except Exception as e:
            logger.error(f"Database query failed: {query[:100]}... Error: {e}")
            raise DatabaseConnectionError(f"Query execution failed: {e}")
        
    async def fetch(self, query: str, *args):
        """Fetch query results with proper error handling."""
        try:
            if self.transaction:
                return await self.connection.fetch(query, *args)
            else:
                return await self.connection.fetch(query, *args)
        except Exception as e:
            logger.error(f"Database fetch failed: {query[:100]}... Error: {e}")
            raise DatabaseConnectionError(f"Query fetch failed: {e}")
        
    async def fetchval(self, query: str, *args):
        """Fetch single value with proper error handling."""
        try:
            if self.transaction:
                return await self.connection.fetchval(query, *args)
            else:
                return await self.connection.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Database fetchval failed: {query[:100]}... Error: {e}")
            raise DatabaseConnectionError(f"Query fetchval failed: {e}")
        
    async def begin(self):
        """Start transaction."""
        if not self.transaction:
            self.transaction = self.connection.transaction()
            await self.transaction.start()
        
    async def commit(self):
        """Commit transaction."""
        if self.transaction:
            await self.transaction.commit()
            self.transaction = None
        
    async def rollback(self):
        """Rollback transaction."""
        if self.transaction:
            await self.transaction.rollback()
            self.transaction = None
        
    async def close(self):
        """Close session (return connection to pool)."""
        if self.transaction:
            await self.rollback()
        # Connection is returned to pool automatically


# Global database instance
_db_instance = None


async def get_database() -> ProductionTimescaleDB:
    """Get or create database instance using config service settings."""
    global _db_instance
    if _db_instance is None:
        # Import settings to get DATABASE_URL from config service
        from app.core.config import settings
        if not hasattr(settings, 'DATABASE_URL') or not settings.DATABASE_URL:
            raise DatabaseConnectionError("DATABASE_URL not configured in settings from config service")
        
        _db_instance = ProductionTimescaleDB(database_url=settings.DATABASE_URL)
        await _db_instance.connect()
    return _db_instance


@asynccontextmanager
async def get_timescaledb_session() -> AsyncContextManager[ProductionSession]:
    """Get TimescaleDB session with proper connection management."""
    db = await get_database()
    
    if not db.pool:
        logger.error("Database pool not initialized")
        raise DatabaseConnectionError("Database connection pool not available")
        
    connection = await db.pool.acquire()
    session = ProductionSession(connection)
    
    try:
        yield session
    finally:
        await session.close()
        await db.pool.release(connection)


# Legacy synchronous database helpers removed - use async get_timescaledb_session() instead


# Connection pool management functions
async def create_timescaledb_pool(**kwargs):
    """Create TimescaleDB connection pool with custom parameters."""
    database_url = kwargs.get('database_url')
    if not database_url:
        raise DatabaseConnectionError("Database URL must be provided explicitly - no environment variable fallbacks allowed")
        
    try:
        pool = await asyncpg.create_pool(database_url, **kwargs)
        logger.info("Custom TimescaleDB connection pool created")
        return pool
    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        raise DatabaseConnectionError(f"Connection pool creation failed: {e}")


def get_database_url():
    """Get database URL from config service settings - no environment variable access."""
    raise DatabaseConnectionError("Direct environment variable access not allowed - use config service settings instead")
>>>>>>> compliance-violations-fixed
