"""
Production database module - requires actual TimescaleDB integration.
Mock implementations removed to enforce proper database deployment.
"""
from typing import Any, Dict, Optional
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseIntegrationError(Exception):
    """Exception raised when database integration is required but not available"""
    pass


class ProductionDatabaseRequired:
    """Enforces production database integration requirement."""
    
    def __init__(self):
        raise DatabaseIntegrationError(
            "Production TimescaleDB integration required - cannot use mock database"
        )
    
    async def connect(self):
        """Database connection requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            "TimescaleDB connection required - cannot use mock implementation"
        )
    
    async def disconnect(self):
        """Database disconnection requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            "TimescaleDB disconnection requires actual database connection"
        )


class ProductionSessionRequired:
    """Enforces production database session requirement."""
    
    def __init__(self):
        raise DatabaseIntegrationError(
            "Production TimescaleDB session required - cannot use mock session"
        )
    
    def execute(self, query):
        """Query execution requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            f"TimescaleDB integration required to execute query: {query}"
        )
        
    def commit(self):
        """Transaction commit requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            "TimescaleDB integration required for transaction commit"
        )
        
    def rollback(self):
        """Transaction rollback requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            "TimescaleDB integration required for transaction rollback"
        )
        
    def close(self):
        """Session close requires TimescaleDB integration."""
        raise DatabaseIntegrationError(
            "TimescaleDB integration required to close session"
        )


@contextmanager
def get_timescaledb_session():
    """Get TimescaleDB session - requires production database integration."""
    logger.error("TimescaleDB session requested but no production database available")
    raise DatabaseIntegrationError(
        "Production TimescaleDB integration required - cannot provide mock database session"
    )


# Async version for compatibility
async def get_async_timescaledb_session():
    """Get async TimescaleDB session - requires production database integration."""
    logger.error("Async TimescaleDB session requested but no production database available")
    raise DatabaseIntegrationError(
        "Production TimescaleDB async integration required - cannot provide mock database session"
    )


# Connection pool functions require production implementation
def create_timescaledb_pool(**kwargs):
    """Create TimescaleDB connection pool - requires production integration."""
    raise DatabaseIntegrationError(
        "TimescaleDB connection pool requires production database integration"
    )


def get_database_url():
    """Get database URL - requires config service integration."""
    raise DatabaseIntegrationError(
        "Database URL requires config service integration - cannot provide mock URL"
    )