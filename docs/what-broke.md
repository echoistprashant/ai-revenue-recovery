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

No development issue has been recorded yet.
