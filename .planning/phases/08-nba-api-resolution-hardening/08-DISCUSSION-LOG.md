# Phase 08 Discussion Log

## 2026-05-07

### Topic: Resolution strategy

- Decision: Use deterministic resolution first, then explicit suppression second.
- Rationale: The phase should try to recover real data before declaring a miss non-actionable.

### Topic: Suppression boundary

- Decision: Suppress only when the failure is explicitly classified as non-actionable.
- Rationale: This keeps degraded-run counts meaningful and prevents suppression from masking fixable regressions.

### Topic: Current-season vs historical misses

- Decision: Treat current-season misses as higher severity.
- Rationale: Current-season logs are closer to the real projection surface, so unresolved misses there matter more than older-context gaps.

### Topic: Success measurement

- Decision: Primary success is fewer real degraded current-season misses; secondary success is clearer classification.
- Rationale: This rewards real recovery first while still valuing honest reporting when some misses remain unavoidable.
