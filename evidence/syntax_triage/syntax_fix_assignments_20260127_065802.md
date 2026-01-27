# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** 2026-01-27 06:58
**Total Syntax Errors:** 335
**Files Affected:** 27
**Modules Affected:** 1

## Executive Summary

**CRITICAL BLOCKER:** 335 syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

### 🔥 / (335 errors, 27 files)

**Assignee:** [TBD - Assign team lead for /]
**Priority:** P0 - IMMEDIATE  
**Deadline:** Within 48 hours

#### Files requiring fixes:
- `app/core/health_checker.py`: 31 errors
- `app/api/v2/email_webhook.py`: 27 errors
- `app/utils/redis.py`: 26 errors
- `app/services/broker_symbol_converter.py`: 25 errors
- `app/api/v2/historical.py`: 24 errors
- `app/api/v2/admin.py`: 22 errors
- `app/services/timeframe_cache_manager.py`: 21 errors
- `app/clients/alert_service_client.py`: 18 errors
- `app/clients/comms_service_client.py`: 18 errors
- `app/middleware/entitlement_middleware.py`: 18 errors
- *17 more files*: 105 errors

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

### Missing Syntax (237 errors - 70.7%)

**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.

**Sample files with this error type:**
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'

### Indentation Error (71 errors - 21.2%)

**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.

**Sample files with this error type:**
- `app/api/v2/admin.py:374`: SyntaxError: Expected an indented block after `try` statement
- `app/api/v2/admin.py:377`: SyntaxError: Unexpected indentation
- `app/api/v2/admin.py:397`: SyntaxError: Unexpected indentation

### Other Syntax (27 errors - 8.1%)

**Fix approach:** Run individual files through Python parser to identify specific issues.

**Sample files with this error type:**
- `app/brokers/broker_factory.py:318`: SyntaxError: Unparenthesized generator expression cannot be used here
- `app/brokers/broker_factory.py:319`: SyntaxError: Unparenthesized generator expression cannot be used here
- `app/clients/user_service_client.py:54`: Missing explicit `return` at the end of function able to return non-`None` value

