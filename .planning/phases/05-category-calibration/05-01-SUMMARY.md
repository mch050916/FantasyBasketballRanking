# Plan 05-01 Summary

## Outcome

Added explicit `DD`/`TD` contribution analysis to the benchmark loop so milestone-stat distortion is now directly inspectable instead of inferred from raw projections or top-rank intuition.

## Changes

- Extended [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) with a `DD`/`TD` contribution artifact path built from `DD_G`, `TD_G`, `TOTAL_VALUE`, and dominant milestone-driver labels.
- Added compact `DD/TD contribution` CLI summaries in [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) so each benchmark now prints average `DD_G`, average `TD_G`, milestone share, and whether `DD` or `TD` dominates the distortion.
- Added deterministic artifact persistence via [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) and wired it through [main.py](/Users/chesterman/FantasyBasketballRanking/main.py).
- Added saved milestone-contribution artifacts under [/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions](/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions).
- Extended [tests/test_validate.py](/Users/chesterman/FantasyBasketballRanking/tests/test_validate.py) to cover contribution shape, separate `DD`/`TD` surfacing, and deterministic persistence.

## Verification

- `python -m unittest discover -s tests`

## Result

- The benchmark loop now shows concrete milestone-stat influence instead of only raw `DD`/`TD` rates.
- Exact-league and Yahoo-style benchmarks now preserve persistent contribution artifacts for follow-up calibration work.
- The new artifact format stays compact and consistent with the existing diagnostics structure.

## Notes

- Contribution share can exceed `100%` on individual misses when milestone G-scores are large but other category G-scores offset them; that is expected and still useful as a distortion signal.
