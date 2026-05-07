# Phase 05 Context — Category Calibration

## Goal

Calibrate `DD` and `TD` so they stop overpowering the multicategory profile in this exact 14-category league while preserving the rest of the DURANT pipeline.

## Decisions Locked

- Prioritize exact-league validation benchmarks first:
  - [actual_14cat_24_25_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_24_25_snapshot.csv)
  - [actual_14cat_23_24_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_23_24_snapshot.csv)
- Use **weight + scaling calibration**, not weight-only and not a full scoring rewrite.
- Calibrate `DD` and `TD` separately.
- Judge success primarily by the exact-league 14-cat historical benchmarks, with Yahoo comparisons used as secondary sanity checks.

## Current Evidence

- Recent miss artifacts still show `category-weight distortion` for players whose multicategory profile is boosted materially by `DD` and `TD`.
- Examples from current diagnostics include players like `Nikola Vučević`, `Josh Hart`, `Tyrese Haliburton`, and `Jayson Tatum`.
- Phase 4 improved projection signals, but miss concentration still points to category-balance issues rather than identity, reliability, or benchmark-plumbing failures.

## Constraints

- Keep the current Python CLI architecture.
- Preserve the DURANT scoring framework.
- Avoid a large formula rewrite in this phase.
- Keep the calibration measurable through the existing diagnostics loop and benchmark history.

## Expected Focus

- Inspect how `DD` and `TD` are currently projected and scored.
- Decide where to compress or rescale them before weighting.
- Keep `TD` calibration independent from `DD` because the event frequency and ranking impact differ.
