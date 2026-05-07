---
phase: 08-nba-api-resolution-hardening
plan: 01
subsystem: nba-api-resolution
tags: [data-resolution, classification, deterministic-matching, unittest]
requires: []
provides:
  - Explicit classification for non-actionable unresolved player-season misses
  - Narrow suppression boundaries for known current-season inactive returnees
  - Regression tests for deterministic resolution and severity bucketing
affects: [data-fetching, run-health, phase-08]
tech-stack:
  added: []
  patterns: [narrow non-actionable classification, severity-aware fetch health]
key-files:
  created: []
  modified: [data.py, tests/test_data.py]
key-decisions:
  - "Keep current-season failures severe by default and suppress only narrow explicitly classified non-actionable cases"
  - "Use explicit pair-level non-actionable reasons instead of broad retry exhaustion suppression"
patterns-established:
  - "Run health now distinguishes actionable unresolved misses from known non-actionable current-season returnees"
  - "Deterministic source overrides remain the first identity recovery step, with classification layered after that"
requirements-completed: [DRES-01, DRES-02]
duration: 0min
completed: 2026-05-07
---

# Phase 08 Plan 01 Summary

**The NBA API fetch layer now treats real unresolved misses and narrow non-actionable cases as different things**

## Accomplishments

- Extended [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) with explicit missing-pair classification helpers.
- Added narrow current-season non-actionable classifications for:
  - `Bojan Bogdanović (2024-25)`
  - `Saddiq Bey (2024-25)`
- Kept deterministic player resolution intact and added test coverage for the existing `Jimmy Butler -> Jimmy Butler III` source override path.
- Expanded [tests/test_data.py](/Users/chesterman/FantasyBasketballRanking/tests/test_data.py) to cover:
  - deterministic source overrides
  - current-season vs historical missing severity
  - explicit non-actionable reason classification
  - richer fetch-health accounting

## Verification

- `python -m unittest discover -s tests`

## Result

- The fetch layer no longer treats every remaining missing pair as equally degraded.
- Known inactive current-season returnees can now be suppressed narrowly and explicitly instead of inflating degraded counts.
- Actionable unresolved misses are still preserved in the health payload for honest reporting.

## Notes

- This plan intentionally keeps the non-actionable bucket narrow. It does not create a general-purpose “known failures” escape hatch.
