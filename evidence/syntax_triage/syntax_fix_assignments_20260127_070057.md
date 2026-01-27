# 🚨 P0 CRITICAL: Syntax Error Fix Assignments

**Generated:** 2026-01-27 07:00
**Total Syntax Errors:** 107
**Files Affected:** 18
**Modules Affected:** 1

## Executive Summary

**CRITICAL BLOCKER:** 107 syntax errors are blocking all CI merges. These are actual code problems requiring immediate manual fix - they cannot be auto-resolved.

## Module Assignments

### 🔥 / (107 errors, 18 files)

**Assignee:** [TBD - Assign team lead for /]
**Priority:** P0 - IMMEDIATE  
**Deadline:** Within 48 hours

#### Files requiring fixes:
- `app/services/external_function_executor.py`: 17 errors
- `app/services/premium_discount_calculator.py`: 17 errors
- `app/core/auth/gateway_trust.py`: 15 errors
- `app/services/universal_calculator.py`: 15 errors
- `app/repositories/signal_repository.py`: 13 errors
- `app/api/health.py`: 7 errors
- `app/core/dashboard_registrar.py`: 7 errors
- `app/api/v2/email_webhook.py`: 2 errors
- `app/brokers/broker_factory.py`: 2 errors
- `app/services/clustering_indicators_temp.py`: 2 errors
- *8 more files*: 10 errors

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

### Missing Syntax (82 errors - 76.6%)

**Fix approach:** Add missing colons after if/for/def statements, close parentheses and brackets.

**Sample files with this error type:**
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'
- `app/api/health.py:178`: SyntaxError: Expected ',', found '<<'

### Other Syntax (14 errors - 13.1%)

**Fix approach:** Run individual files through Python parser to identify specific issues.

**Sample files with this error type:**
- `app/api/v2/email_webhook.py:45`: Undefined name `expected_secret`
- `app/api/v2/email_webhook.py:45`: Undefined name `expected_secret`
- `app/brokers/broker_factory.py:318`: SyntaxError: Unparenthesized generator expression cannot be used here

### Indentation Error (11 errors - 10.3%)

**Fix approach:** Check for mixed tabs/spaces, incorrect indentation levels, missing indentation after colons.

**Sample files with this error type:**
- `app/core/auth/gateway_trust.py:140`: SyntaxError: Unexpected indentation
- `app/services/clustering_indicators_temp.py:360`: SyntaxError: Expected an indented block after `if` statement
- `app/services/clustering_indicators_temp.py:418`: SyntaxError: Expected an indented block after `if` statement

