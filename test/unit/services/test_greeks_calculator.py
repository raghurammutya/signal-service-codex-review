"""Comprehensive unit tests for Greeks calculator."""

import pytest

from app.errors import GreeksCalculationError
from app.services.greeks_calculator import GreeksCalculator


class TestGreeksCalculator:
    """Comprehensive unit tests for Greeks calculator."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance for testing."""
        return GreeksCalculator()

    @pytest.fixture
    def sample_option_data(self, test_data_factory):
        """Sample option data for testing."""
        return test_data_factory.create_option_data()

    def test_calculator_initialization(self, calculator):
        """Test calculator initializes correctly."""
        assert calculator is not None
        assert hasattr(calculator, 'calculate_greeks')

    def test_greeks_calculation_accuracy(self, calculator, sample_option_data):
        """Test Greeks calculation accuracy against known values."""
        result = calculator.calculate_greeks(**sample_option_data)

        # Assert structure
        required_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
        for greek in required_greeks:
            assert greek in result, f"Missing {greek} in Greeks calculation"
            assert isinstance(result[greek], (int, float)), f"{greek} should be numeric"

        # Assert expected ranges for ATM call option
        assert 0.4 <= result["delta"] <= 0.6, f"ATM call delta should be ~0.5, got {result['delta']}"
        assert result["gamma"] > 0, "Gamma should be positive"
        assert result["theta"] < 0, "Theta should be negative (time decay)"
        assert result["vega"] > 0, "Vega should be positive"
        assert result["rho"] > 0, "Call rho should be positive"

    @pytest.mark.parametrize("option_type,expected_delta_sign", [
        ("call", 1),
        ("put", -1)
    ])
    def test_option_type_delta_signs(self, calculator, sample_option_data, option_type, expected_delta_sign):
        """Test that call/put options have correct delta signs."""
        sample_option_data["option_type"] = option_type
        result = calculator.calculate_greeks(**sample_option_data)

        actual_sign = 1 if result["delta"] >= 0 else -1
        assert actual_sign == expected_delta_sign, f"{option_type} delta sign incorrect"

    @pytest.mark.parametrize("invalid_param,invalid_value", [
        ("volatility", -0.1),  # Negative volatility
        ("time_to_expiry", -1),  # Negative time
        ("spot_price", -100),  # Negative price
        ("strike_price", 0),  # Zero strike
        ("risk_free_rate", -2),  # Unreasonable rate
    ])
    def test_invalid_input_validation(self, calculator, sample_option_data, invalid_param, invalid_value):
        """Test that calculator validates input parameters."""
        sample_option_data[invalid_param] = invalid_value

        with pytest.raises((GreeksCalculationError, ValueError)):
            calculator.calculate_greeks(**sample_option_data)

    def test_no_silent_fallbacks_on_errors(self, calculator, sample_option_data):
        """Test that calculator raises proper exceptions instead of silent failures."""
        # Test with extreme/invalid values that might cause numerical issues
        extreme_cases = [
            {"volatility": 100.0},  # Extreme volatility
            {"time_to_expiry": 0.0001},  # Very short time
            {"spot_price": 1e10},  # Extreme price
        ]

        for case in extreme_cases:
            test_data = sample_option_data.copy()
            test_data.update(case)

            # Should either succeed or raise exception, never return None
            try:
                result = calculator.calculate_greeks(**test_data)
                assert result is not None, f"Calculator returned None for case: {case}"
                assert "delta" in result, f"Calculator returned invalid result for case: {case}"
            except (GreeksCalculationError, ValueError):
                pass  # Expected for some extreme cases

    @pytest.mark.parametrize("moneyness", [
        (18000, 20000),  # Deep OTM put / Deep ITM call
        (19000, 20000),  # OTM put / ITM call
        (20000, 20000),  # ATM
        (21000, 20000),  # ITM put / OTM call
        (22000, 20000),  # Deep ITM put / Deep OTM call
    ])
    def test_moneyness_scenarios(self, calculator, sample_option_data, moneyness):
        """Test Greeks calculation across different moneyness levels."""
        spot_price, strike_price = moneyness
        sample_option_data.update({
            "spot_price": spot_price,
            "strike_price": strike_price
        })

        result = calculator.calculate_greeks(**sample_option_data)

        # Basic sanity checks
        assert isinstance(result["delta"], (int, float))
        assert 0 <= abs(result["delta"]) <= 1, f"Delta magnitude should be ≤1, got {result['delta']}"
        assert result["gamma"] >= 0, "Gamma should be non-negative"
        assert result["vega"] >= 0, "Vega should be non-negative"

    @pytest.mark.asyncio
    async def test_concurrent_calculations_accuracy(self, calculator):
        """Test calculator accuracy under concurrent load."""
        import asyncio

        async def calculate_single(spot_offset):
            spot = 20000 + spot_offset * 100
            data = {
                "spot_price": spot,
                "strike_price": 20000.0,
                "time_to_expiry": 0.25,
                "risk_free_rate": 0.06,
                "volatility": 0.20,
                "option_type": "call"
            }
            return await calculator.calculate_greeks_async(**data)

        # Test concurrent calculations
        tasks = [calculate_single(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10

        # All results should be valid
        for i, result in enumerate(results):
            assert isinstance(result, dict)
            assert "delta" in result
            assert isinstance(result["delta"], (int, float))

            # Delta should increase with spot price for calls
            if i > 0:
                assert result["delta"] >= results[i-1]["delta"], "Call delta should increase with spot price"

    def test_greeks_mathematical_properties(self, calculator, sample_option_data):
        """Test mathematical properties of Greeks calculations."""
        result = calculator.calculate_greeks(**sample_option_data)

        # Test put-call parity relationships where applicable
        put_data = sample_option_data.copy()
        put_data["option_type"] = "put"
        put_result = calculator.calculate_greeks(**put_data)

        # Delta relationship: call_delta - put_delta ≈ 1 (for European options)
        delta_diff = result["delta"] - put_result["delta"]
        assert 0.9 <= delta_diff <= 1.1, f"Call-Put delta difference should ≈ 1, got {delta_diff}"

        # Gamma should be the same for calls and puts with same parameters
        gamma_diff = abs(result["gamma"] - put_result["gamma"])
        assert gamma_diff < 0.001, f"Call-Put gamma should be equal, difference: {gamma_diff}"

    def test_time_decay_behavior(self, calculator, sample_option_data):
        """Test theta (time decay) behavior."""
        # Test options with different times to expiry
        times = [0.25, 0.1, 0.05, 0.01]  # 3 months to 1 week
        thetas = []

        for time_to_expiry in times:
            data = sample_option_data.copy()
            data["time_to_expiry"] = time_to_expiry
            result = calculator.calculate_greeks(**data)
            thetas.append(result["theta"])

        # Theta should generally become more negative as expiry approaches (time decay accelerates)
        for i in range(1, len(thetas)):
            assert thetas[i] <= thetas[i-1], "Theta should become more negative closer to expiry"

    def test_implied_volatility_calculation(self, calculator, sample_option_data):
        """Test implied volatility calculation if available."""
        if hasattr(calculator, 'calculate_implied_volatility'):
            # Test basic IV calculation
            option_price = 150.0  # Arbitrary option price

            try:
                iv = calculator.calculate_implied_volatility(
                    option_price=option_price,
                    **sample_option_data
                )

                assert isinstance(iv, (int, float))
                assert 0 < iv < 10, f"IV should be reasonable, got {iv}"

            except NotImplementedError:
                pytest.skip("Implied volatility not implemented")

    @pytest.mark.performance
    def test_calculation_performance(self, calculator, sample_option_data):
        """Test that Greeks calculation is performant."""
        import time

        start_time = time.time()

        # Calculate Greeks 100 times
        for _ in range(100):
            calculator.calculate_greeks(**sample_option_data)

        end_time = time.time()
        avg_time = (end_time - start_time) / 100

        # Should complete in under 10ms per calculation on average
        assert avg_time < 0.01, f"Greeks calculation too slow: {avg_time:.4f}s average"
