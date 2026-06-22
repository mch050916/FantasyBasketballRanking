# Phase 01 Context — Category Distortion Diagnostics

## Goal

Identify which broad category families are still over- or under-driving exact-league 14-cat miss patterns so the next calibration phase can target real repeat distortions instead of one-off noise.

## Decisions Locked

- Use the two exact-league historical snapshot benchmarks as the **primary diagnostic surface**:
  - [actual_14cat_24_25_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_24_25_snapshot.csv)
  - [actual_14cat_23_24_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_23_24_snapshot.csv)
- Treat Yahoo benchmark surfaces as **secondary supporting context**, not co-equal diagnostic targets.
- Diagnose distortion through **broad category families first**, with raw category evidence underneath those family labels.
- Produce both a **console summary** and a **saved diagnostic artifact**.
- Only call a distortion family “real” when it **repeats across the exact-league snapshot surface**, or shows strongly in one snapshot with directional support in the other.
- Use **compact representative player examples** for each distortion family; deeper detail can remain in the existing miss and milestone artifacts.

## Current Evidence

- The current exact-league miss artifacts already mark repeated `category-weight distortion` misses for players such as `Nikola Vučević` and `Josh Hart`.
- Supporting Yahoo miss artifacts also surface distortion-tagged examples like `Jayson Tatum` and `Tyrese Haliburton`, but these are supporting signals rather than the acceptance surface.
- Existing diagnostics already provide enough raw material to build this phase on top of:
  - saved top-miss artifacts in [/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses)
  - saved milestone-contribution artifacts in [/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions](/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions)
  - benchmark history in [benchmark_history.csv](/Users/chesterman/FantasyBasketballRanking/diagnostics/benchmark_history.csv)

## Constraints

- Stay within the current Python CLI pipeline.
- Do not recalibrate the model in this phase; this phase is diagnostic only.
- Preserve the current benchmark and miss-diagnostic loop rather than inventing a parallel evaluation path.
- Keep exact-league 14-cat usefulness as the main success surface.

## Expected Focus

- Define a small set of interpretable distortion families that can explain repeated category-balance misses.
- Map existing miss and contribution artifacts into those families.
- Surface enough representative evidence to make the next calibration phase concrete and measurable.

## Existing Code Insights

### Reusable Assets

- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py): already builds top-miss artifacts, miss buckets, DD/TD contribution artifacts, and benchmark history rows.
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py): already prints validation summaries and persists diagnostic artifacts during the normal run loop.
- [/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses](/Users/chesterman/FantasyBasketballRanking/diagnostics/top_misses): current compact miss examples can serve as source material for distortion-family summaries.
- [/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions](/Users/chesterman/FantasyBasketballRanking/diagnostics/milestone_contributions): existing contribution breakdowns provide one layer of supporting evidence for family-level diagnosis.

### Established Patterns

- Diagnostics are persisted to CSV artifacts and summarized in the CLI.
- Exact-league snapshots are the primary acceptance surface when league-specific tuning is in scope.
- Compact artifact design is preferred over dumping every category in the main output.

### Integration Points

- The most natural insertion point is the existing validation/reporting path in [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) and [main.py](/Users/chesterman/FantasyBasketballRanking/main.py).
- Any saved diagnostic artifact should live alongside the current benchmark-history, top-miss, and milestone-contribution outputs in [/Users/chesterman/FantasyBasketballRanking/diagnostics](/Users/chesterman/FantasyBasketballRanking/diagnostics).

