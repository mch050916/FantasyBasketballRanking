---
phase: 11-breakout-and-availability-diagnostics
plan: 01
subsystem: diagnostics
tags: [breakout, availability, classification, validation, unittest]
requires: []
provides:
  - Deterministic breakout/availability classifier over the locked label set
  - Per-benchmark breakout/availability diagnostic artifact builder
affects: [validate-py, diagnostics, phase-11]
tech-stack:
  added: []
  patterns: [deterministic evidence-based classification, per-benchmark saved-ready artifact]
key-files:
  modified: [validate.py, tests/test_validate.py]
key-decisions:
  - "Classify on rank delta, miss bucket, GP/MIN/GP_FACTOR availability signal, and a simple multicategory role-growth score rather than adding a new evidence universe"
  - "Reuse the existing category-distortion family classifier for context instead of duplicating distortion logic"
patterns-established:
  - "classify_breakout_availability emits only the five locked labels: breakout underreaction, role-growth underreaction, availability overtrust, availability undertrust, unclear"
  - "build_breakout_availability_artifact mirrors the existing top-miss/category-distortion artifact shape: sorted by |delta|, capped at top_n, stable empty-frame fallback"
requirements-completed: [BAV-01, BAV-02]
duration: n/a (resumed from a prior interrupted session; classifier/artifact code already existed uncommitted)
completed: 2026-08-12
---

# Phase 11 Plan 01 Summary

**Exact-league misses can now be classified as breakout underreaction, role-growth underreaction, availability overtrust, availability undertrust, or unclear, from existing pipeline evidence.**

## Accomplishments

- Added `_role_signal_score`, `_availability_signal`, `_diagnostic_reason`, and `classify_breakout_availability` to [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) — a deterministic classifier driven by rank delta, `GP`/`MIN`/`GP_FACTOR`, and a simple multicategory role-growth score.
- Added `build_breakout_availability_artifact` and `summarize_breakout_availability_labels` to build a per-benchmark saved-ready diagnostic artifact with richer context (`ROLE_SIGNAL_SCORE`, `AVAILABILITY_SIGNAL`, `DIAGNOSTIC_REASON`, `DISTORTION_FAMILY`) than the compact top-miss artifact.
- Added focused unit tests in [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py): `test_classify_breakout_availability_emits_only_locked_labels`, `test_build_breakout_availability_artifact_keeps_context_compact` (covers a role-growth case, an availability case, and empty-result handling).

## Verification

- `python -m unittest discover -s tests` — 70 tests, all passing.

## Result

- Validation rows can now be assigned a stable, deterministic breakout/availability diagnostic label from evidence already present in the pipeline (no new evidence universe, no model/projection changes).
- The artifact composes with, and does not replace, the existing top-miss, milestone-contribution, and category-distortion artifacts.

## Notes

- This plan's classifier and artifact code was found already implemented (uncommitted) from an earlier interrupted session; this pass added the missing test coverage required by the plan's acceptance criteria and confirmed the existing implementation satisfies them.
