"""
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


# Synchronous context manager for backwards compatibility
class SyncDatabaseSession:
    """Synchronous wrapper for database session."""
    
    def __init__(self):
        self.async_session = None
        
    def __enter__(self):
        # Synchronous database operations not supported in production - fail fast
        logger.error("Synchronous database session usage not supported - must use async get_timescaledb_session")
        raise DatabaseConnectionError("Synchronous database operations are deprecated and not supported - use async get_timescaledb_session instead")
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        
    def execute(self, query: str, *args):
        """Execute query - requires async context."""
        logger.error("Synchronous execute called - use async get_timescaledb_session instead")
        raise DatabaseConnectionError("Synchronous database operations not supported - use async session")
        
    def fetch(self, query: str, *args):
        """Fetch query - requires async context."""
        logger.error("Synchronous fetch called - use async get_timescaledb_session instead")
        raise DatabaseConnectionError("Synchronous database operations not supported - use async session")
        
    def commit(self):
        """Commit transaction - requires async context."""
        logger.error("Synchronous commit called - use async session")
        pass
        
    def rollback(self):
        """Rollback transaction - requires async context."""
        logger.error("Synchronous rollback called - use async session")
        pass
        
    def close(self):
        """Close session - requires async context."""
        pass


def get_timescaledb_session():
    """Get synchronous database session (deprecated) - fails fast in production."""
    logger.error("Synchronous database session requested - not supported, use async get_timescaledb_session")
    raise DatabaseConnectionError("Synchronous database sessions are deprecated and not supported - use async get_timescaledb_session instead")


# Async version for new code
async def get_async_timescaledb_session():
    """Get async TimescaleDB session - preferred method."""
    return get_timescaledb_session()


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