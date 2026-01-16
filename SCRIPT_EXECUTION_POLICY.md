# Script Execution Policy

## Production Environment - Script Execution Disabled

**⚠️ IMPORTANT: Script execution is completely disabled in production environments for security reasons.**

### Why Script Execution is Disabled

1. **Security Risk**: Dynamic script execution poses significant security vulnerabilities
2. **Code Injection**: Untrusted scripts could potentially execute malicious code
3. **Resource Abuse**: Scripts could consume excessive CPU/memory resources
4. **Data Access**: Scripts might access sensitive data inappropriately

### Affected Endpoints

The following endpoints will return HTTP 500 errors in production:

- `POST /api/v2/signals/execute-marketplace`
- `POST /api/v2/signals/execute-personal`
- Any endpoint using `SignalExecutor.execute_signal_script()`

### Alternative Approaches for Production

#### 1. Pre-Compiled Signal Libraries
```python
# Instead of dynamic scripts, use pre-compiled signal functions
from signal_library import bollinger_bands, rsi_divergence

signals = bollinger_bands(market_data, period=20, std_dev=2)
```

#### 2. Signal Configuration
```json
{
  "signal_type": "technical_indicator",
  "indicator": "RSI",
  "parameters": {
    "period": 14,
    "overbought": 70,
    "oversold": 30
  }
}
```

#### 3. Signal Deployment Pipeline
```bash
# Deploy signals through proper CI/CD pipeline
1. Develop signal in safe environment
2. Code review and testing
3. Package as container or library
4. Deploy through orchestration system
```

### Development Environment

Script execution remains enabled in development environments for:

- Testing and experimentation
- Signal development and debugging
- Educational purposes

### Migration Guide

If your application currently depends on script execution:

1. **Audit Dependencies**: Identify which workflows use script execution
2. **Convert to Libraries**: Migrate dynamic scripts to pre-compiled libraries
3. **Use Signal Configs**: Replace scripts with configuration-based signals
4. **Test Alternatives**: Verify functionality works with new approach
5. **Update Documentation**: Document the new signal deployment process

### Environment Detection

The service automatically detects environment using the `ENVIRONMENT` variable:

- **Production Environments**: `production`, `prod`, `staging`
- **Development Environments**: `development`, `dev`, `local`

### Error Messages

When script execution is attempted in production:

```
RuntimeError: Script execution is disabled in production environment for security reasons.
Use pre-compiled signal libraries or contact administrators for signal deployment.
See SCRIPT_EXECUTION_POLICY.md for migration guidance.
```

### Contact

For questions about signal deployment in production:

1. **Development Team**: Implement pre-compiled signal libraries
2. **DevOps Team**: Set up signal deployment pipeline  
3. **Security Team**: Review signal security requirements

---

**This policy ensures production security while maintaining development flexibility.**