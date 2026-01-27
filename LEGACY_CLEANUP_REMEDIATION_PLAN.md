# Legacy instrument_token Cleanup - Prioritized Remediation Plan


## ✅ **UPDATE - Experimental Directory Archived**

**Date:** 2026-01-27

The `instrument_registry_experiments` directory has been successfully archived to `/home/stocksadmin/.archived_experiments/` following successful production migration. All references below are now historical.

**Production Service Location:** `/home/stocksadmin/instrument_registry/`

---


## 🎯 **EXECUTIVE SUMMARY**

Post-Phase 2 repository scan identified **26 remaining instrument_token references** across the codebase. These fall into expected categories (migration artifacts, documentation, testing) with **1 critical contract violation** requiring immediate attention.

**Key Finding:** Production services are now instrument_key-native as designed, with tokens relegated to metadata/compatibility roles. ✅

---

## 📊 **PRIORITY MATRIX**

| Priority | Count | Description | Timeline | Impact |
|----------|-------|-------------|----------|---------|
| **P0 (Critical)** | 1 file | Active contract violations | 1-2 days | High |
| **P1 (High)** | 2 files | Developer confusion risk | 3-5 days | Medium |
| **P2 (Medium)** | 11 files | Documentation cleanup | 1-2 weeks | Low |
| **P3 (Low)** | 12 files | Historical artifacts | As needed | None |

---

## 🚨 **P0 - CRITICAL (Immediate Action Required)**

### **1. Contract Violation in Production API**
**File:** `app/api/v2/indicators.py:147`  
**Issue:** Public API still accepts `instrument_token` parameter violating instrument_key-first contract  
**Impact:** Architectural consistency violation, potential developer confusion  
**Owner:** API Team  

**Required Fix:**
```python
# CURRENT (violates contract):
async def get_historical_data(
    self,
    instrument_token: int,  # ❌ CONTRACT VIOLATION
    timeframe: str,
    periods: int,
    end_date: Optional[datetime] = None
) -> pd.DataFrame:

# REQUIRED CHANGE:
async def get_historical_data(
    self,
    instrument_key: str,  # ✅ CONTRACT COMPLIANT
    timeframe: str,
    periods: int,
    end_date: Optional[datetime] = None
) -> pd.DataFrame:
    # Add internal token resolution for broker compatibility
    from app.clients.instrument_registry_client import create_registry_client
    registry = create_registry_client()
    instrument_token = await registry.get_broker_token(instrument_key, "kite")
    
    # Rest of implementation unchanged...
```

**Action:** Update API signature to use instrument_key, add internal token resolution
**Timeline:** 1-2 days
**Testing:** Update API tests to use instrument_key format

---

## ⚠️ **P1 - HIGH (Developer Confusion Risk)**

### **2. Testing Infrastructure Inconsistency**
**File:** `tests/integration/test_historical_data_retrieval.py:23`  
**Issue:** Integration tests use token-based mocking while production uses instrument_key  
**Impact:** New developers may follow incorrect testing patterns  
**Owner:** QA Team

**Current Code:**
```python
@pytest.fixture
def mock_historical_data():
    return {
        "instrument_token": 12345,  # ❌ INCONSISTENT WITH PRODUCTION
        "data": [...]
    }
```

**Recommended Fix:**
```python
@pytest.fixture
def mock_historical_data():
    return {
        "instrument_key": "AAPL_NASDAQ_EQUITY",  # ✅ CONSISTENT
        "instrument_token": 12345,  # Metadata for broker compatibility
        "data": [...]
    }
```

### **3. SDK Documentation Inconsistency**
**File:** `docs/sdk/historical_data_usage.md:45`  
**Issue:** SDK examples show token-based usage instead of instrument_key  
**Impact:** Developers may implement using deprecated patterns  
**Owner:** Documentation Team

**Current Documentation:**
```markdown
# Historical Data Example
client.get_historical_data(
    instrument_token=12345,  # ❌ DEPRECATED PATTERN
    timeframe="1D"
)
```

**Recommended Update:**
```markdown
# Historical Data Example  
client.get_historical_data(
    instrument_key="AAPL_NASDAQ_EQUITY",  # ✅ CURRENT PATTERN
    timeframe="1D"
)
```

---

## 📋 **P2 - MEDIUM (Documentation Cleanup)**

### **Migration & Legacy Artifacts (Intentionally Preserved)**
| File | Context | Action | Owner |
|------|---------|--------|-------|
| `instrument_registry_experiments/schema_bridge.py` | Migration bridge | Document as "migration artifact" | Migration Team |
| `order_service_clean/migration_scripts/token_to_key.sql` | Migration script | Add header comment explaining historical purpose | Data Team |
| `order_service_backup/legacy_tick_listener.py` | Legacy listener | Mark as "historical backup only" | DevOps |
| `signal-service-codex-review/legacy_router.py` | Backward compatibility | Document compatibility purpose | API Team |

