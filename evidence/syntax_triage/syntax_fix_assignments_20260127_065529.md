# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** 2026-01-27 06:55
**Total Syntax Errors:** 540
**Files Affected:** 31
**Modules Affected:** 1

## Executive Summary

**CRITICAL BLOCKER:** 540 syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

### 🔥 / (540 errors, 31 files)

**Assignee:** [TBD - Assign team lead for /]
**Priority:** P0 - IMMEDIATE  
**Deadline:** Within 48 hours

#### Files requiring fixes:
- `app/core/distributed_health_manager.py`: 47 errors
- `app/services/signal_delivery_service.py`: 47 errors
- `app/services/signal_executor.py`: 39 errors
- `app/services/signal_processor.py`: 39 errors
- `app/middleware/ratelimit.py`: 34 errors
- `app/core/health_checker.py`: 31 errors
- `app/api/v2/email_webhook.py`: 27 errors
- `app/utils/redis.py`: 26 errors
- `app/services/broker_symbol_converter.py`: 25 errors
- `app/api/v2/historical.py`: 24 errors
- *21 more files*: 201 errors

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

### Missing Syntax (386 errors - 71.5%)

**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.

**Sample files with this error type:**
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'

### Indentation Error (128 errors - 23.7%)

**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.

**Sample files with this error type:**
- `app/api/v2/admin.py:374`: SyntaxError: Expected an indented block after `try` statement
- `app/api/v2/admin.py:377`: SyntaxError: Unexpected indentation
- `app/api/v2/admin.py:397`: SyntaxError: Unexpected indentation

### Other Syntax (26 errors - 4.8%)

**Fix approach:** Run individual files through Python parser to identify specific issues.

**Sample files with this error type:**
- `app/brokers/broker_factory.py:318`: SyntaxError: Unparenthesized generator expression cannot be used here
- `app/brokers/broker_factory.py:319`: SyntaxError: Unparenthesized generator expression cannot be used here
- `app/clients/user_service_client.py:54`: Missing explicit `return` at the end of function able to return non-`None` value

