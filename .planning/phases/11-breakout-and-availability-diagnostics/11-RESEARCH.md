---
phase: 11
slug: breakout-and-availability-diagnostics
status: complete
created: 2026-07-03
---

# Phase 11 Research — Breakout And Availability Diagnostics

## Objective

Identify the cleanest way to add breakout and availability diagnostics without changing projection logic in this phase.

## Evidence Reviewed

- [11-CONTEXT.md](/Users/chesterman/FantasyBasketballRanking/.planning/phases/11-breakout-and-availability-diagnostics/11-CONTEXT.md)
- [PROJECT.md](/Users/chesterman/FantasyBasketballRanking/.planning/PROJECT.md)
- [REQUIREMENTS.md](/Users/chesterman/FantasyBasketballRanking/.planning/REQUIREMENTS.md)
- [ROADMAP.md](/Users/chesterman/FantasyBasketballRanking/.planning/ROADMAP.md)
- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py)
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py)
- [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py)
- [diagnostics/top_misses](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses)
- [diagnostics/category_distortions](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions)
- [diagnostics/milestone_contributions](/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions)

## Key Findings

### 1. The validation layer already has the correct integration point

[validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) already builds:

- compact top-miss artifacts
- deterministic miss buckets
- DD/TD milestone contribution artifacts
- category-distortion family artifacts
- cross-benchmark category-distortion summaries

Phase 11 can follow this existing pattern by adding a separate breakout/availability diagnostic artifact rather than expanding older artifacts beyond their intended scope.

### 2. The new diagnostic should attach after top misses are known

The current `validate()` function already merges predicted rankings with benchmark ranks, computes `delta`, builds top misses, and attaches context columns from the ranking DataFrame.

That means the new artifact can be built from `result["details"]` after `delta` exists, using the same `top_n_misses` boundary as the current top-miss artifact.

### 3. Current artifacts are useful but not deep enough alone

The existing top-miss artifact includes:

- `PLAYER_NAME`
- `RANK`
- `ACTUAL_RANK`
- `delta`
- `MISS_BUCKET`
- compact context like `GP_FACTOR`, `PTS`, `REB`, `AST`, `DD`, `TD`, `TECH`, and `TOTAL_VALUE`

For Phase 11, the saved artifact should add richer context required by the locked decisions:

- `GP`
- `MIN`
- `GP_FACTOR`
- rank delta
- miss bucket
- category-distortion family when available
- growth cues derived from available projected/recent context where practical
- a deterministic breakout/availability label
- a short reason string suitable for console examples

### 4. `main.py` already has the artifact save and summary shape

[main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already saves diagnostic artifacts under stable directories and prints compact cross-benchmark summaries after validation.

Phase 11 should mirror this shape:

- `diagnostics/breakout_availability/{benchmark_slug}_breakout_availability.csv`
- `diagnostics/breakout_availability/breakout_availability_summary.csv`
- a compact `Breakout / Availability Summary` block in normal `python main.py` output

### 5. Tests should stay concentrated in `tests/test_validate.py`

The phase is diagnostic and validation-facing. Unless implementation unexpectedly touches model code, focused coverage belongs in [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py).

The important test behaviors are:

- classification labels are deterministic
- availability overtrust and undertrust are distinguishable
- breakout underreaction and role-growth underreaction are distinguishable
- the per-benchmark artifact keeps rich saved context
- the cross-benchmark summary preserves exact-league primary and Yahoo secondary semantics

## Recommended Phase Shape

### Plan 11-01

Build the classifier and per-benchmark artifact in [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py), with focused tests in [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py).

### Plan 11-02

Wire artifact saving and cross-benchmark summary reporting through [main.py](/Users/chesterman/FantasyBasketballRanking/main.py), then rerun the full pipeline to confirm the diagnostics appear without replacing existing miss buckets, DD/TD contribution, or category-distortion output.

## Risks

- Classification could become too clever and start acting like a model change. Keep it diagnostic only.
- Missing growth inputs may make some labels noisy. Use `unclear` when evidence is insufficient.
- Console output could become crowded. Keep examples compact and put detail in CSV artifacts.
- Summary logic must preserve exact-league primary handling instead of letting Yahoo-only signals dominate the phase.

## Research Conclusion

Phase 11 should be planned as two sequential plans:

1. classifier and per-benchmark artifact
2. saved artifact plus cross-benchmark and console integration

That shape reuses the existing diagnostic pipeline, keeps the phase strictly non-modeling, and leaves durable evidence for Phase 12 and Phase 13.
