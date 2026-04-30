---
status: complete
phase: 03-miss-diagnostics
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
started: 2026-04-30T12:00:00+10:00
updated: 2026-04-30T12:03:00+10:00
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Baseline Delta Loop
expected: Running `python main.py` twice should create `diagnostics/benchmark_history.csv` on the first run, then on the second run each benchmark should print a compact baseline-delta block using its own previous saved metrics instead of the first-run placeholder.
result: pass

### 2. Saved Top-Miss Artifacts
expected: After `python main.py`, each active benchmark target should write a top-miss CSV under `diagnostics/top_misses/`, and those files should contain compact miss context like `GP_FACTOR`, `PTS`, `REB`, `AST`, `DD`, `TD`, `TECH`, and `TOTAL_VALUE` instead of a full category dump.
result: pass

### 3. Miss Bucket Summary
expected: The validation output should include a compact miss-bucket summary per benchmark, using the approved heuristic labels so the dominant error mode is visible without opening the CSV.
result: pass

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