**Recommended Action for All:**
Add standardized header comments:
```python
"""
LEGACY ARTIFACT - Phase 2 Migration Support
This file intentionally preserves instrument_token references for:
- Migration bridge compatibility
- Historical data validation  
- Backup/rollback procedures
Status: Maintained for operational safety, not for new development
"""
```

### **Documentation & Audit Reports**
| File | Context | Action | Owner |
|------|---------|--------|-------|
| `instrument_usage/token_audit_2025.md` | Historical audit | Add "historical context only" disclaimer | Audit Team |
| `algo_engine_instrument_usage.md` | Usage analysis | Update with current instrument_key patterns | Analytics Team |
| `analysis/phase_0_audit.json` | Phase 0 results | Archive with "pre-migration baseline" label | Project Team |
| `docs/migration/token_sunset_plan.md` | Sunset planning | Update status to "COMPLETED" | Documentation Team |

**Recommended Action:**
Add disclaimer to documentation files:
```markdown
> **HISTORICAL CONTEXT:** This document reflects pre-Phase 2 migration state. 
> Current production systems use instrument_key identifiers. 
> Preserved for audit trail and historical reference.
```

---

## 📚 **P3 - LOW (Historical Artifacts)**

### **Archive & Backup Materials**
These files are correctly preserved as historical artifacts:

| Category | Files | Recommendation |
|----------|-------|----------------|
| **Testing Fixtures** | 4 files in `tests/fixtures/legacy/` | Keep as regression test support |
| **Migration Scripts** | 3 files in `scripts/migration/archive/` | Archive with retention policy |
| **Backup Services** | 2 files in `order_service_backup/` | Maintain for rollback capability |
| **Experimental Code** | 3 files in `_tmp_ml/experiments/` | Clean up when experiments complete |

**No Action Required** - These serve their intended archival purpose.

---

## 🔧 **IMPLEMENTATION ROADMAP**

### **Week 1: Critical Fixes**
- **Day 1-2:** Fix P0 contract violation in indicators API
- **Day 3-4:** Update integration tests (P1)  
- **Day 5:** Update SDK documentation (P1)

### **Week 2: Documentation Cleanup**  
- **Day 6-8:** Add headers to migration artifacts
- **Day 9-10:** Update audit documentation with disclaimers
- **Day 11-12:** Review and validate all changes

### **Week 3: Optional Cleanup**
- **Day 13-15:** Archive experimental files if ready
- **Day 16-17:** Optimize backup retention policies
- **Day 18-19:** Final validation and testing

---

## 📊 **QUALITY GATES**

### **Definition of Done:**
- ✅ P0 contract violations resolved
- ✅ P1 developer confusion risks mitigated  
- ✅ P2 documentation clearly labeled
- ✅ All changes tested and validated
- ✅ No regression in production systems

### **Validation Checklist:**
```bash
# Verify no new contract violations
grep -r "instrument_token.*:" app/api/ --include="*.py" | grep -v "# Legacy"

# Verify test consistency  
grep -r "instrument_token" tests/ --include="*.py" | grep -v "# Migration artifact"

# Verify documentation disclaimers
find docs/ -name "*.md" -exec grep -l "instrument_token" {} \; | xargs grep -L "HISTORICAL CONTEXT"
```

---

## 🎯 **SUCCESS METRICS**

### **Completion Criteria:**
- **Contract Compliance:** 100% of active APIs use instrument_key
- **Developer Experience:** Clear distinction between current vs legacy patterns
- **Documentation Quality:** All historical references properly labeled
- **Code Maintainability:** Reduced confusion for new team members

### **Risk Mitigation:**
- **Regression Testing:** Use existing Phase 2 validation framework
- **Rollback Plan:** Changes are additive, minimal rollback risk
- **Monitoring:** No production impact expected from documentation changes

---

## 📋 **OWNERSHIP & RESPONSIBILITIES**

| Team | Responsibility | Timeline |
|------|---------------|----------|
| **API Team** | Fix contract violation (P0), legacy router documentation | Week 1 |
| **QA Team** | Update integration tests, validate changes | Week 1 |  
| **Documentation Team** | SDK docs, audit disclaimers | Week 1-2 |
| **Migration Team** | Migration artifact documentation | Week 2 |
| **DevOps** | Backup service documentation | Week 2 |

---

## ✅ **SIGNOFF REQUIREMENTS**

### **Required Approvals:**
- **Technical Lead:** Contract violation fix approval
- **QA Lead:** Testing strategy validation
- **Documentation Lead:** Documentation standards compliance
- **Product Owner:** API change impact assessment

### **Final Validation:**
After completing P0-P2 items:
- Run complete Phase 2 regression suite
- Validate no production impact
- Confirm developer documentation clarity
- Update this remediation plan status to COMPLETE

---

**Prepared by:** Legacy Cleanup Task Force  
**Date:** January 27, 2026  
**Status:** READY FOR IMPLEMENTATION  
**Next Steps:** Begin P0 critical fixes immediately