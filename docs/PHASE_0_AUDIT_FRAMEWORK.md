# Phase 0: Token Usage Audit & Contract Enforcement Framework

## Overview

Phase 0 establishes the foundation for accelerated instrument_key adoption by conducting comprehensive token usage audits and defining strict API contracts.

**Duration**: 1 week  
**Prerequisites**: Phase 3 registry integration complete  
**Next Phase**: SDK & Strategy Layer Migration

---

## 1. Comprehensive Token Usage Audit

### 1.1 Automated Code Scanning

```python
# Token usage detection script
import ast
import os
import re
from typing import Dict, List, Set

class TokenUsageAuditor:
    """Audits codebase for instrument_token usage patterns"""
    
    def __init__(self, codebase_path: str):
        self.codebase_path = codebase_path
        self.token_patterns = [
            r'instrument_token',
            r'\.token\b',
            r'token_id',
            r'broker_token',
            r'ticker_token'
        ]
        
    def scan_token_usage(self) -> Dict[str, List[str]]:
        """Scan for all token usage patterns in codebase"""
        findings = {
            'api_parameters': [],
            'database_columns': [],
            'cache_keys': [],
            'business_logic': [],
            'broker_integration': []
        }
        
        # Implementation details for comprehensive scanning
        return findings
        
    def generate_migration_priority(self) -> List[str]:
        """Generate prioritized list of services for migration"""
        # Critical path analysis for token dependencies
        pass
```

### 1.2 Database Schema Analysis

```sql
-- Token persistence audit query
SELECT 
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE column_name LIKE '%token%'
   OR column_name LIKE '%instrument_id%'
ORDER BY table_schema, table_name;

-- Index usage analysis for token-based queries
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE indexdef ILIKE '%token%';
```

### 1.3 API Endpoint Analysis

```python
# API endpoint token usage scanner
class APITokenAuditor:
    """Analyzes API endpoints for token parameter usage"""
    
    def scan_api_endpoints(self) -> Dict[str, Any]:
        """Scan all API endpoints for token parameters"""
        return {
            'token_accepting_endpoints': [
                {
                    'service': 'order_service',
                    'endpoint': '/api/v1/orders',
                    'token_parameters': ['instrument_token'],
                    'migration_priority': 'high'
                }
            ],
            'token_returning_endpoints': [],
            'internal_token_apis': []
        }
```

---

## 2. API Contract Definition

### 2.1 Primary Contract Standards

```python
# API contract definition
from typing import Protocol, runtime_checkable

@runtime_checkable
class InstrumentKeyContract(Protocol):
    """Defines instrument_key as primary identifier contract"""
    
    def process_instrument(self, instrument_key: str, **kwargs) -> Any:
        """All APIs must accept instrument_key as primary identifier"""
        pass
    
    def _derive_token(self, instrument_key: str) -> Optional[str]:
        """Internal method for token derivation from registry"""
        pass

# Contract validation decorator
def requires_instrument_key(func):
    """Decorator to enforce instrument_key usage"""
    def wrapper(*args, **kwargs):
        if 'instrument_token' in kwargs:
            raise APIContractViolation(
                "Direct instrument_token usage not allowed. Use instrument_key."
            )
        return func(*args, **kwargs)
    return wrapper
```

### 2.2 Migration Contract Framework

```python
# Migration compatibility framework
class MigrationCompatibilityLayer:
    """Provides backward compatibility during migration"""
    
    def __init__(self, registry_client):
        self.registry_client = registry_client
        
    @deprecated("Use instrument_key parameter")
    def accept_legacy_token(self, instrument_token: str) -> str:
        """Convert legacy token to instrument_key"""
        return self.registry_client.resolve_key_from_token(instrument_token)
    
    def validate_contract_compliance(self, api_call: Dict) -> bool:
        """Validate API call follows instrument_key contract"""
        has_key = 'instrument_key' in api_call
        has_token_input = 'instrument_token' in api_call
        
        return has_key and not has_token_input
```

