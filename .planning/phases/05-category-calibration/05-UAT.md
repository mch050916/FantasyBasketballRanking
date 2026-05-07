---
status: complete
phase: 05-category-calibration
source:
  - 05-01-SUMMARY.md
  - 05-02-SUMMARY.md
started: 2026-04-30T18:30:00+10:00
updated: 2026-04-30T18:34:00+10:00
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. DD/TD Contribution Visibility
expected: After `python main.py`, each benchmark block should now show a compact `DD/TD contribution` section with average `DD_G`, average `TD_G`, milestone share, and dominant contribution labels, instead of forcing you to infer milestone distortion from raw player rows.
result: pass

### 2. Saved Milestone Artifacts
expected: After `python main.py`, the project should write per-benchmark milestone contribution CSVs under `diagnostics/milestone_contributions`, and those artifacts should separate `DD` from `TD` instead of collapsing them into one generic signal.
result: pass

### 3. Separate DD and TD Calibration
expected: The final model should apply bounded but separate calibration paths for `DD` and `TD`, with `TD` remaining the more strongly compressed of the two rather than sharing one blunt reduction path.
result: pass

### 4. Exact-League-First Acceptance
expected: The Phase 5 rerun summary should make it clear that the exact-league 14-cat snapshots are the primary acceptance surface, even if secondary Yahoo-style benchmarks move differently.
result: pass

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
