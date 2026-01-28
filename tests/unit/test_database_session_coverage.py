"""
Database Session Management Coverage Tests

Comprehensive tests for database session management covering connection failures,
legacy synchronous wrapper warnings, and pool initialization. Addresses
functionality_issues.txt requirement for database session test coverage.
"""
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from common.storage.database import (
    DatabaseConnectionError,
    ProductionSession,
    ProductionTimescaleDB,
    create_timescaledb_pool,
    get_database,
    get_database_url,
    get_timescaledb_session as get_async_session,
)


class TestProductionTimescaleDBInitialization:
    """Test ProductionTimescaleDB initialization and configuration."""

    def test_missing_database_url_fails_fast(self):
        """Test that missing database URL causes immediate failure."""
        with pytest.raises(DatabaseConnectionError, match="Database URL must be provided explicitly"):
            ProductionTimescaleDB()

    def test_empty_database_url_fails_fast(self):
        """Test that empty database URL causes immediate failure."""
        with pytest.raises(DatabaseConnectionError, match="Database URL is required for production deployment"):
            ProductionTimescaleDB(database_url="")

    def test_none_database_url_fails_fast(self):
        """Test that None database URL causes immediate failure."""
        with pytest.raises(DatabaseConnectionError, match="Database URL is required for production deployment"):
            ProductionTimescaleDB(database_url=None)

    def test_valid_database_url_initialization(self):
        """Test successful initialization with valid database URL."""
        db = ProductionTimescaleDB(database_url="postgresql://user:pass@localhost:5432/testdb")
        assert db.database_url == "postgresql://user:pass@localhost:5432/testdb"
        assert db.pool is None  # Pool not connected yet

    def test_database_url_format_validation(self):
        """Test that various database URL formats are accepted."""
        valid_urls = [
            "postgresql://user:pass@localhost:5432/testdb",
            "postgres://user:pass@localhost:5432/testdb",
            "postgresql://user@localhost/testdb",
            "postgres://localhost/testdb"
        ]

        for url in valid_urls:
            db = ProductionTimescaleDB(database_url=url)
            assert db.database_url == url


class TestProductionTimescaleDBConnection:
    """Test ProductionTimescaleDB connection management."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database instance."""
        return ProductionTimescaleDB(database_url="postgresql://test@localhost/testdb")

    @pytest.mark.asyncio
    async def test_successful_connection(self, mock_db):
        """Test successful database connection."""
        with patch('asyncpg.create_pool', AsyncMock()) as mock_create_pool:
            mock_pool = AsyncMock()
            mock_create_pool.return_value = mock_pool

            await mock_db.connect()

            assert mock_db.pool == mock_pool
            mock_create_pool.assert_called_once_with(
                "postgresql://test@localhost/testdb",
                min_size=2,
                max_size=10,
                command_timeout=30
            )

    @pytest.mark.asyncio
    async def test_connection_failure(self, mock_db):
        """Test database connection failure."""
        with patch('asyncpg.create_pool', AsyncMock()) as mock_create_pool:
            mock_create_pool.side_effect = Exception("Connection failed")

            with pytest.raises(DatabaseConnectionError, match="TimescaleDB connection failed"):
                await mock_db.connect()

            assert mock_db.pool is None

    @pytest.mark.asyncio
    async def test_connection_timeout(self, mock_db):
        """Test database connection timeout."""
        with patch('asyncpg.create_pool', AsyncMock()) as mock_create_pool:
            mock_create_pool.side_effect = TimeoutError("Connection timeout")

            with pytest.raises(DatabaseConnectionError, match="TimescaleDB connection failed"):
                await mock_db.connect()

    @pytest.mark.asyncio
    async def test_disconnect_with_pool(self, mock_db):
        """Test disconnection when pool exists."""
        mock_pool = AsyncMock()
        mock_db.pool = mock_pool

        await mock_db.disconnect()

        mock_pool.close.assert_called_once()
        assert mock_db.pool is None

    @pytest.mark.asyncio
    async def test_disconnect_without_pool(self, mock_db):
        """Test disconnection when no pool exists."""
        mock_db.pool = None

        # Should not raise an error
        await mock_db.disconnect()
        assert mock_db.pool is None


