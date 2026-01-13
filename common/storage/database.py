"""
Mock storage database module for testing
"""
from typing import Any, Dict, Optional
from contextlib import contextmanager

class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        pass
    
    async def connect(self):
        """Mock connect."""
        pass
    
    async def disconnect(self):
        """Mock disconnect."""
        pass


class MockSession:
    """Mock database session for testing."""
    def __init__(self):
        pass
    
    def execute(self, query):
        """Mock execute."""
        return []
        
    def commit(self):
        """Mock commit."""
        pass
        
    def rollback(self):
        """Mock rollback."""
        pass
        
    def close(self):
        """Mock close."""
        pass

@contextmanager
def get_timescaledb_session():
    """Mock get timescaledb session for testing."""
    session = MockSession()
    try:
        yield session
    finally:
        session.close()

def get_database():
    """Get mock database for testing.""" 
    return MockDatabase()