---
phase: 02
slug: broad-category-calibration
status: complete
created: 2026-05-10
---

# Phase 02 Research — Broad Category Calibration

## Objective

Identify the most credible calibration levers for the repeat-supported exact-league distortion families from Phase 1, while keeping the benchmark deltas interpretable and the core DURANT pipeline intact.

## Evidence Reviewed

- [02-CONTEXT.md](/Users/chesterman/FantasyBasketballRanking/.planning/phases/02-broad-category-calibration/02-CONTEXT.md)
- [category_distortion_summary.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions/category_distortion_summary.csv)
- [actual_14cat_24_25_snapshot_csv_category_distortions.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions/actual_14cat_24_25_snapshot_csv_category_distortions.csv)
- [actual_14cat_23_24_snapshot_csv_category_distortions.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/category_distortions/actual_14cat_23_24_snapshot_csv_category_distortions.csv)
- [model.py](/Users/chesterman/FantasyBasketballRanking/model.py)
- [config.py](/Users/chesterman/FantasyBasketballRanking/config.py)

## Key Findings

### 1. `milestone carry` is still the dominant repeat-supported exact-league family

The current cross-benchmark summary shows:

- `milestone carry`: `10` primary hits across `2` exact-league snapshots
- `balanced category carry`: `2` primary hits across `2` exact-league snapshots
- `guard creation carry`: `secondary_only`

Representative `milestone carry` players remain:

- `Nikola Vučević`
- `Josh Hart`
- `Trae Young`
- `LeBron James`
- `Bam Adebayo`

This is enough evidence to justify a first-pass calibration focused squarely on the remaining milestone-shape distortion.

### 2. The model already has a clean milestone calibration hook

[model.py](/Users/chesterman/FantasyBasketballRanking/model.py) already exposes:

- `calibrate_milestone_value()`
- `calibrate_category_values()`

[config.py](/Users/chesterman/FantasyBasketballRanking/config.py) already exposes:

- `LEAGUE_CONFIG["milestone_calibration"]`
- `LEAGUE_CONFIG["category_weights"]["DD"]`
- `LEAGUE_CONFIG["category_weights"]["TD"]`

This means Phase 2 does not need a new architecture. It can stay within the existing bounded-transform plus selective-weight model the user already approved.

### 3. `balanced category carry` is real but currently narrow

The repeat-supported exact-league `balanced category carry` family currently resolves to the same representative example in both exact-league artifacts:

- `Toumani Camara`

That matters in two ways:

- it is still repeat-supported on the primary surface, so it should not be ignored
- but it is too narrow right now to justify a blind broad category rewrite before we see what the milestone pass changes

This supports an evidence-gated second plan:

- rerun after milestone calibration
- reassess residual `balanced category carry`
- only then apply a targeted follow-up adjustment if it still repeats clearly

### 4. The safest acceptance gate remains exact-league ordering quality first

The project already has:

- per-benchmark baseline history in [benchmark_history.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/benchmark_history.csv)
- top-miss artifacts
- milestone contribution artifacts
- category distortion artifacts

That existing loop is strong enough to judge the phase without inventing a new evaluation surface.

## Recommended Phase Shape

### Plan 02-01

Calibrate the remaining `milestone carry` distortion using:

- bounded `DD`/`TD` transform adjustments in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py)
- only if needed, selective follow-up weight changes in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py)

### Plan 02-02

Rerun the exact-league benchmark loop, inspect residual family movement, and apply a narrow follow-up calibration for `balanced category carry` only if the family still repeats materially after the milestone pass.

## Risks

- Over-correcting `DD`/`TD` can erase meaningful custom-league signal rather than just reducing distortion.
- Bundling milestone and balanced-category changes together would make benchmark movement harder to interpret.
- Treating `balanced category carry` as broad when the current exact-league evidence is effectively one repeated player could produce a noisy fix.

## Research Conclusion

Phase 2 should be planned as two sequential plans:

1. bounded `milestone carry` recalibration first
2. residual `balanced category carry` reassessment and targeted follow-up second

That shape matches the evidence, preserves explainability, and keeps exact-league deltas interpretable.
