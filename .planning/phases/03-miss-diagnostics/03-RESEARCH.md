## User Constraints

### Implementation Decisions

- **D-01:** Compare each benchmark target against the most recent saved baseline for that same benchmark.
- **D-02:** Baseline comparison should be automatic rather than requiring manual baseline selection.
- **D-03:** Keep a concise console summary for immediate feedback.
- **D-04:** Save structured CSV artifacts for benchmark deltas and top misses so runs can be inspected later.
- **D-05:** Use compact context for biggest misses rather than full 14-category dumps.
- **D-06:** Compact miss context should include the rank delta plus a small set of explanatory projected columns.
- **D-07:** Group misses into explicit heuristic buckets rather than leaving interpretation fully manual.
- **D-08:** Initial miss buckets should include `availability miss`, `breakout/role growth`, `aging/decline`, `category-weight distortion`, and `unclear/other`.

### The Agent's Discretion

- Exact CSV filenames and folder structure for diagnostic artifacts.
- Exact projected columns included in compact miss context.
- Exact threshold heuristics for deterministic miss bucketing.

### Deferred Ideas

- Statistical clustering of misses.
- Manual named-baseline management.
- Markdown-only reporting as the primary saved artifact.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Keep outputs deterministic and file-based.
- Keep user-facing CLI output concise and informative.
- Use small helpers and preserve the existing modular split.
- Do not hide degraded or low-trust states behind over-polished summaries.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas` remains the right abstraction for saved benchmark summaries and miss artifact CSVs. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `unittest` remains the test surface for this phase. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- `main.py` already owns benchmark iteration and final run output, so baseline artifact save/load and delta printing should plug into that loop rather than create a second entrypoint. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- `validate.validate()` already computes structured per-target metrics plus a detailed merged DataFrame, so miss artifacts should be derived there or immediately downstream from its return value. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- Phase 2 established explicit benchmark metadata (`benchmark_class`, `trust_tier`); Phase 3 should preserve and reuse those fields in all saved diagnostic artifacts. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]

## Don't Hand-Roll

- Do not store diagnostics only in ad hoc console strings when structured CSVs are a phase requirement. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/03-miss-diagnostics/03-CONTEXT.md]
- Do not dump the entire 14-category row for every miss; the user explicitly chose compact context. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/03-miss-diagnostics/03-CONTEXT.md]
- Do not use fuzzy or opaque bucketing logic; the miss groups must stay deterministic and explainable. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/03-miss-diagnostics/03-CONTEXT.md]

## Common Pitfalls

- `validate.validate()` currently prints biggest misses but only returns the raw merged comparison details; there is no persisted miss artifact or baseline history yet. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- `main.py` currently discards historical run metrics after printing them, so there is no durable “did this change help?” loop yet. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- The current biggest-miss output is rank-only; without projected context it is hard to tell whether a miss points to availability, breakout risk, aging, or category calibration. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]

## Code Examples

- A small diagnostics artifact directory such as `diagnostics/` or a similarly scoped repo-root folder fits the existing file-based workflow and keeps baseline CSVs separate from the ranking output file. [ASSUMED]
- A per-benchmark baseline summary CSV keyed by benchmark label is the cleanest way to compare current metrics to the most recent saved run without introducing a database or config burden. [ASSUMED]
- Miss bucket assignment can remain deterministic by using projected context already present in the rankings DataFrame, such as `GP_FACTOR`, `DD`, `TD`, and category-heavy stat profiles. [ASSUMED]

## Validation Architecture

- Unit tests should cover baseline load/save behavior and delta calculation when a prior benchmark snapshot exists or does not exist.
- Unit tests should cover miss artifact shaping, including compact context columns and deterministic miss bucket assignment.
- End-to-end verification should continue using `python -m unittest discover -s tests` and `python -u main.py`.
- Manual verification should confirm that the CLI stays readable while saved CSV artifacts contain the richer detail.

## Planning Notes

- The cleanest split remains:
  1. build benchmark baseline persistence plus delta reporting;
  2. add saved top-miss artifacts with compact context and heuristic buckets.
- Plan 1 should establish the reusable artifact path and per-benchmark summary model first so Plan 2 can save miss outputs alongside it.
- The biggest correctness risk in this phase is diagnostics that imply causality without enough evidence, so miss bucket heuristics should be modest and clearly named rather than overconfident.
