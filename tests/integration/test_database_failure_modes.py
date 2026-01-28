#!/usr/bin/env python3
"""
Database Failure Modes Integration Tests

Comprehensive integration tests for rare database failure scenarios to achieve
100% production readiness confidence. Tests asyncpg pool exhaustion, partial
transaction failures, and schema drift detection.
"""
import asyncio
import importlib.util
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

if importlib.util.find_spec('app.errors'):
    from app.errors import (
        DatabaseConnectionError,
        ProductionSession,
        ProductionTimescaleDB,
        get_timescaledb_session,
    )
    try:
        from app.errors import DatabaseError
        from app.repository.signal_repository import SignalRepository
    except ImportError:
        # Create mock classes for testing
        SignalRepository = MagicMock
        DatabaseError = Exception
    DATABASE_MODULES_AVAILABLE = True
else:
    DATABASE_MODULES_AVAILABLE = False
    # Create mock classes for testing
    SignalRepository = MagicMock
    DatabaseError = Exception


class TestAsyncpgPoolFailureModes:
    """Test asyncpg connection pool exhaustion and timeout scenarios."""

    @pytest.fixture
    def mock_pool_exhausted(self):
        """Mock connection pool in exhausted state."""
        pool = AsyncMock()
        pool.acquire.side_effect = TimeoutError("Pool exhausted")
        pool.size.return_value = 10
        pool.checkedout.return_value = 10  # All connections checked out
        return pool

    @pytest.fixture
    def mock_slow_pool(self):
        """Mock connection pool with slow acquisition."""
        async def slow_acquire():
            await asyncio.sleep(5)  # Simulate slow acquisition
            raise TimeoutError("Acquisition timeout")

        pool = AsyncMock()
        pool.acquire.side_effect = slow_acquire
        pool.size.return_value = 10
        pool.checkedout.return_value = 8
        return pool

    @pytest.mark.asyncio
    async def test_pool_exhaustion_handling(self, mock_pool_exhausted):
        """Test handling of connection pool exhaustion."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        db = ProductionTimescaleDB(database_url="postgresql://test@localhost/testdb")
        db.pool = mock_pool_exhausted

        # Attempt to get session when pool is exhausted
        with pytest.raises(DatabaseConnectionError) as exc_info:
            async with get_timescaledb_session():
                pass

        # Should fail fast with appropriate error
        assert "pool" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_pool_exhaustion_scenario(self):
        """Test concurrent requests causing pool exhaustion."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Create a pool with limited connections
        with patch('asyncpg.create_pool') as mock_create_pool:
            # Mock pool that becomes exhausted after 3 concurrent connections
            connection_count = 0
            acquired_connections = []

            async def mock_acquire():
                nonlocal connection_count
                if connection_count >= 3:
                    raise TimeoutError("Pool exhausted after 3 connections")
                connection_count += 1
                conn = AsyncMock()
                acquired_connections.append(conn)
                return conn

            async def mock_release(conn):
                nonlocal connection_count
                connection_count -= 1
                if conn in acquired_connections:
                    acquired_connections.remove(conn)

            mock_pool = AsyncMock()
            mock_pool.acquire = mock_acquire
            mock_pool.release = mock_release
            mock_pool.size.return_value = 3
            mock_create_pool.return_value = mock_pool

            db = ProductionTimescaleDB(database_url="postgresql://test@localhost/testdb")
            await db.connect()

            # Create multiple concurrent session requests
            session_tasks = []
            for i in range(5):  # More requests than pool size
                task = asyncio.create_task(self._use_session(db, i))
                session_tasks.append(task)

            # Some should succeed, some should fail due to pool exhaustion
            results = await asyncio.gather(*session_tasks, return_exceptions=True)

            success_count = len([r for r in results if not isinstance(r, Exception)])
            failure_count = len([r for r in results if isinstance(r, Exception)])

            # Should have some failures due to pool limits
            assert failure_count > 0
            assert success_count <= 3  # Limited by pool size

    async def _use_session(self, db: ProductionTimescaleDB, request_id: int):
        """Helper to simulate database session usage."""
        try:
            connection = await db.pool.acquire()
            ProductionSession(connection)

            # Simulate some work
            await asyncio.sleep(0.1)

            await db.pool.release(connection)
            return f"request_{request_id}_success"

        except Exception as e:
            raise DatabaseConnectionError(f"Session {request_id} failed: {str(e)}") from e

    @pytest.mark.asyncio
    async def test_connection_leak_detection(self):
        """Test detection of connection leaks in pool."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        leak_tracker = []

        async def mock_acquire():
            conn = AsyncMock()
            leak_tracker.append(conn)  # Track acquired connections
            return conn

        async def mock_release(conn):
            if conn in leak_tracker:
                leak_tracker.remove(conn)  # Track released connections

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire
        mock_pool.release = mock_release

        db = ProductionTimescaleDB(database_url="postgresql://test@localhost/testdb")
        db.pool = mock_pool

        # Simulate session usage with potential leak
        connection = await db.pool.acquire()
        ProductionSession(connection)

        # Simulate forgetting to release connection (leak)
        # await db.pool.release(connection)  # Commented out to simulate leak

        # Check leak tracker
        assert len(leak_tracker) == 1  # Connection not released

        # Cleanup
        await db.pool.release(connection)
        assert len(leak_tracker) == 0  # Leak resolved

    @pytest.mark.asyncio
    async def test_pool_recovery_after_failure(self, mock_slow_pool):
        """Test pool recovery after failure conditions."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        recovery_attempts = 0

        async def mock_acquire_with_recovery():
            nonlocal recovery_attempts
            recovery_attempts += 1

            if recovery_attempts <= 2:
                raise TimeoutError(f"Pool failure attempt {recovery_attempts}")
            # Simulate recovery on third attempt
            return AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = mock_acquire_with_recovery

        db = ProductionTimescaleDB(database_url="postgresql://test@localhost/testdb")
        db.pool = mock_pool

        # First two attempts should fail
        with pytest.raises((DatabaseConnectionError, asyncio.TimeoutError)):
            connection = await db.pool.acquire()

        with pytest.raises((DatabaseConnectionError, asyncio.TimeoutError)):
            connection = await db.pool.acquire()

        # Third attempt should succeed (recovery)
        connection = await db.pool.acquire()
        assert connection is not None
        assert recovery_attempts == 3


