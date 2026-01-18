# 3rd Party Package Integration Verification Checklist

## Overview
This checklist provides critical files and commands to verify end-to-end wiring of PyVolLib, scikit-learn, and pandas_ta integrations in the Signal Service.

## 1. PyVolLib (Options Greeks) Verification

### Critical Files
```bash
# Core integration files
app/services/greeks_indicators.py          # 7 registered Greeks indicators
app/services/greeks_calculator.py          # Individual Greek methods
app/services/vectorized_pyvollib_engine.py # Vectorized engine
app/services/register_indicators.py        # Import chain
app/services/indicator_registry.py         # GREEKS/OPTIONS categories
```

### Verification Commands
```bash
# Test vectorized engine with fallback behavior
pytest tests/unit/test_pyvollib_vectorized_engine_fallback.py -v

# Test end-to-end PyVolLib workflow
pytest test_pyvollib_end_to_end.py -v

# Test signal processing coverage including Greeks
pytest tests/integration/test_signal_processing_coverage.py -v

# Verify registration
python -c "from app.services.indicator_registry import IndicatorRegistry; from app.services.register_indicators import register_all_indicators; register_all_indicators(); print(f'Greeks indicators: {len(IndicatorRegistry.list_by_category(IndicatorRegistry.GREEKS))}')"

# Test API accessibility
curl -X GET "http://localhost:8003/api/v2/indicators/available-indicators" | jq '.greeks'
```

### Expected Results
- 7 Greeks indicators registered (delta, gamma, theta, vega, rho, implied_vol, all_greeks)
- Vectorized engine functional with numpy array processing
- Fallback to standard PyVolLib when vectorized unavailable
- API endpoints return Greeks in available indicators list

## 2. Scikit-learn (Clustering) Verification

### Critical Files
```bash
# Core integration files
app/services/clustering_indicators.py      # DBSCAN, KMeans, IsolationForest
app/services/register_indicators.py       # Import clustering_indicators
app/services/indicator_registry.py        # CLUSTERING category
requirements.txt                          # scikit-learn>=1.5.0
```

### Verification Commands
```bash
# Test clustering indicators directly
python -c "from app.services.clustering_indicators import cluster_support_resistance, kmeans_price_levels, price_outliers; print('Clustering indicators loaded successfully')"

# Test integration coverage
pytest tests/integration/test_signal_processing_coverage.py::test_clustering_indicators -v

# Verify scikit-learn dependency
python -c "import sklearn; print(f'sklearn version: {sklearn.__version__}')"

# Test registration
python -c "from app.services.indicator_registry import IndicatorRegistry; from app.services.register_indicators import register_all_indicators; register_all_indicators(); print(f'Clustering indicators: {len(IndicatorRegistry.list_by_category(IndicatorRegistry.CLUSTERING))}')"

# Test API accessibility
curl -X GET "http://localhost:8003/api/v2/indicators/available-indicators" | jq '.clustering'
```

### Expected Results
- 3 clustering indicators registered (cluster_support_resistance, kmeans_price_levels, price_outliers)
- DBSCAN, KMeans, IsolationForest algorithms functional
- Proper parameter validation and error handling
- API endpoints expose clustering indicators

## 3. Pandas_ta (Technical Analysis) Verification

### Critical Files
```bash
# Core integration files
app/services/pandas_ta_executor.py         # Enhanced executor with strategy support
app/api/v2/indicators.py                  # API integration
app/services/indicator_registry.py        # PANDAS_TA category
requirements.txt                          # pandas-ta>=0.4.67b0
```

### Verification Commands
```bash
# Test pandas_ta coverage with real data
pytest tests/unit/test_pandas_ta_coverage_with_real_data.py -v

# Test pandas_ta executor functionality
pytest tests/unit/test_pandas_ta_executor.py -v

# Test comprehensive pandas_ta integration
python run_pandas_ta_tests.py

# Verify pandas_ta dependency
python -c "import pandas_ta as ta; print(f'pandas_ta version: {ta.version}')"

# Test dual execution model (custom first, then pandas_ta)
python -c "from app.services.pandas_ta_executor import PandasTAExecutor; executor = PandasTAExecutor(); print('Executor initialized successfully')"

# Test API integration
curl -X GET "http://localhost:8003/api/v2/indicators/available-indicators" | jq '.pandas_ta | length'
```

### Expected Results
- 244+ pandas_ta indicators accessible
- Strategy-based execution functional (_execute_strategy_sync)
- Dual execution model (custom indicators first, pandas_ta fallback)
- 90%+ success rate in indicator calculations
- Sub-millisecond execution performance

## 4. Universal Computation API Verification

### Critical Files
```bash
# Universal API integration
app/api/v2/universal.py                   # Unified computation endpoint
app/services/universal_calculator.py      # Universal calculation engine
```