---

## 3. Documentation Updates

### 3.1 INSTRUMENT_DATA_ARCHITECTURE.md Updates

```markdown
# Instrument Data Architecture - instrument_key Primary

## Core Principles

1. **instrument_key is the PRIMARY identifier** for all instruments across services
2. **instrument_token is derived metadata** obtained from registry only when needed
3. **No direct token persistence** as primary keys in any service
4. **Registry-first lookup** for all instrument operations

## API Contract Standards

### Required Patterns
```python
# ✅ CORRECT: instrument_key as primary identifier
def create_order(instrument_key: str, quantity: int) -> Order:
    # Get token internally when needed for broker
    token = registry.get_broker_token(instrument_key, broker_id)
    return broker_client.place_order(token, quantity)

# ❌ INCORRECT: instrument_token as input parameter  
def create_order(instrument_token: str, quantity: int) -> Order:
    return broker_client.place_order(instrument_token, quantity)
```

### Migration Requirements
- All existing APIs must be updated to accept instrument_key
- Backward compatibility maintained during transition period
- Token derivation must use registry client only
```

### 3.2 INSTRUMENT_SUBSCRIPTION_ARCHITECTURE.md Updates

```markdown
# Instrument Subscription Architecture - Key-Based Subscriptions

## Subscription Contract

### Primary Subscription Pattern
```python
# ✅ CORRECT: Key-based subscription
subscription_manager.subscribe_to_instrument(
    instrument_key="AAPL_NASDAQ_EQUITY",
    data_types=["quotes", "trades"]
)

# ❌ INCORRECT: Token-based subscription
subscription_manager.subscribe_to_instrument(
    instrument_token="12345",  # Not allowed
    data_types=["quotes", "trades"]
)
```

### Internal Token Resolution
- Subscription bridge resolves tokens internally for broker feeds
- Multiple broker tokens supported per instrument_key
- Subscription state tracked by instrument_key
```

---

## 4. Contract Compliance Testing

### 4.1 Automated Contract Validation

```python
# Contract compliance test framework
import pytest
from unittest.mock import patch

class TestAPIContractCompliance:
    """Test suite for instrument_key contract compliance"""
    
    def test_api_requires_instrument_key(self):
        """Test that APIs require instrument_key parameter"""
        with pytest.raises(APIContractViolation):
            order_service.create_order(instrument_token="12345", quantity=100)
    
    def test_no_direct_token_persistence(self):
        """Test that tokens are not persisted as primary keys"""
        order = order_service.create_order(
            instrument_key="AAPL_NASDAQ_EQUITY", 
            quantity=100
        )
        # Verify instrument_key is stored, not token
        assert order.instrument_key == "AAPL_NASDAQ_EQUITY"
        assert not hasattr(order, 'instrument_token')
    
    @patch('registry_client.get_broker_token')
    def test_token_derivation_from_registry(self, mock_registry):
        """Test that tokens are derived from registry only"""
        mock_registry.return_value = "broker_token_123"
        
        order_service.create_order(
            instrument_key="AAPL_NASDAQ_EQUITY", 
            quantity=100
        )
        
        mock_registry.assert_called_with(
            instrument_key="AAPL_NASDAQ_EQUITY",
            broker_id="default"
        )
```

### 4.2 Performance Impact Testing

