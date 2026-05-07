## User Constraints

### Implementation Decisions

- **D-01:** Prioritize exact-league 14-cat historical snapshots over Yahoo-style benchmarks when judging calibration success.
- **D-02:** Use weight + scaling calibration, not a weight-only tweak and not a full scoring rewrite.
- **D-03:** Calibrate `DD` and `TD` separately.
- **D-04:** Use Yahoo benchmarks only as secondary sanity checks.

### The Agent's Discretion

- Exact compression or scaling function for `DD`.
- Exact compression or scaling function for `TD`.
- Whether weight changes are needed in addition to scaling changes.
- Exact reporting artifact shape for showing `DD`/`TD` contribution and distortion.

### Deferred Ideas

- Full DURANT scoring-formula rewrite.
- Adding new data sources for milestone stats.
- General category reweighting beyond `DD` and `TD`.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Preserve the DURANT framework and current benchmark loop.
- Keep behavior deterministic and explainable.
- Calibrate from evidence using the saved diagnostics, not intuition alone.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `numpy`, and `unittest` remain sufficient for this phase. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- `derive_stats_from_logs()` in [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) currently sets `DD` and `TD` from the most recent available season only, using `DD2/gp` and `TD3/gp`. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `project_stats()` in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) carries those `DD` and `TD` rates directly into projections with `GP_FACTOR` and `DECLINE_FACTOR`, but no extra compression or special calibration. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- `compute_g_scores()` in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) treats `DD` and `TD` like other positive counting categories: Box-Cox/log transform, player tau, clipping, then category weighting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- Current configured weights in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py) are `DD: 0.8` and `TD: 0.8`, already reduced from a higher prior setting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/config.py]

## Don't Hand-Roll

- Do not optimize primarily for Yahoo-market agreement; exact-league historical snapshots are the main target. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/05-category-calibration/05-CONTEXT.md]
- Do not collapse `DD` and `TD` into one shared calibration path; they are intentionally separate. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/05-category-calibration/05-CONTEXT.md]
- Do not rewrite the whole scoring system when a local `DD`/`TD` scaling path can address the observed distortion. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/05-category-calibration/05-CONTEXT.md]

## Common Pitfalls

- `DD` and `TD` are sparse event-rate categories with many zeros, so even modest rate differences can separate players sharply after transformation and weighting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- Because `derive_stats_from_logs()` uses the most recent season only, spike seasons in `DD`/`TD` are not naturally smoothed by a multi-season projection blend. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- Current diagnostics can show category-weight distortion, but they do not yet isolate how much `DD_G` or `TD_G` contributed to a miss. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]

## Evidence From Current Miss Artifacts

- [actual_14cat_24_25_snapshot_csv_top_misses.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses/actual_14cat_24_25_snapshot_csv_top_misses.csv) shows `category-weight distortion` for `Nikola Vučević` and `Josh Hart`, both with meaningful `DD` contribution. [VERIFIED]
- [yahoo_25_26_adp_proxy_top_misses.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses/yahoo_25_26_adp_proxy_top_misses.csv) shows `category-weight distortion` for `Jayson Tatum` and `Tyrese Haliburton`, indicating the issue is not limited to one player archetype. [VERIFIED]
- Phase 4 improved projection signals, but the benchmark history still leaves `DD`/`TD` distortion as one of the remaining high-signal miss drivers. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/diagnostics/benchmark_history.csv]

## Validation Architecture

- Plan 1 should make `DD`/`TD` contribution visible enough to justify calibration changes against the exact-league benchmarks.
- Plan 2 should adjust scaling and possibly weights, then judge the result through the existing benchmark history and top-miss artifacts.
- Continue automated verification with `python -m unittest discover -s tests`, plus `python -u main.py` after the calibration changes land.

## Planning Notes

- The cleanest split remains:
  1. add `DD`/`TD` contribution analysis and distortion visibility;
  2. calibrate `DD` and `TD` separately with bounded scaling/weight changes and rerun the benchmarks.
- The main risk is overcorrecting and flattening categories that still matter in the custom league, so exact-league benchmark deltas should drive acceptance.
