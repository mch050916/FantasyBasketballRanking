# Phase 11 Discussion Log

**Phase:** Breakout And Availability Diagnostics  
**Date:** 2026-07-03  
**Status:** Complete

## Discussed Gray Areas

### 1. Classification labels

Decision: Use a richer compact label set.

Chosen labels:
- `breakout underreaction`
- `role-growth underreaction`
- `availability overtrust`
- `availability undertrust`
- `unclear`

Rationale: The labels separate upside misses from availability misses without becoming too granular to act on.

### 2. Evidence inputs

Decision: Use a combined evidence surface.

Included evidence:
- existing miss artifacts
- projected stats
- `GP`
- `MIN`
- `GP_FACTOR`
- year-over-year category growth
- current miss buckets
- category-distortion labels

Rationale: The diagnostics should build on existing trusted artifacts while adding the signals needed to explain breakout and availability behavior.

### 3. Primary benchmark surface

Decision: Keep exact-league snapshots primary and Yahoo secondary.

Rationale: `v1.3` should continue optimizing for the real league format, with Yahoo outputs acting as sanity checks rather than acceptance drivers.

### 4. Artifact shape

Decision: Produce all three output layers.

Required outputs:
- per-benchmark diagnostic CSVs
- a cross-benchmark summary artifact
- a compact console summary in `python main.py`

Rationale: Phase 12 and Phase 13 need durable evidence, while normal CLI runs should still expose the diagnostic pattern.

### 5. Player context depth

Decision: Compact console, richer saved artifact.

Console should show representative players and headline reasons. CSV artifacts should carry richer context such as rank delta, `GP`, `MIN`, `GP_FACTOR`, growth cues, miss bucket, and category-distortion family.

## Deferred

- Role-growth tuning is Phase 12.
- Availability-risk tuning is Phase 13.
- OCR backend enablement remains outside the current milestone.

## Next Step

`/gsd-plan-phase 11`
