---
phase: 02-broad-category-calibration
plan: 02
subsystem: validation-rerun
tags: [exact-league, rerun, residual-family, diagnostics, unittest]
requires:
  - 02-01
provides:
  - A full exact-league-first rerun judgment for the phase
  - Residual-family follow-up guidance surfaced directly in the distortion summary
  - Updated baseline, miss, milestone, and distortion artifacts
affects: [validation, diagnostics, planning-artifacts, milestone-v1.2, phase-02]
tech-stack:
  added: []
  patterns: [follow-up decision labels, evidence-gated residual family handling]
key-files:
  created: []
  modified: [validate.py, main.py, tests/test_validate.py, .planning/ROADMAP.md, .planning/REQUIREMENTS.md, .planning/PROJECT.md]
key-decisions:
  - "Treat the residual balanced-category family as `monitor_narrow` instead of forcing a broad second-pass rebalance"
  - "Keep exact-league ordering quality as the primary acceptance surface for the rerun summary"
patterns-established:
  - "Category distortion summaries now expose a follow-up decision such as `active_target` or `monitor_narrow`"
  - "Residual family handling is explicit in diagnostics instead of living only in execution notes"
requirements-completed: [CCAL-02, CCAL-03]
duration: 0min
completed: 2026-05-10
---

# Phase 02 Plan 02 Summary

**The rerun improved exact-league ordering, and the residual balanced family is now explicitly marked as monitor-only**

## Accomplishments

- Reran the full ranking and validation loop after the milestone calibration pass.
- Updated [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py), [main.py](/Users/chesterman/FantasyBasketballRanking/main.py), and [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py) so the category-distortion summary now exposes:
  - `active_target`
  - `monitor_narrow`
  - supporting follow-up states for weaker families
- Confirmed the residual `balanced category carry` family still resolves to a narrow exact-league case centered on `Toumani Camara`, so no broad second-pass recalibration was forced.
- Left behind updated artifacts in:
  - [category_distortions](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions)
  - [top_misses](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses)
  - [milestone_contributions](/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions)

## Verification

- `python -m unittest discover -s tests`
- `python -u main.py`

## Result

- Exact-league historical snapshots improved on ordering quality and slightly improved MAE:
  - `actual_14cat_24_25_snapshot.csv`: Spearman `0.665 -> 0.676`, MAE `24.1 -> 23.9`
  - `actual_14cat_23_24_snapshot.csv`: Spearman `0.616 -> 0.627`, MAE `22.5 -> 22.4`
- Yahoo-style surfaces remained healthy as sanity checks rather than collapsing under the change.
- The residual balanced-category family is now explicitly labeled `monitor_narrow`, which closes the phase honestly without forcing a noisy extra rebalance.

## Notes

- Hit rate softened on the exact-league snapshots, but Phase 2 intentionally prioritized ordering quality first. The final call stayed aligned with the milestone’s acceptance rules.
