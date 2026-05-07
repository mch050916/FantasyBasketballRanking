## User Constraints

### Implementation Decisions

- **D-01:** Replace the current points-only trend logic with a broad multicategory trend score.
- **D-02:** Use a single composite trend score rather than separate per-category trend systems.
- **D-03:** Build the composite from `PTS`, `AST`, `REB`, `3PTM`, `ST`, `BLK`, and `MIN`.
- **D-04:** Use a light age-based decline penalty rather than an aggressive veteran fade.
- **D-05:** Strengthen the decline penalty only when veteran age and negative recent trend line up.
- **D-06:** Add an extra role-change breakout boost on top of the composite trend score.
- **D-07:** Keep the system moderately responsive and bounded so one recent season cannot fully dominate.

### The Agent's Discretion

- Exact weighting of the composite trend components.
- Exact age threshold and decline penalty magnitude.
- Exact breakout thresholds and caps for the separate role-change boost.

### Deferred Ideas

- Full per-category trend systems.
- Fully data-driven age curves.
- Category-calibration changes to DD/TD, which remain Phase 5 scope.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Keep the DURANT scoring framework intact; this phase changes projection signals, not the ranking formula itself.
- Keep model behavior deterministic and explainable.
- Preserve the existing validation rerun loop so improvements can be measured directly after implementation.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas` and `numpy` remain sufficient for the projection heuristics needed here. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `unittest` remains the right test surface for this phase. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- `model.compute_trend_weights()` is already the main seam for season-weight adjustment, so broadening its signal is lower-risk than inventing a parallel weighting system. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- `project_stats()` already computes `GP_FACTOR` and the final weighted projections, making it the natural integration point for any bounded decline penalty that should affect projected counting stats. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- Phase 3’s diagnostics loop is now strong enough that Phase 4 can be judged directly by rerunning the same benchmarks and miss artifacts. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/03-miss-diagnostics/03-01-SUMMARY.md]

## Don't Hand-Roll

- Do not let one recent season fully dominate the weights even when breakout signals are strong; bounded responsiveness is a locked decision. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/04-projection-signal-upgrades/04-CONTEXT.md]
- Do not reintroduce points-only logic under a different name; the trend signal must genuinely incorporate the broader stat set. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/04-projection-signal-upgrades/04-CONTEXT.md]
- Do not apply a blind veteran fade independent of recent performance; age and negative trend must reinforce each other. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/04-projection-signal-upgrades/04-CONTEXT.md]

## Common Pitfalls

- `compute_trend_weights()` currently keys entirely off recent `PTS` versus weighted baseline, so it misses players whose role growth shows up more in assists, threes, defensive stats, or minutes. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- The current trend boost is symmetric and single-factor, which means breakout and decline response are too narrow for the error profiles now captured in diagnostics. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]
- `project_stats()` currently has no age-aware decline path at all, so stable-but-aging veterans can carry too much prior value into the next-season projection. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/model.py]

## Evidence From Current Miss Artifacts

- Historical snapshot miss artifacts show clear `breakout/role growth` misses for players like Keyonte George and Andrew Nembhard, which supports broadening the trend signal and adding explicit role-change response. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses/actual_14cat_23_24_snapshot_csv_top_misses.csv]
- Historical and Yahoo miss artifacts still show `availability miss` and `category-weight distortion`, but Phase 4 should stay focused on signal upgrades rather than availability plumbing or DD/TD calibration. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses/yahoo_25_26_adp_proxy_top_misses.csv]
- Veteran over-carry cases like Nikola Vučević and Brook Lopez appear repeatedly, which supports a modest age-and-negative-trend decline path. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses/actual_14cat_24_25_snapshot_csv_top_misses.csv]

## Validation Architecture

- Add unit tests around the composite trend calculation and bounded weight adjustment behavior.
- Add unit tests around decline penalties so older players with negative trend are discounted while similarly aged but stable players are not over-penalized.
- Continue end-to-end verification with `python -m unittest discover -s tests` plus `python -u main.py`.
- Use Phase 3 baseline deltas and saved miss artifacts as the success-measurement loop for this phase.

## Planning Notes

- The cleanest split remains:
  1. replace points-only trend detection with a broad composite trend score plus bounded role-change boost;
  2. add the age-and-negative-trend decline penalty and verify benchmark impact.
- Plan 1 should land first so Plan 2 can evaluate decline behavior on top of the broader signal model rather than the old points-only base.
- The biggest risk is overreacting to one-season noise, so both the composite trend score and the extra role boost should be capped and regression-tested.
