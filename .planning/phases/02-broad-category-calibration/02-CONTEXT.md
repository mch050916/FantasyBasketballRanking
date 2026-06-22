# Phase 02 Context — Broad Category Calibration

## Goal

Recalibrate the ranking model’s remaining broad category-balance distortions using the new exact-league-first family evidence from Phase 1, while keeping the existing benchmark and miss-diagnostic loop intact.

## Decisions Locked

- Use the saved category-distortion family evidence from Phase 1 as the calibration guide, with the two exact-league historical snapshot benchmarks as the **primary acceptance surface**.
- Follow a **strict priority order** for family targeting:
  1. `milestone carry`
  2. `balanced category carry`
  3. revisit secondary-only families later only if needed
- Use a **mixed adjustment surface**:
  - bounded transforms in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py)
  - selective weight adjustments in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py)
- Tune **one family at a time**, not as one bundled rebalance pass.
- Judge success primarily by **exact-league ordering quality**, with MAE as supporting evidence and Yahoo outputs as secondary sanity checks only.
- Treat `guard creation carry` as **monitor only** in this phase; do not target it directly unless it improves incidentally as a side effect of the primary family work.

## Current Evidence

- The current cross-benchmark summary in [category_distortion_summary.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions/category_distortion_summary.csv) shows:
  - `milestone carry` as a repeat-supported exact-league family
  - `balanced category carry` as a repeat-supported exact-league family
  - `guard creation carry` as `secondary_only`
- Phase 5 already reduced the most obvious `DD` and `TD` distortion, but the remaining repeated family still clusters under `milestone carry`, which suggests there is still broader contribution-shape or weighting work left beyond the earlier milestone-specific compression.
- The exact-league validation surface remains the real target:
  - [actual_14cat_24_25_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_24_25_snapshot.csv)
  - [actual_14cat_23_24_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_23_24_snapshot.csv)

## Constraints

- Stay within the current Python CLI pipeline.
- Preserve the benchmark and miss-diagnostic loop rather than inventing a new evaluation path.
- Keep the work interpretable: later calibration decisions should be explainable from saved artifacts, not only from aggregate metrics.
- Avoid bundling multiple family calibrations together in a way that makes benchmark movement ambiguous.

## Expected Focus

- First, tune the remaining `milestone carry` distortion in a bounded, measurable way.
- Then assess whether `balanced category carry` still needs direct follow-up work or whether the first pass already reduced it incidentally.
- Keep exact-league snapshot improvement as the acceptance gate, while watching Yahoo outputs only for obvious regressions or sanity-check failures.

## Existing Code Insights

### Reusable Assets

- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py): now exposes family-level distortion artifacts and cross-benchmark summaries.
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py): already persists category-distortion artifacts and prints exact-league-first summary output.
- [config.py](/Users/chesterman/FantasyBasketballRanking/config.py): the natural home for any light category-weight changes.
- [model.py](/Users/chesterman/FantasyBasketballRanking/model.py): the natural home for bounded contribution transforms or compression behavior.
- [diagnostics/category_distortions](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions): the main evidence surface for deciding whether the target family actually shrank.

### Established Patterns

- Calibration changes should rerun the full benchmark surface and compare current results against saved baselines.
- Exact-league snapshots are the primary acceptance target whenever league-specific tuning is in scope.
- Heuristic tuning stays bounded and explainable instead of rewriting the core DURANT pipeline.

### Integration Points

- The most likely implementation surface is a combination of [model.py](/Users/chesterman/FantasyBasketballRanking/model.py), [config.py](/Users/chesterman/FantasyBasketballRanking/config.py), and the existing validation output in [main.py](/Users/chesterman/FantasyBasketballRanking/main.py).
- The category-distortion artifacts from Phase 1 should remain the evidence layer for deciding whether a calibration pass actually improved the targeted family.