```python
# Performance testing for registry lookup overhead
class TestRegistryLookupPerformance:
    """Test performance impact of registry-based token resolution"""
    
    def test_registry_lookup_latency(self):
        """Test registry lookup stays under 50ms"""
        start_time = time.time()
        token = registry_client.get_broker_token("AAPL_NASDAQ_EQUITY")
        end_time = time.time()
        
        lookup_latency = (end_time - start_time) * 1000
        assert lookup_latency < 50, f"Registry lookup took {lookup_latency}ms"
    
    def test_cache_effectiveness(self):
        """Test that registry lookups are properly cached"""
        # First lookup - should hit registry
        token1 = registry_client.get_broker_token("AAPL_NASDAQ_EQUITY")
        
        # Second lookup - should hit cache
        start_time = time.time()
        token2 = registry_client.get_broker_token("AAPL_NASDAQ_EQUITY")
        end_time = time.time()
        
        cache_latency = (end_time - start_time) * 1000
        assert cache_latency < 5, f"Cache lookup took {cache_latency}ms"
        assert token1 == token2
```

---

## 5. Governance Standards

### 5.1 Service Development Standards

```python
# Code review checklist generator
class ContractComplianceChecker:
    """Automated checker for code review compliance"""
    
    def check_service_compliance(self, service_code: str) -> List[str]:
        """Check service code for contract compliance"""
        violations = []
        
        # Check for direct token usage
        if re.search(r'instrument_token.*=.*request\.', service_code):
            violations.append(
                "Direct instrument_token parameter usage detected"
            )
        
        # Check for token persistence
        if re.search(r'\.save\(.*instrument_token', service_code):
            violations.append(
                "Token persistence as primary key detected"
            )
        
        # Check for registry usage
        if 'registry_client' not in service_code:
            violations.append(
                "Missing registry client for token derivation"
            )
        
        return violations
```

### 5.2 Deployment Gate Integration

```python
# Deployment gate for contract compliance
class InstrumentKeyDeploymentGate:
    """Deployment gate ensuring contract compliance"""
    
    def validate_deployment(self, service_config: Dict) -> bool:
        """Validate service follows instrument_key contract"""
        checks = [
            self._check_api_contracts(),
            self._check_database_schema(),
            self._check_registry_integration(),
            self._validate_test_coverage()
        ]
        
        return all(checks)
    
    def _check_api_contracts(self) -> bool:
        """Verify all APIs use instrument_key"""
        # Implementation for API contract validation
        return True
```

---

## 6. Phase 0 Deliverables

### 6.1 Audit Reports

1. **Comprehensive Token Usage Report**
   - Service-by-service token dependency analysis
   - Migration priority matrix
   - Risk assessment for each service
   - Estimated migration effort

2. **Database Schema Analysis**
   - Token column inventory
   - Index usage analysis
   - Data migration requirements
   - Performance impact assessment

3. **API Contract Compliance Report**
   - Current API compliance status
   - Required changes for each endpoint
   - Backward compatibility plan
   - Performance impact analysis

### 6.2 Updated Documentation

1. **INSTRUMENT_DATA_ARCHITECTURE.md**
   - instrument_key primacy established
   - Token usage restrictions documented
   - Registry-first patterns defined

2. **INSTRUMENT_SUBSCRIPTION_ARCHITECTURE.md**
   - Key-based subscription patterns
   - Internal token resolution flows
   - Subscription state management

3. **API_CONTRACT_STANDARDS.md**
   - Mandatory instrument_key usage
   - Token derivation patterns
   - Compliance testing requirements

### 6.3 Compliance Framework

1. **Automated Testing Suite**
   - Contract compliance tests
   - Performance impact validation
   - Registry lookup testing

2. **Code Review Standards**
   - Compliance checking tools
   - Review checklist automation
   - Deployment gate integration

3. **Governance Procedures**
   - Contract enforcement policies
   - Violation reporting procedures
   - Compliance monitoring tools

---

## 7. Success Criteria for Phase 0

- [ ] **Complete token usage inventory** across all services
- [ ] **API contracts defined** with enforcement mechanisms
- [ ] **Documentation updated** with new standards
- [ ] **Compliance testing framework** operational
- [ ] **Governance procedures** established and validated
- [ ] **Migration priority plan** approved and resourced

**Phase 0 completion enables confident execution of SDK & Strategy Layer Migration in Phase 1.**