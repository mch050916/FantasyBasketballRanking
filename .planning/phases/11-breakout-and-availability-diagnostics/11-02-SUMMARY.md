---
phase: 11-breakout-and-availability-diagnostics
plan: 02
subsystem: diagnostics
tags: [breakout, availability, reporting, main-pipeline, unittest]
requires:
  - 11-01
provides:
  - Cross-benchmark breakout/availability summary artifact
  - Saved per-benchmark breakout/availability CSVs under diagnostics/breakout_availability/
  - Compact console "Breakout / Availability Summary" reporting in normal pipeline runs
affects: [validate-py, main-py, diagnostics, phase-11, phase-12, phase-13]
tech-stack:
  added: []
  patterns: [primary/secondary evidence rollup, additive console reporting section]
key-files:
  created: [diagnostics/breakout_availability/actual_14cat_24_25_snapshot_csv_breakout_availability.csv, diagnostics/breakout_availability/actual_14cat_23_24_snapshot_csv_breakout_availability.csv, diagnostics/breakout_availability/actual_9cat_24_25_csv_breakout_availability.csv, diagnostics/breakout_availability/yahoo_25_26_adp_proxy_breakout_availability.csv, diagnostics/breakout_availability/yahoo_25_26_live_snapshot_breakout_availability.csv, diagnostics/breakout_availability/breakout_availability_summary.csv]
  modified: [validate.py, main.py, tests/test_validate.py]
key-decisions:
  - "Mirror the existing category-distortion summary pattern exactly (evidence-level rollup, primary=exact-league snapshots, secondary=Yahoo) instead of inventing a new reporting shape"
  - "Keep the new console block strictly additive after Category Distortion Summary and before Run Health Summary so existing sections are undisturbed"
patterns-established:
  - "build_breakout_availability_summary keeps exact-league (historical_snapshot + snapshot_derived) hits under PRIMARY_HITS/PRIMARY_BENCHMARKS and Yahoo/direct-export hits under SECONDARY_HITS only"
  - "save_breakout_availability_artifact / print_breakout_availability_summary in main.py follow the same save/print helper shape as the category-distortion equivalents"
requirements-completed: [BAV-01, BAV-02]
duration: n/a (resumed from a prior interrupted session; Task 1 summary helper already existed uncommitted)
completed: 2026-08-12
---

# Phase 11 Plan 02 Summary

**Breakout/availability diagnostics are now durable and visible: saved per-benchmark CSVs, a cross-benchmark summary artifact, and a compact console block on every normal run.**

## Accomplishments

- Added `build_breakout_availability_summary` to [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) (rolls up per-benchmark artifacts across benchmarks, keeping exact-league snapshots primary and Yahoo/direct-export benchmarks secondary) and a unit test, `test_build_breakout_availability_summary_keeps_exact_league_primary`, proving Yahoo-only labels never count as primary evidence.
- Wired the new diagnostic into [main.py](/Users/chesterman/FantasyBasketballRanking/main.py):
  - `BREAKOUT_AVAILABILITY_DIR` / `BREAKOUT_AVAILABILITY_SUMMARY_FILE` path constants.
  - `save_breakout_availability_artifact` — saves each benchmark's artifact to `diagnostics/breakout_availability/{label}_breakout_availability.csv`, called alongside the existing top-miss/milestone/category-distortion saves.
  - `print_breakout_availability_summary` — prints a compact `Breakout / Availability Summary` block (label, primary/secondary hit counts, evidence level, representative players/reasons), called after the existing Category Distortion Summary block.
- Ran the full pipeline end-to-end (`python -u main.py`) against the cached game logs/TECH data; all 5 benchmark targets validated `ok`.

## Verification

- `python -m unittest discover -s tests` — 70 tests, all passing.
- `python -u main.py` — full run completed cleanly. Confirmed:
  - `diagnostics/breakout_availability/` created with one CSV per validated benchmark plus `breakout_availability_summary.csv`.
  - New `Breakout / Availability Summary` console block appears after `Category Distortion Summary` and before `Run Health Summary`.
  - Existing top-miss, DD/TD contribution, and category-distortion sections still print unchanged.
- Manual inspection of `diagnostics/breakout_availability/actual_14cat_24_25_snapshot_csv_breakout_availability.csv` and the console summary confirmed labels and reason strings read clearly (e.g. `availability undertrust — availability=very_low; GP_FACTOR=0.50` for LaMelo Ball, `role-growth underreaction — role_score=3.5; MIN=31.5` for Keyonte George).

## Result

- Both exact-league snapshots repeat multiple breakout/availability labels (`unclear`, `availability undertrust`, `availability overtrust`, `role-growth underreaction`, `breakout underreaction`), all currently at `repeat_exact_league` evidence level — this is the evidence surface Phase 12 (role-growth calibration) and Phase 13 (availability-risk calibration) will plan against.
- No projection or scoring logic was touched — Phase 11 remains diagnostic-only.

## Notes

- Plan 11-02 Task 1 (`build_breakout_availability_summary`) was found already implemented (uncommitted) from an earlier interrupted session; this pass added its test coverage and completed all of Task 2 (main.py wiring, artifact persistence, console reporting, end-to-end verification), which had not been started.
