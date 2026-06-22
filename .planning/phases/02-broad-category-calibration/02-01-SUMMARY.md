---
phase: 02-broad-category-calibration
plan: 01
subsystem: model-calibration
tags: [milestone-carry, bounded-calibration, exact-league, unittest]
requires: []
provides:
  - A tighter bounded milestone calibration path for the dominant exact-league distortion family
  - Updated DD and TD weights aligned with the first-pass calibration target
  - Regression coverage for stronger high-end milestone compression
affects: [model, config, benchmark-quality, milestone-v1.2, phase-02]
tech-stack:
  patterns: [bounded milestone recalibration, exact-league-first heuristic tuning]
key-files:
  created: []
  modified: [model.py, config.py, tests/test_model.py]
key-decisions:
  - "Tighten the existing milestone transform and weight hooks instead of adding a new scoring subsystem"
  - "Prefer the candidate that improves exact-league ordering quality and MAE even if hit rate softens"
patterns-established:
  - "High-end milestone values now compress more strongly while preserving ordering and non-zero league value"
  - "Phase 2 calibration remains inside the existing config-plus-model hook pattern"
requirements-completed: [CCAL-01]
duration: 0min
completed: 2026-05-10
---

# Phase 02 Plan 01 Summary

**The dominant exact-league `milestone carry` family now has a stronger bounded calibration pass**

## Accomplishments

- Tightened milestone calibration in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py) using the existing bounded transform path:
  - `DD`: stronger compression plus a modest weight trim
  - `TD`: stronger compression plus a larger weight trim
- Kept the work within the existing hooks already exposed by [model.py](/Users/chesterman/FantasyBasketballRanking/model.py), rather than introducing any new scoring subsystem.
- Expanded [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) with regression coverage for:
  - stronger high-end milestone compression
  - non-milestone categories remaining untouched
  - DD and TD continuing to calibrate separately and monotonically

## Verification

- `python -m unittest discover -s tests`

## Result

- The model now applies a stronger first-pass reduction to the remaining repeat-supported milestone distortion.
- The calibration stays bounded and explainable instead of flattening the custom-league milestone categories into irrelevance.
- Phase 2 stayed aligned with the exact-league-first evidence surface when choosing the calibration candidate.

## Notes

- This first pass intentionally focused only on `milestone carry`. It did not force a second family adjustment before the rerun evidence was available.
