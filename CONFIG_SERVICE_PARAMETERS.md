# 🎯 Signal Service Config Service Parameters

This document defines all parameters that should be stored in `config_service` for the Signal Service.

## 📋 **MINIMAL PARAMETER SET (5 Total)**

### **1. Model Selection**
**Parameter**: `signal_service.options_pricing_model`
**Type**: String  
**Default**: `"black_scholes_merton"`
**Valid Values**: `["black_scholes_merton", "black_scholes", "black76"]`
**Description**: Selects which pyvollib model to use for option Greeks calculations

```yaml
signal_service.options_pricing_model: "black_scholes_merton"
```

### **2. Risk-Free Rate**
**Parameter**: `signal_service.model_params.risk_free_rate`
**Type**: Float
**Default**: `"0.06"`
**Range**: `0.0 - 0.50` (0% to 50% annual)
**Description**: Annual risk-free interest rate (typically RBI repo rate for India)

```yaml
signal_service.model_params.risk_free_rate: "0.06"
```

### **3. Dividend Yield** 
**Parameter**: `signal_service.model_params.dividend_yield`
**Type**: Float
**Default**: `"0.0"`
**Range**: `0.0 - 0.20` (0% to 20% annual)
**Description**: Annual dividend yield (typically 0.0 for Indian equity options)

```yaml
signal_service.model_params.dividend_yield: "0.0"
```

### **4. Default Volatility**
**Parameter**: `signal_service.model_params.default_volatility`
**Type**: Float
**Default**: `"0.20"`
**Range**: `0.01 - 10.0` (1% to 1000%)
**Description**: Fallback volatility when implied volatility unavailable

```yaml
signal_service.model_params.default_volatility: "0.20"
```

### **5. Maximum Volatility**
**Parameter**: `signal_service.model_params.volatility_max`
**Type**: Float
**Default**: `"5.0"`
**Range**: `0.1 - 20.0`
**Description**: Maximum allowed volatility for validation

```yaml
signal_service.model_params.volatility_max: "5.0"
```

## 🔧 **DOCKER-COMPOSE ENVIRONMENT VARIABLES**

Only these elementary parameters should be passed via docker-compose:

```yaml
environment:
  # Core service configuration
  - CONFIG_SERVICE_URL=http://config-service:8100
  - INTERNAL_API_KEY=${INTERNAL_API_KEY}
  - SERVICE_NAME=signal_service
  - ENVIRONMENT=${ENVIRONMENT:-prod}
  
  # Emergency fallbacks (only if config_service fails)
  - DATABASE_URL=${DATABASE_URL:-}
  - REDIS_URL=${REDIS_URL:-}
  
  # Container-specific (not business logic)
  - PORT=${SIGNAL_SERVICE_PORT:-8003}
  - WORKER_ID=${WORKER_ID:-signal-worker-1}
```

## ✅ **VALIDATION AND ERROR HANDLING**

### **Exception Types**
1. **UnsupportedModelError**: Invalid model in config_service
2. **ConfigurationError**: Invalid parameter values or ranges
3. **GreeksCalculationError**: Calculation failures

### **Example Error Messages**
```
UnsupportedModelError: Unsupported options pricing model: 'invalid_model'. 
Supported models: black_scholes_merton, black_scholes, black76

ConfigurationError: Invalid risk_free_rate: 0.75. Must be between 0.0 and 0.50

ConfigurationError: Invalid volatility bounds: min=0.50, max=0.20
```

## 📊 **PARAMETER USAGE**

### **Model Parameter Mapping**
| Model | Function Signature |
|-------|-------------------|
| `black_scholes_merton` | `func(flag, S, K, t, r, sigma, q)` |
| `black_scholes` | `func(flag, S, K, t, r, sigma)` |
| `black76` | `func(flag, S, K, t, r, sigma, q)` |

### **Consistency Guarantee**
- Both **individual** and **vectorized** calculations use the same model
- Same parameters across all Greeks (delta, gamma, theta, vega, rho)
- Same results regardless of calculation method

## 🚀 **BENEFITS**

1. **Centralized**: All parameters in one place (config_service)
2. **Validated**: Comprehensive parameter validation with clear errors
3. **Flexible**: Can switch models without code changes  
4. **Consistent**: Individual and batch calculations always match
5. **Minimal**: Only 5 parameters needed (down from 40+ scattered values)
6. **Production-Ready**: Proper error handling and fallbacks

## 📝 **IMPLEMENTATION NOTES**

- Parameters are loaded once at service startup and cached
- Model functions are dynamically imported based on configuration
- Invalid models fail fast with clear error messages
- All calculations use the same configured model consistently
- Emergency fallbacks available if config_service unavailable

This design ensures the Signal Service is truly production-ready with dynamic, centralized parameter management! 🎯