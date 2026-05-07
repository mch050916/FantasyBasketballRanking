# Plan 04-02 Summary

## Outcome

Added a light age-and-negative-trend decline factor and reran the full benchmark loop through the existing Phase 3 diagnostics. The model now discounts veteran over-carry more honestly, but the benchmark impact is intentionally mixed rather than overly aggressive.

## Changes

- Added `compute_decline_factor()` in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) so veteran fade stays light by default and only strengthens when age and negative trend align.
- Integrated the decline factor into [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) for counting categories plus `DD`, `TD`, and `TECH`, while leaving `FG%` as a ratio projection.
- Added regression tests in [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) to distinguish age-only behavior from age-plus-negative-trend decline.
- Reran [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) to refresh benchmark deltas and top-miss artifacts under [/Users/chesterman/FantasyBasketballRanking/diagnostics](/Users/chesterman/FantasyBasketballRanking/diagnostics).

## Verification

- `python -m unittest discover -s tests`
- `python -u main.py`

## Result

- `actual_14cat_24_25_snapshot.csv`: Spearman `+0.002`, hit rate `+1.1`, MAE `+0.0`
- `actual_14cat_23_24_snapshot.csv`: Spearman `-0.005`, hit rate `+1.2`, MAE `+0.2`
- `yahoo_25_26_adp_proxy`: Spearman `+0.003`, hit rate `0.0`, MAE `-0.1`
- `yahoo_25_26_live_snapshot`: Spearman `+0.006`, hit rate `-3.1`, MAE `-0.2`
- `actual_9cat_24_25.csv`: Spearman `-0.011`, hit rate `-0.0`, MAE `-0.2`

## Notes

- The exact-league 14-cat benchmark improved slightly, which is the most relevant signal for this phase.
- Veteran over-carry remains present for players like Nikola Vučević, but the decline path moved him down without introducing a blind old-player fade.
- Remaining misses are still concentrated in breakout/role-growth and category-balance issues, which keeps Phase 5 focused on calibration rather than more benchmark plumbing.
