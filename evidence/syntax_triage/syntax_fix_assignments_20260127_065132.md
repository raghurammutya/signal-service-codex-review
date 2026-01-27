# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** 2026-01-27 06:51
**Total Syntax Errors:** 879
**Files Affected:** 35
**Modules Affected:** 1

## Executive Summary

**CRITICAL BLOCKER:** 879 syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

### 🔥 / (879 errors, 35 files)

**Assignee:** [TBD - Assign team lead for /]
**Priority:** P0 - IMMEDIATE  
**Deadline:** Within 48 hours

#### Files requiring fixes:
- `app/services/moneyness_historical_processor.py`: 78 errors
- `app/api/v2/sdk_signals.py`: 74 errors
- `app/services/instrument_service_client.py`: 69 errors
- `app/services/stream_abuse_protection.py`: 64 errors
- `app/api/monitoring.py`: 56 errors
- `app/core/distributed_health_manager.py`: 47 errors
- `app/services/signal_delivery_service.py`: 47 errors
- `app/services/signal_executor.py`: 39 errors
- `app/services/signal_processor.py`: 39 errors
- `app/middleware/ratelimit.py`: 34 errors
- *25 more files*: 332 errors

#### Commands to identify issues:
```bash
# Check all syntax errors in /
ruff check // --exclude signal_service_legacy

# Get detailed output for specific files
python -m py_compile //[filename].py
```

#### Acceptance criteria:
- [ ] All syntax errors resolved in /
- [ ] Files can be imported without Python syntax errors  
- [ ] Ruff check passes for //
- [ ] CI pipeline can parse all files

---


## Error Type Analysis

Understanding the types of syntax errors helps prioritize fixing approach:

### Missing Syntax (659 errors - 75.0%)

**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.

**Sample files with this error type:**
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'

### Indentation Error (194 errors - 22.1%)

**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.

**Sample files with this error type:**
- `app/api/monitoring.py:271`: SyntaxError: Unexpected indentation
- `app/api/monitoring.py:314`: SyntaxError: Unexpected indentation
- `app/api/monitoring.py:322`: SyntaxError: unindent does not match any outer indentation level

### Other Syntax (26 errors - 3.0%)

**Fix approach:** Run individual files through Python parser to identify specific issues.

**Sample files with this error type:**
- `app/api/monitoring.py:355`: SyntaxError: Invalid assignment target
- `app/api/v2/sdk_signals.py:524`: SyntaxError: Invalid annotated assignment target
- `app/brokers/broker_factory.py:318`: SyntaxError: Unparenthesized generator expression cannot be used here

