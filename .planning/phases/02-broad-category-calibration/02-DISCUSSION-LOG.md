# Phase 02 Discussion Log

Date: 2026-05-10
Phase: 02 Broad Category Calibration

## Decisions

### Calibration priority order
- Decision: Use a strict family priority order.
- Locked order:
  1. `milestone carry`
  2. `balanced category carry`
  3. secondary-only families later if needed
- Reason: keeps the next calibration pass measurable and aligned with the strongest repeat-supported exact-league evidence.

### Adjustment surface
- Decision: Use a mixed adjustment surface.
- Locked approach:
  - bounded transforms in [model.py](/Users/chesterman/FantasyBasketballRanking/model.py)
  - selective category-weight changes in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py)
- Reason: some distortion is about contribution shape, not just raw weight.

### Family isolation vs bundled tuning
- Decision: Tune one family at a time.
- Locked approach:
  - target `milestone carry` first
  - only move to `balanced category carry` afterward if still needed
- Reason: keeps benchmark deltas interpretable and avoids overlapping explanations.

### Acceptance threshold
- Decision: Exact-league ordering quality is the primary gate.
- Supporting rules:
  - MAE is secondary evidence
  - Yahoo outputs remain sanity checks only
- Reason: `v1.2` exists to improve the real league ordering, not to maximize all surfaces equally.

### Secondary-family treatment
- Decision: `guard creation carry` is monitor-only in this phase.
- Locked approach:
  - no direct targeting in Phase 2
  - only note incidental movement if the main family work changes it
- Reason: it is currently `secondary_only` and does not yet have enough exact-league evidence to become a primary calibration target.
