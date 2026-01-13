"""Test that all critical architectural fixes are properly implemented."""
import pytest
import ast
import os
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock

class TestCriticalFixesCompliance:
    """Test critical architectural fixes compliance."""
    
    def test_no_ticker_service_v2_references(self):
        """Ensure no ticker_service_v2 references exist in codebase."""
        app_dir = Path("app")
        if not app_dir.exists():
            pytest.skip("App directory not found")
            
        python_files = list(app_dir.rglob("*.py"))
        
        violations = []
        for file_path in python_files:
            try:
                content = file_path.read_text()
                if "ticker_service_v2" in content:
                    violations.append(str(file_path))
            except (UnicodeDecodeError, PermissionError):
                continue  # Skip binary or protected files
        
        assert not violations, f"ticker_service_v2 references found in: {violations}"
    
    def test_no_hardcoded_nifty_references(self):
        """Ensure no hardcoded NIFTY references in production code."""
        app_dir = Path("app")
        if not app_dir.exists():
            pytest.skip("App directory not found")
            
        python_files = list(app_dir.rglob("*.py"))
        
        violations = []
        for file_path in python_files:
            # Skip test files
            if "test" in str(file_path):
                continue
                
            try:
                content = file_path.read_text()
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    # Skip comments and docstrings
                    line_stripped = line.strip()
                    if line_stripped.startswith('#') or '"""' in line_stripped or "'''" in line_stripped:
                        continue
                        
                    if 'NIFTY' in line and not line.strip().startswith('#'):
                        violations.append(f"{file_path}:{i}")
            except (UnicodeDecodeError, PermissionError):
                continue
        
        assert not violations, f"Hardcoded NIFTY references found: {violations}"
    
    @pytest.mark.asyncio
    async def test_silent_fallback_elimination_signal_repository(self):
        """Test that signal repository raises exceptions instead of returning None."""
        from app.repositories.signal_repository import SignalRepository, DatabaseError
        
        repo = SignalRepository()
        
        # Mock database connection failure
        with patch.object(repo, 'db_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_conn.fetchrow.side_effect = Exception("Database connection failed")
            mock_db.acquire.return_value.__aenter__.return_value = mock_conn
            mock_db.acquire.return_value.__aexit__.return_value = None
            
            # Should raise DatabaseError, not return None
            with pytest.raises(DatabaseError):
                await repo.get_latest_greeks("test_instrument")
    
    @pytest.mark.asyncio
    async def test_silent_fallback_elimination_instrument_client(self):
        """Test that instrument service client raises exceptions instead of silent failures."""
        from app.services.instrument_service_client import InstrumentServiceClient, ServiceUnavailableError
        
        client = InstrumentServiceClient()
        
        # Test service unavailable scenario
        with patch.object(client, '_service_available', False):
            with pytest.raises(ServiceUnavailableError):
                await client.get_instrument("test_instrument")
    
    def test_proper_exception_hierarchy(self):
        """Test that all custom exceptions inherit properly."""
        from app.errors import (
            SignalServiceError, CommsServiceError, DatabaseQueryError,
            WorkerRegistryError, TimeframeAggregationError, 
            CacheConnectionError, ConsumerError
        )
        
        # Test inheritance
        assert issubclass(CommsServiceError, SignalServiceError)
        assert issubclass(DatabaseQueryError, SignalServiceError)
        assert issubclass(WorkerRegistryError, SignalServiceError)
        assert issubclass(TimeframeAggregationError, SignalServiceError)
        assert issubclass(CacheConnectionError, SignalServiceError)
        assert issubclass(ConsumerError, SignalServiceError)
        
        # Test exception initialization
        error = CommsServiceError("Test error", status_code=500)
        assert str(error) == "Test error"
        assert error.status_code == 500
    
    def test_config_service_url_consistency(self):
        """Test that config uses ticker_service not ticker_service_v2."""
        from app.core.config import settings
        
        # Verify TICKER_SERVICE_URL doesn't contain v2
        ticker_url = str(settings.TICKER_SERVICE_URL)
        assert "ticker_service_v2" not in ticker_url.lower()
        
        # Should contain ticker_service or ticker-service  
        assert any(variant in ticker_url.lower() for variant in ["ticker_service", "ticker-service"])

class TestSmartMoneyRealImplementations:
    """Test that Smart Money indicators use real implementations, not mocks."""
    
    def test_break_of_structure_real_implementation(self, sample_market_data):
        """Test that Break of Structure uses real algorithmic implementation."""
        from app.services.smart_money_indicators import SmartMoneyIndicators
        
        indicators = SmartMoneyIndicators()
        
        # Test with real market data
        bos_signals = indicators.calculate_break_of_structure(sample_market_data)
        
        # Should return pandas Series with boolean or object dtype
        assert hasattr(bos_signals, 'dtype'), "BOS should return pandas Series"
        
        # Should not be all the same value (mock behavior)
        unique_values = bos_signals.nunique() if hasattr(bos_signals, 'nunique') else len(set(bos_signals))
        assert unique_values > 1, "BOS implementation should not return uniform mock data"
    
    def test_order_blocks_real_implementation(self, sample_market_data):
        """Test that Order Blocks identification uses real volume confirmation."""
        from app.services.smart_money_indicators import SmartMoneyIndicators
        
        indicators = SmartMoneyIndicators()
        
        order_blocks = indicators.identify_order_blocks(sample_market_data)
        
        # Should return DataFrame with specific columns
        expected_columns = ['level', 'strength', 'volume_confirmation']
        for col in expected_columns:
            assert col in order_blocks.columns, f"Order blocks should include {col} column"
        
        # Volume confirmation should be boolean
        if len(order_blocks) > 0:
            assert order_blocks['volume_confirmation'].dtype == bool
    
    def test_fair_value_gaps_real_implementation(self, sample_market_data):
        """Test that Fair Value Gaps detection uses real price action analysis."""
        from app.services.smart_money_indicators import SmartMoneyIndicators
        
        indicators = SmartMoneyIndicators()
        
        fvg_zones = indicators.detect_fair_value_gaps(sample_market_data)
        
        # Should return DataFrame with gap information
        expected_columns = ['gap_start', 'gap_end', 'gap_type']
        for col in expected_columns:
            assert col in fvg_zones.columns, f"FVG should include {col} column"
        
        # Gap types should be valid
        if len(fvg_zones) > 0:
            valid_types = ['bullish', 'bearish']
            assert all(gap_type in valid_types for gap_type in fvg_zones['gap_type'])

class TestSandboxSecurity:
    """Test that sandbox implementation provides real security isolation."""
    
    def test_sandbox_import_restrictions(self):
        """Test that sandbox restricts dangerous imports."""
        try:
            from app.security.sandbox_enhancements import EnhancedSandbox
            
            sandbox = EnhancedSandbox()
            
            # Test that dangerous imports are blocked
            dangerous_script = "import os; os.system('echo test')"
            
            with pytest.raises(Exception):  # Should raise security exception
                sandbox.execute_code(dangerous_script)
        except ImportError:
            pytest.skip("Sandbox implementation not available")
    
    def test_sandbox_resource_limits(self):
        """Test that sandbox enforces resource limits."""
        try:
            from app.security.sandbox_enhancements import EnhancedSandbox
            
            sandbox = EnhancedSandbox()
            
            # Test memory limit enforcement
            memory_heavy_script = """
data = []
for i in range(1000000):
    data.append('x' * 1000)
"""
            
            with pytest.raises(Exception):  # Should raise resource limit exception
                sandbox.execute_code(memory_heavy_script, memory_limit_mb=10)
        except ImportError:
            pytest.skip("Sandbox implementation not available")