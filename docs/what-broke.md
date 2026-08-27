# What Broke — Development Log

This document records real problems encountered during development of the AI Revenue Recovery & Payment Intelligence Platform.

## Purpose

The log preserves useful engineering history, including bugs, failed implementations, incorrect assumptions, architectural problems, data leakage, test failures, integration failures, model issues, LLM boundary failures, security issues, dead ends, performance problems, and important lessons.

Do not fabricate problems. Record an issue only when it actually occurs and provides a meaningful lesson or requires a non-trivial response.

## Instructions

1. Assign the next sequential issue number.
2. Identify the phase and date.
3. Record observed evidence rather than speculation.
4. Describe the smallest reliable reproduction when applicable.
5. Separate root cause from symptoms.
6. Describe the actual fix and the checks proving it worked.
7. Do not remove unresolved issues merely because they are inconvenient.
8. Use `WONT_FIX` or `DEFERRED` honestly when appropriate.

## Issue Template

```markdown
## Issue #[NUMBER] — [SHORT TITLE]

### Phase

Phase X — [Phase Name]

### Date

YYYY-MM-DD

### Status

OPEN / FIXED / WONT_FIX / DEFERRED

### Severity

LOW / MEDIUM / HIGH / CRITICAL

### 1. Problem

What were we trying to do, and what went wrong?

### 2. Expected Behavior

What should have happened?

### 3. Actual Behavior

What actually happened? Include relevant errors, output, failed tests, or incorrect predictions.

### 4. Reproduction

List the smallest reliable steps required to reproduce the problem.

### 5. Root Cause

Why did the problem occur?

### 6. Fix

What was changed, or why was the issue deferred?

### 7. Verification

Which tests or checks proved the result?

### 8. Lesson

What should future development learn from this issue?
```

## Issue Log

## Issue #1 — Small Incident Window Caused a False Positive

### Phase

Phase 4 — System Intelligence and Guardrails

### Date

2026-08-27

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

The incident test classified one failure among ten events as an active systemic incident.

### 2. Expected Behavior

A small sample should not trigger gateway-wide retry suppression.

### 3. Actual Behavior

The observed 10% rate exceeded three times the 2% baseline and activated the incident rule.

### 4. Reproduction

Evaluate gateway health with one failure, ten total events, a 2% baseline, and a 3x multiplier.

### 5. Root Cause

The default minimum evidence window was only ten events, allowing normal small-sample variation to dominate the multiplier.

### 6. Fix

The minimum default incident window was increased to twenty events.

### 7. Verification

The false-positive test and incident activation/recovery tests pass within the 37-test suite.

### 8. Lesson

Rate multipliers need a minimum sample requirement; relative thresholds alone are unsafe on sparse traffic.

## Issue #2 — Nested Experiment Dataclasses Failed JSON Serialization

### Phase

Phase 6 — Experimentation Engine

### Date

2026-08-27

### Status

FIXED

### Severity

LOW

### 1. Problem

The experiment report script failed after the test suite passed.

### 2. Expected Behavior

The script should print the experiment and what-if report as JSON.

### 3. Actual Behavior

`json.dumps` raised `TypeError: Object of type VariantMetrics is not JSON serializable`.

### 4. Reproduction

Run `python scripts/run_experiment.py` with an `ExperimentResult` containing nested dataclasses.

### 5. Root Cause

Using `result.__dict__` converted only the outer dataclass. Nested `VariantMetrics` objects remained custom Python objects.

### 6. Fix

Use `dataclasses.asdict` for recursive dataclass conversion in both the report script and typed API boundary.

### 7. Verification

The script now prints valid JSON, the typed experiment endpoint validates nested response models, and the full test suite passes.

### 8. Lesson

Unit tests for calculation logic do not replace running user-facing scripts; nested serialization requires an end-to-end check.
