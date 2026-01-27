# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** 2026-01-27 07:01
**Total Syntax Errors:** 19
**Files Affected:** 14
**Modules Affected:** 1

## Executive Summary

**CRITICAL BLOCKER:** 19 syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

### 🔥 / (19 errors, 14 files)

**Assignee:** [TBD - Assign team lead for /]
**Priority:** P0 - IMMEDIATE  
**Deadline:** Within 48 hours

#### Files requiring fixes:
- `app/api/v2/email_webhook.py`: 2 errors
- `app/brokers/broker_factory.py`: 2 errors
- `app/services/clustering_indicators_temp.py`: 2 errors
- `app/services/instrument_service_client.py`: 2 errors
- `tests/unit/test_optional_dependencies_computation_errors.py`: 2 errors
- `app/api/health.py`: 1 errors
- `app/clients/user_service_client.py`: 1 errors
- `app/core/dashboard_registrar.py`: 1 errors
- `app/repositories/signal_repository.py`: 1 errors
- `app/services/signal_delivery_service.py`: 1 errors
- *4 more files*: 4 errors

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

### Other Syntax (15 errors - 78.9%)

**Fix approach:** Run individual files through Python parser to identify specific issues.

**Sample files with this error type:**
- `app/api/v2/email_webhook.py:45`: Undefined name `expected_secret`
- `app/api/v2/email_webhook.py:45`: Undefined name `expected_secret`
- `app/brokers/broker_factory.py:318`: SyntaxError: Unparenthesized generator expression cannot be used here

### Missing Syntax (2 errors - 10.5%)

**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.

**Sample files with this error type:**
- `app/api/health.py:178`: SyntaxError: unexpected EOF while parsing
- `app/core/dashboard_registrar.py:81`: SyntaxError: unexpected EOF while parsing

### Indentation Error (2 errors - 10.5%)

**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.

**Sample files with this error type:**
- `app/services/clustering_indicators_temp.py:360`: SyntaxError: Expected an indented block after `if` statement
- `app/services/clustering_indicators_temp.py:418`: SyntaxError: Expected an indented block after `if` statement