### Verification Commands
```bash
# Test universal computation with all libraries
curl -X POST "http://localhost:8003/api/v2/universal/compute" \
  -H "Content-Type: application/json" \
  -d '{"computation_type": "greeks", "library": "py_vollib", "function": "option_delta", "parameters": {...}}'

# Test library enumeration
curl -X GET "http://localhost:8003/api/v2/universal/libraries" | jq '.'

# Test computation types
curl -X GET "http://localhost:8003/api/v2/universal/computation-types" | jq '.'
```

### Expected Results
- All three libraries (py_vollib, scikit-learn, pandas_ta) listed in supported libraries
- Universal computation routes correctly to respective engines
- Proper error handling and validation

## 5. QA Pipeline Verification

### Coverage Reports
```bash
# Verify current coverage reports
cat coverage_reports/COMPLIANCE_COVERAGE_REPORT.md
cat COMPLIANCE_COVERAGE_REPORT.md

# Run full test suite
pytest tests/ --cov=app --cov-report=html --cov-report=term

# Specific 3rd party package tests
pytest tests/unit/test_pyvollib_vectorized_engine_fallback.py tests/unit/test_pandas_ta_coverage_with_real_data.py tests/integration/test_signal_processing_coverage.py -v
```

### Expected Results
- 100% coverage for all 3rd party integrations
- No "0.0% confidence" entries in current reports
- All tests passing with go/no-go status: GO
- QA artifacts properly archived

## 6. End-to-End Workflow Verification

### Complete Integration Test
```bash
# Start the service
python -m app.main

# Verify all indicators loaded
curl -X GET "http://localhost:8003/api/v2/indicators/available-indicators" | jq 'keys'

# Test sample calculations from each library
# PyVolLib
curl -X POST "http://localhost:8003/api/v2/indicators/calculate" \
  -H "Content-Type: application/json" \
  -d '{"indicator": "option_delta", "parameters": {...}}'

# Scikit-learn
curl -X POST "http://localhost:8003/api/v2/indicators/calculate" \
  -H "Content-Type: application/json" \
  -d '{"indicator": "cluster_support_resistance", "parameters": {...}}'

# Pandas_ta
curl -X POST "http://localhost:8003/api/v2/indicators/calculate" \
  -H "Content-Type: application/json" \
  -d '{"indicator": "sma", "parameters": {...}}'
```

### Expected Results
- Service starts without errors
- All indicator categories present (greeks, options, clustering, pandas_ta)
- Sample calculations return valid results
- No missing wiring or stub implementations

## 7. Release Readiness Criteria

### Pre-Release Checklist
- [ ] All pytest commands above pass
- [ ] Coverage reports show 100% for 3rd party integrations  
- [ ] API endpoints return expected indicator counts
- [ ] No placeholder/stub code in critical paths
- [ ] QA pipeline generates current (not stale) coverage reports
- [ ] Universal computation API handles all three libraries
- [ ] Performance benchmarks within acceptable ranges

### Commands to Re-verify on Release Commit
```bash
# Quick verification suite
pytest tests/unit/test_pyvollib_vectorized_engine_fallback.py tests/unit/test_pandas_ta_coverage_with_real_data.py tests/integration/test_signal_processing_coverage.py --tb=short

# Indicator count verification
python -c "
from app.services.register_indicators import register_all_indicators
from app.services.indicator_registry import IndicatorRegistry
register_all_indicators()
counts = IndicatorRegistry.count_by_category()
print(f'Total: {IndicatorRegistry.count()}')
for cat, count in sorted(counts.items()):
    print(f'  {cat}: {count}')
expected = {'greeks': 7, 'clustering': 3}
for cat, exp_count in expected.items():
    assert counts.get(cat, 0) >= exp_count, f'{cat} has {counts.get(cat, 0)}, expected >= {exp_count}'
print('✓ All 3rd party packages properly integrated')
"

# API smoke test
curl -s "http://localhost:8003/api/v2/indicators/available-indicators" | jq -e '.greeks | length >= 7' && echo "✓ PyVolLib integrated"
curl -s "http://localhost:8003/api/v2/indicators/available-indicators" | jq -e '.clustering | length >= 3' && echo "✓ Scikit-learn integrated"  
curl -s "http://localhost:8003/api/v2/indicators/available-indicators" | jq -e '.pandas_ta | length >= 200' && echo "✓ Pandas_ta integrated"
```

## Notes
- Stale coverage reports (0.0% confidence) in older coverage_reports/ files should be ignored
- Current QA workflow regenerates reports correctly showing 100% coverage
- Release readiness summary only succeeds when all tests pass
- This checklist should be run on each release candidate to verify integration integrity