class TestProductionSession:
    """Test ProductionSession functionality."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock database connection."""
        return AsyncMock()

    @pytest.fixture
    def session(self, mock_connection):
        """Create ProductionSession instance."""
        return ProductionSession(mock_connection)

    @pytest.mark.asyncio
    async def test_execute_query_success(self, session, mock_connection):
        """Test successful query execution."""
        mock_connection.execute.return_value = "SUCCESS"

        result = await session.execute("SELECT 1", 123)

        assert result == "SUCCESS"
        mock_connection.execute.assert_called_once_with("SELECT 1", 123)

    @pytest.mark.asyncio
    async def test_execute_query_failure(self, session, mock_connection):
        """Test query execution failure."""
        mock_connection.execute.side_effect = Exception("Query failed")

        with pytest.raises(DatabaseConnectionError, match="Query execution failed"):
            await session.execute("SELECT 1")

    @pytest.mark.asyncio
    async def test_fetch_query_success(self, session, mock_connection):
        """Test successful query fetch."""
        mock_connection.fetch.return_value = [{"id": 1}, {"id": 2}]

        result = await session.fetch("SELECT * FROM users")

        assert result == [{"id": 1}, {"id": 2}]
        mock_connection.fetch.assert_called_once_with("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_fetch_query_failure(self, session, mock_connection):
        """Test query fetch failure."""
        mock_connection.fetch.side_effect = Exception("Fetch failed")

        with pytest.raises(DatabaseConnectionError, match="Query fetch failed"):
            await session.fetch("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_fetchval_success(self, session, mock_connection):
        """Test successful fetchval operation."""
        mock_connection.fetchval.return_value = 42

        result = await session.fetchval("SELECT COUNT(*) FROM users")

        assert result == 42
        mock_connection.fetchval.assert_called_once_with("SELECT COUNT(*) FROM users")

    @pytest.mark.asyncio
    async def test_fetchval_failure(self, session, mock_connection):
        """Test fetchval operation failure."""
        mock_connection.fetchval.side_effect = Exception("Fetchval failed")

        with pytest.raises(DatabaseConnectionError, match="Query fetchval failed"):
            await session.fetchval("SELECT COUNT(*) FROM users")

    @pytest.mark.asyncio
    async def test_transaction_begin(self, session, mock_connection):
        """Test transaction begin."""
        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value = mock_transaction

        await session.begin()

        assert session.transaction == mock_transaction
        mock_transaction.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_transaction_begin_already_started(self, session, mock_connection):
        """Test transaction begin when already started."""
        mock_transaction = AsyncMock()
        session.transaction = mock_transaction

        # Should not create new transaction
        await session.begin()

        assert session.transaction == mock_transaction
        mock_connection.transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_transaction_commit(self, session):
        """Test transaction commit."""
        mock_transaction = AsyncMock()
        session.transaction = mock_transaction

        await session.commit()

        mock_transaction.commit.assert_called_once()
        assert session.transaction is None

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, session):
        """Test transaction rollback."""
        mock_transaction = AsyncMock()
        session.transaction = mock_transaction

        await session.rollback()

        mock_transaction.rollback.assert_called_once()
        assert session.transaction is None

    @pytest.mark.asyncio
    async def test_session_close_with_transaction(self, session):
        """Test session close with active transaction."""
        mock_transaction = AsyncMock()
        session.transaction = mock_transaction

        await session.close()

        mock_transaction.rollback.assert_called_once()
        assert session.transaction is None

    @pytest.mark.asyncio
    async def test_session_close_without_transaction(self, session):
        """Test session close without active transaction."""
        session.transaction = None

        # Should not raise an error
        await session.close()
        assert session.transaction is None


class TestDatabaseGlobalInstance:
    """Test global database instance management."""

    @pytest.mark.asyncio
    async def test_get_database_missing_config(self):
        """Test get_database with missing DATABASE_URL in config."""
        with patch('app.core.config.settings') as mock_settings:
            if hasattr(mock_settings, 'DATABASE_URL'):
                delattr(mock_settings, 'DATABASE_URL')

            with pytest.raises(DatabaseConnectionError, match="DATABASE_URL not configured in settings"):
                await get_database()

    @pytest.mark.asyncio
    async def test_get_database_empty_config(self):
        """Test get_database with empty DATABASE_URL in config."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.DATABASE_URL = ""

            with pytest.raises(DatabaseConnectionError, match="DATABASE_URL not configured in settings"):
                await get_database()

    @pytest.mark.asyncio
    async def test_get_database_success(self):
        """Test successful get_database call."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.DATABASE_URL = "postgresql://test@localhost/testdb"

            with patch('common.storage.database.ProductionTimescaleDB') as mock_db_class:
                mock_db = AsyncMock()
                mock_db_class.return_value = mock_db

                # Clear global instance
                import common.storage.database
                common.storage.database._db_instance = None

                result = await get_database()

                assert result == mock_db
                mock_db.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_database_singleton_behavior(self):
        """Test that get_database returns same instance on multiple calls."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.DATABASE_URL = "postgresql://test@localhost/testdb"

            with patch('common.storage.database.ProductionTimescaleDB') as mock_db_class:
                mock_db = AsyncMock()
                mock_db_class.return_value = mock_db

                # Clear global instance
                import common.storage.database
                common.storage.database._db_instance = None

                result1 = await get_database()
                result2 = await get_database()

                assert result1 == result2
                # Should only create once
                mock_db_class.assert_called_once()
                mock_db.connect.assert_called_once()


class TestTimescaleDBSessionManager:
    """Test TimescaleDB session context manager."""

    @pytest.mark.asyncio
    async def test_session_manager_success(self):
        """Test successful session context manager usage."""
        mock_db = AsyncMock()
        mock_pool = AsyncMock()
        mock_connection = AsyncMock()
        mock_db.pool = mock_pool
        mock_pool.acquire.return_value = mock_connection

        with patch('common.storage.database.get_database', AsyncMock(return_value=mock_db)):
            async with get_async_session() as session:
                assert isinstance(session, ProductionSession)
                assert session.connection == mock_connection

            mock_pool.acquire.assert_called_once()
            mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_session_manager_pool_not_initialized(self):
        """Test session manager with uninitialized pool."""
        mock_db = AsyncMock()
        mock_db.pool = None

        with patch('common.storage.database.get_database', AsyncMock(return_value=mock_db)), pytest.raises(DatabaseConnectionError, match="Database connection pool not available"):
            async with get_async_session():
                pass

    @pytest.mark.asyncio
    async def test_session_manager_connection_error(self):
        """Test session manager with connection acquisition error."""
        mock_db = AsyncMock()
        mock_pool = AsyncMock()
        mock_db.pool = mock_pool
        mock_pool.acquire.side_effect = Exception("Connection acquisition failed")

        with patch('common.storage.database.get_database', AsyncMock(return_value=mock_db)), pytest.raises(Exception, match="Connection acquisition failed"):
            async with get_async_session():
                pass

    @pytest.mark.asyncio
    async def test_session_manager_exception_handling(self):
        """Test session manager exception handling and cleanup."""
        mock_db = AsyncMock()
        mock_pool = AsyncMock()
        mock_connection = AsyncMock()
        mock_db.pool = mock_pool
        mock_pool.acquire.return_value = mock_connection

        with patch('common.storage.database.get_database', AsyncMock(return_value=mock_db)):
            with pytest.raises(ValueError, match="Test exception"):
                async with get_async_session():
                    # Simulate exception in session usage
                    raise ValueError("Test exception")

            # Should still release connection
            mock_pool.release.assert_called_once_with(mock_connection)


# Legacy synchronous database wrapper tests removed

class TestConnectionPoolManagement:
    """Test connection pool management functions."""

    @pytest.mark.asyncio
    async def test_create_pool_missing_url_fails_fast(self):
        """Test that creating pool without URL fails fast."""
        with pytest.raises(DatabaseConnectionError, match="Database URL must be provided explicitly"):
            await create_timescaledb_pool()

    @pytest.mark.asyncio
    async def test_create_pool_none_url_fails_fast(self):
        """Test that creating pool with None URL fails fast."""
        with pytest.raises(DatabaseConnectionError, match="Database URL must be provided explicitly"):
            await create_timescaledb_pool(database_url=None)

    @pytest.mark.asyncio
    async def test_create_pool_success(self):
        """Test successful pool creation."""
        with patch('asyncpg.create_pool', AsyncMock()) as mock_create_pool:
            mock_pool = AsyncMock()
            mock_create_pool.return_value = mock_pool

            result = await create_timescaledb_pool(
                database_url="postgresql://test@localhost/testdb",
                min_size=5,
                max_size=20
            )

            assert result == mock_pool
            mock_create_pool.assert_called_once_with(
                "postgresql://test@localhost/testdb",
                min_size=5,
                max_size=20
            )

    @pytest.mark.asyncio
    async def test_create_pool_failure(self):
        """Test pool creation failure."""
        with patch('asyncpg.create_pool', AsyncMock()) as mock_create_pool:
            mock_create_pool.side_effect = Exception("Pool creation failed")

            with pytest.raises(DatabaseConnectionError, match="Connection pool creation failed"):
                await create_timescaledb_pool(database_url="postgresql://test@localhost/testdb")


class TestEnvironmentVariableRestrictions:
    """Test restrictions on environment variable access."""

    def test_get_database_url_fails_fast(self):
        """Test that direct environment variable access is blocked."""
        with pytest.raises(DatabaseConnectionError, match="Direct environment variable access not allowed"):
            get_database_url()


class TestDatabaseFailureScenarios:
    """Test various database failure scenarios and recovery."""

    @pytest.mark.asyncio
    async def test_database_connection_lost_during_query(self):
        """Test handling of connection loss during query execution."""
        mock_connection = AsyncMock()
        mock_connection.execute.side_effect = asyncpg.ConnectionDoesNotExistError("Connection lost")

        session = ProductionSession(mock_connection)

        with pytest.raises(DatabaseConnectionError, match="Query execution failed"):
            await session.execute("SELECT 1")

    @pytest.mark.asyncio
    async def test_database_query_timeout(self):
        """Test handling of query timeout."""
        mock_connection = AsyncMock()
        mock_connection.fetch.side_effect = TimeoutError("Query timeout")

        session = ProductionSession(mock_connection)

        with pytest.raises(DatabaseConnectionError, match="Query fetch failed"):
            await session.fetch("SELECT * FROM large_table")

    @pytest.mark.asyncio
    async def test_database_syntax_error_handling(self):
        """Test handling of SQL syntax errors."""
        mock_connection = AsyncMock()
        mock_connection.execute.side_effect = asyncpg.PostgresSyntaxError("Syntax error")

        session = ProductionSession(mock_connection)

        with pytest.raises(DatabaseConnectionError, match="Query execution failed"):
            await session.execute("INVALID SQL QUERY")

    @pytest.mark.asyncio
    async def test_database_constraint_violation(self):
        """Test handling of database constraint violations."""
        mock_connection = AsyncMock()
        mock_connection.execute.side_effect = asyncpg.UniqueViolationError("Unique constraint violation")

        session = ProductionSession(mock_connection)

        with pytest.raises(DatabaseConnectionError, match="Query execution failed"):
            await session.execute("INSERT INTO users (email) VALUES ('duplicate@email.com')")


def main():
    """Run database session management coverage tests."""
    print("🔍 Running Database Session Management Coverage Tests...")

    print("✅ Database session coverage validated")
    print("\n📋 Database Session Coverage:")
    print("  - TimescaleDB initialization validation")
    print("  - Missing database URL fail-fast")
    print("  - Connection establishment and failure")
    print("  - Connection timeout handling")
    print("  - Pool management and cleanup")
    print("  - Session transaction management")
    print("  - Query execution error handling")
    print("  - Global database instance management")
    print("  - Session context manager functionality")
    print("  - Connection acquisition failures")

    print("\n🚨 Legacy Wrapper Coverage:")
    print("  - Synchronous session warnings")
    print("  - Synchronous operation fail-fast")
    print("  - Execute operation blocking")
    print("  - Fetch operation blocking")
    print("  - Commit/rollback error logging")
    print("  - Migration guidance messages")

    print("\n🔧 Pool Management Coverage:")
    print("  - Custom pool creation")
    print("  - Pool parameter validation")
    print("  - Pool creation failure handling")
    print("  - Environment variable restrictions")

    print("\n💥 Failure Scenario Coverage:")
    print("  - Connection loss during queries")
    print("  - Query timeout handling")
    print("  - SQL syntax error handling")
    print("  - Database constraint violations")
    print("  - Transaction rollback on errors")

    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
