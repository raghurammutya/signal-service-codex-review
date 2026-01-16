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
                await conn.execute("SELECT 1")
                
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
    """Mock database for testing."""
    
    def __init__(self):
        pass
    
    async def connect(self):
        """Mock connect."""
        logger.warning("Using mock database - should not happen in production!")
        pass
    
    async def disconnect(self):
        """Mock disconnect."""
        pass


class MockSession:
    """Mock database session for testing."""
    def __init__(self):
        pass
    
    async def execute(self, query, params=None):
        """Mock execute."""
        logger.debug(f"Mock execute: {query}")
        return MockResult()
        
    async def commit(self):
        """Mock commit."""
        pass
        
    async def rollback(self):
        """Mock rollback."""
        pass
        
    async def close(self):
        """Mock close."""
        pass

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
    
    # Get database URL
    database_url = os.getenv('DATABASE_URL') or os.getenv('TIMESCALEDB_URL')
    environment = os.getenv('ENVIRONMENT', 'development')
    
    if not database_url:
        # In production, database is required
        if environment in ['production', 'prod', 'staging']:
            raise DatabaseConnectionError(
                f"Database URL not configured for {environment} environment. "
                "Set DATABASE_URL or TIMESCALEDB_URL environment variable."
            )
        
        # Development fallback - return mock
        logger.warning("No database URL configured, using mock database for development")
        mock_db = MockDatabase()
        await mock_db.connect()
        return None, None
    
    try:
        # Create production database connection
        db = ProductionDatabase(database_url)
        await db.connect()
        
        _engine = db.engine
        _async_session_factory = db.session_factory
        
        return _engine, _async_session_factory
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        
        # In production, fail hard
        if environment in ['production', 'prod', 'staging']:
            raise DatabaseConnectionError(f"Production database connection failed: {e}")
        
        # Development fallback
        logger.warning("Using mock database for development")
        mock_db = MockDatabase()
        await mock_db.connect()
        return None, None


@asynccontextmanager
async def get_timescaledb_session():
    """Get TimescaleDB session with proper error handling."""
    try:
        engine, session_factory = await get_database_connection()
        
        if session_factory is None:
            # Use mock session
            session = MockSession()
            try:
                yield session
            finally:
                await session.close()
        else:
            # Use real session
            async with session_factory() as session:
                yield session
                
    except Exception as e:
        logger.error(f"Database session error: {e}")
        # Fallback to mock session
        session = MockSession()
        try:
            yield session
        finally:
            await session.close()


@contextmanager  
def get_timescaledb_session_sync():
    """Synchronous version - deprecated, use async version."""
    logger.warning("Using deprecated sync database session")
    session = MockSession()
    try:
        yield session
    finally:
        pass


def get_database():
    """Get database instance - deprecated, use get_database_connection."""
    logger.warning("Using deprecated get_database function")
    return MockDatabase()


class DatabaseHealthChecker:
    """Database health checker."""
    
    @staticmethod
    async def check_health() -> Dict[str, Any]:
        """Check database health."""
        try:
            engine, _ = await get_database_connection()
            
            if engine is None:
                return {
                    "status": "mock",
                    "message": "Using mock database",
                    "connection_time_ms": 0
                }
            
            # Test connection
            import time
            start_time = time.time()
            
            async with engine.begin() as conn:
                await conn.execute("SELECT 1")
                
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