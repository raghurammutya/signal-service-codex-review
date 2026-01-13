"""
Unit tests for LocalMoneynessCalculator
"""
import pytest
from datetime import datetime
from app.services.moneyness_calculator_local import LocalMoneynessCalculator, MoneynessLevel

@pytest.mark.unit
class TestLocalMoneynessCalculator:
    """Test suite for LocalMoneynessCalculator"""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator instance with test configuration"""
        calc = LocalMoneynessCalculator()
        calc.initialize({
            'atm_threshold': 0.02,
            'otm_thresholds': {
                '5delta': 0.05,
                '10delta': 0.10,
                '25delta': 0.25
            }
        })
        return calc
    
    def test_classify_moneyness_atm(self, calculator):
        """Test ATM classification"""
        # Exactly ATM
        assert calculator.classify_moneyness(21500, 21500, 'call') == MoneynessLevel.ATM
        
        # Within ATM threshold (2%)
        assert calculator.classify_moneyness(21485, 21500, 'call') == MoneynessLevel.ATM
        assert calculator.classify_moneyness(21515, 21500, 'call') == MoneynessLevel.ATM
        
        # Call options - ATM range
        assert calculator.classify_moneyness(21490, 21500, 'call') == MoneynessLevel.ATM
        assert calculator.classify_moneyness(21510, 21500, 'call') == MoneynessLevel.ATM
    
    def test_classify_moneyness_itm_call(self, calculator):
        """Test ITM classification for calls"""
        # ITM calls (strike < spot)
        assert calculator.classify_moneyness(21400, 21500, 'call') == MoneynessLevel.ITM
        assert calculator.classify_moneyness(21300, 21500, 'call') == MoneynessLevel.ITM
        
        # Deep ITM
        assert calculator.classify_moneyness(21000, 21500, 'call') == MoneynessLevel.DITM
    
    def test_classify_moneyness_otm_call(self, calculator):
        """Test OTM classification for calls"""
        # OTM calls (strike > spot)
        assert calculator.classify_moneyness(21600, 21500, 'call') == MoneynessLevel.OTM
        assert calculator.classify_moneyness(21700, 21500, 'call') == MoneynessLevel.OTM
        
        # Deep OTM
        assert calculator.classify_moneyness(22000, 21500, 'call') == MoneynessLevel.DOTM
    
    def test_classify_moneyness_put_options(self, calculator):
        """Test moneyness classification for put options"""
        # ITM puts (strike > spot)
        assert calculator.classify_moneyness(21600, 21500, 'put') == MoneynessLevel.ITM
        
        # OTM puts (strike < spot)
        assert calculator.classify_moneyness(21400, 21500, 'put') == MoneynessLevel.OTM
        
        # ATM puts
        assert calculator.classify_moneyness(21500, 21500, 'put') == MoneynessLevel.ATM
    
    def test_find_strikes_by_delta(self, calculator):
        """Test delta-based strike finding"""
        greeks_data = {
            21400: {'delta': 0.05},
            21450: {'delta': 0.08},
            21500: {'delta': 0.15},
            21550: {'delta': 0.25},
            21600: {'delta': 0.35}
        }
        
        # Find 5delta strike
        result = calculator.find_strikes_by_delta(21500, [21400, 21450, 21500, 21550, 21600], 
                                                 0.05, 'call', greeks_data)
        assert result == 21400
        
        # Find 25delta strike
        result = calculator.find_strikes_by_delta(21500, [21400, 21450, 21500, 21550, 21600], 
                                                 0.25, 'call', greeks_data)
        assert result == 21550
        
        # No matching delta
        result = calculator.find_strikes_by_delta(21500, [21400, 21450, 21500, 21550, 21600], 
                                                 0.45, 'call', greeks_data)
        assert result is None
    
    def test_aggregate_greeks_by_moneyness(self, calculator):
        """Test Greeks aggregation by moneyness level"""
        strikes = [21450, 21500, 21550]
        greeks_by_strike = {
            21450: {'delta': 0.6, 'gamma': 0.01, 'iv': 0.18},
            21500: {'delta': 0.5, 'gamma': 0.02, 'iv': 0.20},
            21550: {'delta': 0.4, 'gamma': 0.01, 'iv': 0.18}
        }
        
        result = calculator.aggregate_greeks_by_moneyness(
            'ATM', strikes, greeks_by_strike, 21500, 'call'
        )
        
        assert 'delta' in result
        assert 'gamma' in result
        assert 'iv' in result
        assert 'strike_count' in result
        assert result['strike_count'] == 3
        
        # Check aggregated values
        assert abs(result['delta'] - 0.5) < 0.1  # Weighted average around ATM
        assert result['gamma'] > 0
        assert result['iv'] > 0
    
    def test_get_moneyness_strikes(self, calculator):
        """Test moneyness-based strike selection"""
        all_strikes = [21300, 21350, 21400, 21450, 21500, 21550, 21600, 21650, 21700]
        
        # Get ATM strikes
        atm_strikes = calculator.get_moneyness_strikes('ATM', all_strikes, 21500, 'call')
        assert 21500 in atm_strikes
        assert 21485 <= min(atm_strikes) <= 21515  # Within ATM range
        
        # Get OTM strikes
        otm_strikes = calculator.get_moneyness_strikes('OTM', all_strikes, 21500, 'call')
        assert all(strike > 21500 for strike in otm_strikes)
        
        # Get ITM strikes
        itm_strikes = calculator.get_moneyness_strikes('ITM', all_strikes, 21500, 'call')
        assert all(strike < 21500 for strike in itm_strikes)
    
    def test_performance_requirements(self, calculator):
        """Test that calculations meet performance requirements"""
        import time
        
        # Test single classification performance (< 1ms)
        start = time.time()
        for i in range(1000):
            calculator.classify_moneyness(21500 + i, 21500, 'call')
        end = time.time()
        
        avg_time = (end - start) / 1000 * 1000  # Convert to ms
        assert avg_time < 1.0, f"Average classification time {avg_time:.3f}ms exceeds 1ms requirement"
    
    def test_edge_cases(self, calculator):
        """Test edge cases and error handling"""
        # Zero strike price
        with pytest.raises(ValueError):
            calculator.classify_moneyness(0, 21500, 'call')
        
        # Negative spot price
        with pytest.raises(ValueError):
            calculator.classify_moneyness(21500, -100, 'call')
        
        # Invalid option type
        with pytest.raises(ValueError):
            calculator.classify_moneyness(21500, 21500, 'invalid')
        
        # Very large price differences
        result = calculator.classify_moneyness(1, 21500, 'call')
        assert result == MoneynessLevel.DITM
        
        result = calculator.classify_moneyness(50000, 21500, 'call')
        assert result == MoneynessLevel.DOTM
    
    def test_initialization_validation(self):
        """Test calculator initialization validation"""
        calc = LocalMoneynessCalculator()
        
        # Valid initialization
        config = {
            'atm_threshold': 0.02,
            'otm_thresholds': {'5delta': 0.05, '10delta': 0.10, '25delta': 0.25}
        }
        calc.initialize(config)
        assert calc.is_initialized
        
        # Invalid threshold (negative)
        with pytest.raises(ValueError):
            calc.initialize({'atm_threshold': -0.01})
        
        # Missing required configuration
        with pytest.raises(ValueError):
            calc.initialize({})
    
    def test_complex_moneyness_scenarios(self, calculator):
        """Test complex real-world moneyness scenarios"""
        # NIFTY weekly options scenario
        spot_price = 21547.30
        strikes = [21400, 21450, 21500, 21550, 21600, 21650, 21700]
        
        # Test calls
        call_classifications = {}
        for strike in strikes:
            call_classifications[strike] = calculator.classify_moneyness(strike, spot_price, 'call')
        
        # Verify logical progression
        assert call_classifications[21400] == MoneynessLevel.ITM
        assert call_classifications[21500] in [MoneynessLevel.ATM, MoneynessLevel.ITM]
        assert call_classifications[21550] in [MoneynessLevel.ATM, MoneynessLevel.OTM]
        assert call_classifications[21700] == MoneynessLevel.OTM
        
        # Test puts (should be inverse)
        put_classifications = {}
        for strike in strikes:
            put_classifications[strike] = calculator.classify_moneyness(strike, spot_price, 'put')
        
        # ITM puts should be where calls are OTM
        assert put_classifications[21700] == MoneynessLevel.ITM
        assert put_classifications[21400] == MoneynessLevel.OTM