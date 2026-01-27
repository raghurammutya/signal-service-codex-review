# Ruff Violation Triage Report

## Executive Summary
**Generated:** 2026-01-27T06:16:07.439158
**Total Violations:** 7,087
**Files Affected:** 327
**Unique Rule Types:** 42

## Priority Categories

### 🚨 **Critical** - P0 - IMMEDIATE
**Total:** 109 violations

- **F821** (undefined-name): 79 (1.1%)
- **F401** (unused-import): 21 (0.3%)
- **F402** (import-shadowed-by-loop-var): 9 (0.1%)

### ⚡ **Imports** - P1 - HIGH
**Total:** 141 violations

- **UP035** (deprecated-import): 121 (1.7%)
- **E402** (module-import-not-at-top-of-file): 20 (0.3%)

### ⚡ **Formatting** - P1 - HIGH
**Total:** 3,766 violations

- **W293** (blank-line-with-whitespace): 3,514 (49.6%)
- **W291** (trailing-whitespace): 229 (3.2%)
- **W292** (missing-newline-at-end-of-file): 23 (0.3%)

### ⚠️ **Typing** - P2 - MEDIUM
**Total:** 49 violations

- **UP006** (non-pep585-annotation): 46 (0.6%)
- **UP045** (non-pep604-annotation-optional): 3 (0.0%)

### ⚠️ **Error_Handling** - P2 - MEDIUM
**Total:** 248 violations

- **B904** (raise-without-from-inside-except): 172 (2.4%)
- **E722** (bare-except): 37 (0.5%)
- **B905** (zip-without-explicit-strict): 25 (0.4%)
- **B017** (assert-raises-exception): 13 (0.2%)
- **B011** (assert-false): 1 (0.0%)

### 📋 **Code_Quality** - P3 - LOW
**Total:** 303 violations

- **F841** (unused-variable): 101 (1.4%)
- **B007** (unused-loop-control-variable): 98 (1.4%)
- **RET504** (unnecessary-assign): 89 (1.3%)
- **PIE810** (multiple-starts-ends-with): 12 (0.2%)
- **RET503** (implicit-return): 2 (0.0%)

### 📋 **Complexity** - P3 - LOW
**Total:** 253 violations

- **SIM117** (multiple-with-statements): 158 (2.2%)
- **SIM102** (collapsible-if): 48 (0.7%)
- **SIM105** (suppressible-exception): 20 (0.3%)
- **SIM103** (needless-bool): 13 (0.2%)
- **SIM108** (if-else-block-instead-of-if-exp): 9 (0.1%)

### 📋 **Style** - P3 - LOW
**Total:** 41 violations

- **E712** (true-false-comparison): 20 (0.3%)
- **N805** (invalid-first-argument-name-for-method): 15 (0.2%)
- **E721** (type-comparison): 2 (0.0%)
- **E741** (ambiguous-variable-name): 2 (0.0%)
- **N818** (error-suffix-on-exception-name): 2 (0.0%)

### 📋 **Uncategorized** - P3 - LOW
**Total:** 2,177 violations

- **** (unknown): 2,144 (30.3%)
- **SIM118** (unknown): 14 (0.2%)
- **B023** (unknown): 7 (0.1%)
- **SIM110** (unknown): 3 (0.0%)
- **B006** (unknown): 2 (0.0%)

## Module Breakdown

Top modules by violation count:

- **/**: 7,087 violations (100.0%)


## Remediation Strategy

### Phase 1: Critical Issues (P0) 
Target completion: 1 week
- Fix F821: 79 occurrences
- Fix F401: 21 occurrences
- Fix F402: 9 occurrences

### Phase 2: Quick Wins (P1)
Target completion: 2 weeks  
- Imports: 141 violations (auto-fixable)
- Formatting: 3,766 violations (auto-fixable)

### Phase 3: Quality Improvements (P2-P3)
Target completion: 1 month
- Typing: 49 violations
- Error_Handling: 248 violations
- Code_Quality: 303 violations
- Complexity: 253 violations
- Style: 41 violations


## Detailed Module Analysis

### / (7,087 violations)

Top rules:
- W293: 3,514
- invalid-syntax: 2,144
- W291: 229
- B904: 172
- SIM117: 158

