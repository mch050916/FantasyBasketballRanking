# Phase 4 Discussion Log

**Date:** 2026-04-30  
**Phase:** 04 — Projection Signal Upgrades

## Decisions Captured

### Trend signals
- Chosen: broad multicategory trend score
- Shape: single composite score
- Inputs: `PTS`, `AST`, `REB`, `3PTM`, `ST`, `BLK`, `MIN`

### Decline model
- Chosen: light age-based decline penalty with performance confirmation
- Rationale: catch over-carried veterans without blindly fading still-elite older players

### Role-change detection
- Chosen: extra role-change boost on top of the composite trend score
- Rationale: role growth should be strong enough to help catch breakout profiles, not just be a weak ingredient in the composite

### Conservatism vs responsiveness
- Chosen: moderately responsive
- Rationale: stronger than the current model, but still capped so one recent season cannot fully dominate

## Deferred

- no per-category trend system in this phase
- no highly aggressive breakout weighting
- no standalone category-calibration work in this phase
