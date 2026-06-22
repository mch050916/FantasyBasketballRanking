---
status: complete
phase: 02-broad-category-calibration
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md
started: 2026-05-10T03:26:27Z
updated: 2026-05-10T03:30:52Z
---

## Current Test

[testing complete]

## Tests

### 1. Exact-League-First Rerun Outcome
expected: After `python main.py`, the two exact-league 14-cat snapshots should read like the primary acceptance surface for the phase. The important behavior is that both snapshot blocks show stronger ordering quality than the pre-Phase-2 baseline, with the rerun clearly framed as an exact-league-first calibration judgment rather than a Yahoo-driven one.
result: pass

### 2. Bounded Milestone Carry Reduction
expected: The updated run should still show `DD/TD contribution` diagnostics, but the dominant milestone-driven distortion should feel more controlled rather than flattened away. This means the milestone-carry problem remains visible and explainable, while exact-league ordering improves instead of collapsing.
result: pass

### 3. Residual Family Stays Evidence-Gated
expected: The `Category Distortion Summary` should explicitly surface the residual `balanced category carry` family as a narrow monitor case, not as a forced broad recalibration target. The important behavior is that `milestone carry` remains the active target and the balanced family is labeled as monitor-only or equivalent.
result: pass

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
