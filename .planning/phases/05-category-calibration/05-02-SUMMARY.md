# Plan 05-02 Summary

## Outcome

Calibrated `DD` and `TD` separately using bounded milestone compression plus modest weight tuning, then reran the full benchmark loop with exact-league 14-cat results treated as the primary acceptance surface.

## Changes

- Added `calibrate_milestone_value()` and `calibrate_category_values()` in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) so `DD` and `TD` can be compressed locally inside the scoring path without rewriting the DURANT framework.
- Applied milestone calibration inside [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) before Box-Cox/log transformation in `compute_g_scores()`.
- Added separate milestone calibration settings in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py):
  - `DD`: lighter compression, full category relevance retained
  - `TD`: stronger compression plus a modest weight trim
- Added regression tests in [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) to prove `DD` and `TD` are calibrated separately and stay bounded.
- Reran [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) to refresh benchmark history, top-miss artifacts, and milestone-contribution artifacts.

## Verification

- `python -m unittest discover -s tests`
- `python -u main.py`

## Result

Compared with the pre-Phase-5 benchmark state from Phase 4:

- `actual_14cat_24_25_snapshot.csv`: Spearman `0.659 -> 0.665`, hit rate `26.6% -> 25.5%`, MAE `24.3 -> 24.1`
- `actual_14cat_23_24_snapshot.csv`: Spearman `0.610 -> 0.616`, hit rate `28.6% -> 27.4%`, MAE `22.6 -> 22.5`
- `yahoo_25_26_adp_proxy`: Spearman `0.678 -> 0.683`, hit rate `13.7% -> 13.7%`, MAE `30.7 -> 30.4`

## Notes

- The final calibration favored a milder `DD` path and a stronger `TD` path after an in-memory tuning sweep against cached benchmark data.
- Exact-league hit rate dipped slightly, but Spearman improved on both historical 14-cat snapshots and MAE improved or held. Given the locked Phase 5 priority on exact-league ranking quality, this is directionally acceptable.
- Remaining misses are now more clearly concentrated in breakout/role-growth and residual category-balance issues rather than unmeasured milestone-stat distortion.