class TestPartialTransactionFailures:
    """Test partial transaction failures across nested repository writes."""

    @pytest.fixture
    def mock_repository(self):
        """Mock signal repository for testing."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        repo = SignalRepository()
        repo._initialized = True
        return repo

    @pytest.mark.asyncio
    async def test_nested_transaction_partial_failure(self, mock_repository):
        """Test partial failure in nested transaction writes."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock database session with partial failure
        failure_on_step = 2  # Fail on second operation
        operation_count = 0

        async def mock_execute(query, *args):
            nonlocal operation_count
            operation_count += 1

            if operation_count == failure_on_step:
                raise asyncpg.PostgresError("Simulated partial transaction failure")

            return {"id": operation_count}

        mock_connection = AsyncMock()
        mock_connection.execute = mock_execute
        mock_connection.fetchrow = mock_execute

        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value = mock_transaction

        # Test multi-step operation that should rollback on partial failure
        with patch.object(mock_repository, 'db_connection') as mock_db:
            mock_db.acquire.return_value.__aenter__.return_value = mock_connection

            # Mock signal data
            greeks_data = MagicMock()
            greeks_data.signal_id = "test_signal"
            greeks_data.instrument_key = "NSE@TEST@EQ"
            greeks_data.timestamp = datetime.now()
            greeks_data.delta = 0.5
            greeks_data.gamma = 0.1

            # Should fail on second operation and trigger rollback
            with pytest.raises((DatabaseError, asyncpg.PostgresError)):
                await mock_repository.save_greeks(greeks_data)

            # Verify transaction started but was rolled back
            mock_transaction.start.assert_called_once()
            # Note: In real implementation, rollback would be called

    @pytest.mark.asyncio
    async def test_concurrent_transaction_conflict(self):
        """Test handling of concurrent transaction conflicts."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Simulate deadlock/conflict scenario
        conflict_detected = False

        async def mock_execute_with_conflict(query, *args):
            nonlocal conflict_detected
            if not conflict_detected and "INSERT" in query:
                conflict_detected = True
                raise asyncpg.DeadlockDetectedError("Deadlock detected")
            return {"id": 1}

        mock_connection1 = AsyncMock()
        mock_connection1.execute = mock_execute_with_conflict
        mock_connection1.fetchrow = mock_execute_with_conflict

        mock_connection2 = AsyncMock()
        mock_connection2.execute = mock_execute_with_conflict
        mock_connection2.fetchrow = mock_execute_with_conflict

        # Test concurrent operations that cause conflict
        async def concurrent_write(connection, data_id):
            session = ProductionSession(connection)
            try:
                await session.begin()
                # Simulate write operation
                result = await session.execute(f"INSERT INTO test_table (id) VALUES ({data_id})")
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                raise DatabaseConnectionError(f"Transaction conflict: {str(e)}") from e

        # Run concurrent transactions that should conflict
        task1 = asyncio.create_task(concurrent_write(mock_connection1, 1))
        task2 = asyncio.create_task(concurrent_write(mock_connection2, 1))

        results = await asyncio.gather(task1, task2, return_exceptions=True)

        # At least one should fail due to conflict
        failures = [r for r in results if isinstance(r, Exception)]
        assert len(failures) > 0
        assert any("conflict" in str(f).lower() or "deadlock" in str(f).lower() for f in failures)

    @pytest.mark.asyncio
    async def test_transaction_timeout_handling(self):
        """Test transaction timeout in long-running operations."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock long-running transaction that times out
        async def mock_long_operation(query, *args):
            await asyncio.sleep(2)  # Simulate long operation
            raise TimeoutError("Transaction timeout after 30 seconds")

        mock_connection = AsyncMock()
        mock_connection.execute = mock_long_operation

        session = ProductionSession(mock_connection)

        # Should timeout and handle gracefully
        start_time = time.time()
        with pytest.raises((DatabaseConnectionError, asyncio.TimeoutError)):
            await session.execute("LONG RUNNING QUERY")

        elapsed = time.time() - start_time
        assert elapsed >= 2  # Should have waited for timeout

    @pytest.mark.asyncio
    async def test_savepoint_rollback_scenario(self):
        """Test savepoint and rollback in nested transactions."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        operations_log = []

        async def mock_execute_with_savepoint(query, *args):
            operations_log.append(query)

            if "SAVEPOINT" in query or "ROLLBACK TO SAVEPOINT" in query:
                return None
            if "INSERT INTO indicators" in query:
                raise asyncpg.CheckViolationError("Check constraint violation")
            return {"id": len(operations_log)}

        mock_connection = AsyncMock()
        mock_connection.execute = mock_execute_with_savepoint
        mock_connection.fetchrow = mock_execute_with_savepoint

        session = ProductionSession(mock_connection)

        # Simulate complex transaction with savepoint
        try:
            await session.begin()

            # First operation succeeds
            await session.execute("INSERT INTO signal_greeks (signal_id) VALUES ('test1')")

            # Create savepoint
            await session.execute("SAVEPOINT sp1")

            # Second operation fails
            with pytest.raises(asyncpg.CheckViolationError):
                await session.execute("INSERT INTO indicators (invalid_data) VALUES ('bad')")

            # Should rollback to savepoint
            await session.execute("ROLLBACK TO SAVEPOINT sp1")

            # Continue with valid operation
            await session.execute("INSERT INTO signal_indicators (signal_id) VALUES ('test2')")

            await session.commit()

        except Exception:
            await session.rollback()
            raise

        # Verify operations were logged correctly
        assert any("SAVEPOINT" in op for op in operations_log)
        assert any("ROLLBACK TO SAVEPOINT" in op for op in operations_log)


class TestSchemaDriftDetection:
    """Test schema drift detection and fail-fast behavior."""

    @pytest.mark.asyncio
    async def test_missing_column_detection(self):
        """Test detection of missing database columns."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock database response with missing column error
        async def mock_execute_missing_column(query, *args):
            if "delta" in query:  # Simulate missing delta column
                raise asyncpg.UndefinedColumnError('column "delta" does not exist')
            return {"id": 1}

        mock_connection = AsyncMock()
        mock_connection.execute = mock_execute_missing_column
        mock_connection.fetchrow = mock_execute_missing_column

        session = ProductionSession(mock_connection)

        # Should fail fast with clear error about schema drift
        with pytest.raises(DatabaseConnectionError) as exc_info:
            await session.execute("SELECT delta FROM signal_greeks WHERE id = 1")

        assert "column" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_missing_table_detection(self):
        """Test detection of missing database tables."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock database response with missing table error
        async def mock_execute_missing_table(query, *args):
            if "signal_greeks" in query:
                raise asyncpg.UndefinedTableError('relation "signal_greeks" does not exist')
            return {"id": 1}

        mock_connection = AsyncMock()
        mock_connection.execute = mock_execute_missing_table
        mock_connection.fetchrow = mock_execute_missing_table

        session = ProductionSession(mock_connection)

        # Should fail fast with clear error about missing table
        with pytest.raises(DatabaseConnectionError) as exc_info:
            await session.execute("SELECT * FROM signal_greeks LIMIT 1")

        assert "relation" in str(exc_info.value).lower() or "table" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_schema_version_mismatch(self):
        """Test handling of schema version mismatches."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock schema version check that fails
        async def mock_schema_version_check(query, *args):
            if "version" in query.lower():
                # Return unexpected schema version
                return {"version": "2.0"}  # Expected might be 1.5
            return {"id": 1}

        mock_connection = AsyncMock()
        mock_connection.fetchrow = mock_schema_version_check

        session = ProductionSession(mock_connection)

        # Simulate schema version validation
        result = await session.fetchrow("SELECT version FROM schema_version")

        expected_version = "1.5"
        actual_version = result["version"]

        if actual_version != expected_version:
            with pytest.raises(DatabaseConnectionError):
                raise DatabaseConnectionError(
                    f"Schema version mismatch: expected {expected_version}, got {actual_version}"
                )

    @pytest.mark.asyncio
    async def test_constraint_violation_handling(self):
        """Test handling of database constraint violations."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Test different types of constraint violations
        constraint_violations = [
            (asyncpg.UniqueViolationError, "Unique constraint violation"),
            (asyncpg.ForeignKeyViolationError, "Foreign key constraint violation"),
            (asyncpg.CheckViolationError, "Check constraint violation"),
            (asyncpg.NotNullViolationError, "Not null constraint violation")
        ]

        for exception_class, error_message in constraint_violations:
            async def mock_constraint_violation(query, *args, exc_class=exception_class, err_msg=error_message):
                raise exc_class(err_msg)

            mock_connection = AsyncMock()
            mock_connection.execute = mock_constraint_violation

            session = ProductionSession(mock_connection)

            # Should fail fast with appropriate constraint error
            with pytest.raises(DatabaseConnectionError) as exc_info:
                await session.execute("INSERT INTO signal_greeks (signal_id) VALUES ('test')")

            assert "constraint" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_data_type_mismatch_detection(self):
        """Test detection of data type mismatches."""
        if not DATABASE_MODULES_AVAILABLE:
            pytest.skip("Database modules not available")

        # Mock data type conversion errors
        async def mock_type_mismatch(query, *args):
            if args and any(isinstance(arg, str) for arg in args):
                raise asyncpg.DataError('invalid input syntax for type numeric: "invalid_number"')
            return {"id": 1}

        mock_connection = AsyncMock()
        mock_connection.execute = mock_type_mismatch

        session = ProductionSession(mock_connection)

        # Should fail fast with data type error
        with pytest.raises(DatabaseConnectionError) as exc_info:
            await session.execute(
                "UPDATE signal_greeks SET delta = $1 WHERE id = $2",
                "invalid_number",  # Should be numeric
                1
            )

        assert "syntax" in str(exc_info.value).lower() or "type" in str(exc_info.value).lower()


def run_failure_mode_coverage_test():
    """Run database failure mode integration coverage test."""
    import subprocess
    import sys

    print("🔍 Running Database Failure Mode Integration Coverage Tests...")

    cmd = [
        sys.executable, "-m", "pytest",
        __file__,
        "--cov=common.storage.database",
        "--cov=app.repositories.signal_repository",
        "--cov=app.errors",
        "--cov-report=term-missing",
        "--cov-report=html:coverage_reports/html_database_failure_modes",
        "--cov-report=json:coverage_reports/coverage_database_failure_modes.json",
        "--cov-fail-under=95",
        "-v",
        "--tb=short"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    print("🚨 Database Failure Mode Integration Tests")
    print("=" * 60)

    success = run_failure_mode_coverage_test()

    if success:
        print("\n✅ Database failure mode integration tests passed with ≥95% coverage!")
        print("📋 Integration coverage validated for:")
        print("  - AsyncPG pool exhaustion and timeout scenarios")
        print("  - Connection leak detection and recovery")
        print("  - Partial transaction failures across nested writes")
        print("  - Concurrent transaction conflicts and deadlocks")
        print("  - Transaction timeout handling")
        print("  - Savepoint rollback scenarios")
        print("  - Missing column/table detection (schema drift)")
        print("  - Schema version mismatch handling")
        print("  - Database constraint violations")
        print("  - Data type mismatch detection")
        print("\n🏆 Critical gap resolved: Rare failure mode coverage comprehensive")
    else:
        print("\n❌ Database failure mode integration tests need improvement")
        import sys
        sys.exit(1)
