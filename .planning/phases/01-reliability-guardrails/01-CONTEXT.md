# Phase 1: Reliability Guardrails - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes stale caches, missing draft-relevant game logs, and broken validation impossible to mistake for a clean run. It does not change the projection model itself; it changes how the pipeline detects, rebuilds, warns about, and reports unreliable inputs and validation outcomes.

</domain>

<decisions>
## Implementation Decisions

### Cache strictness
- **D-01:** Apply strict metadata validation to both `tech_cache.pkl` and `game_log_cache.pkl`, not just the TECH cache.
- **D-02:** Treat missing metadata, malformed metadata, unreadable cache content, or metadata mismatch as "do not trust this cache".
- **D-03:** When a cache is invalid, auto-rebuild and continue the run instead of stopping for manual intervention.

### Missing-log policy
- **D-04:** If any player-season log is still missing after fetch attempts for a player in the requested game-log fetch pool, complete the run but explicitly mark the run as degraded.
- **D-05:** A degraded run must list the missing player-season pairs so the user can see exactly what data remained unavailable.
- **D-06:** The degraded-run trigger should use the requested fetch pool, not a narrower final draft-pool heuristic.

### the agent's Discretion
- The exact metadata envelope format for caches can be chosen during planning as long as it supports strict validation and rebuild-on-mismatch behavior.
- The exact console wording and formatting for degraded-run messaging can be chosen during planning as long as the warnings are prominent and specific.
- Validation health thresholds beyond "empty or obviously broken" were not locked in this discussion and can be refined in planning or a later Phase 1 follow-up.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope
- `.planning/PROJECT.md` — project purpose, brownfield constraints, and the current milestone focus on reliability and benchmark trust.
- `.planning/REQUIREMENTS.md` — source of `DATA-01`, `DATA-02`, and `VAL-02`, which define the required outcomes for this phase.
- `.planning/ROADMAP.md` — Phase 1 goal, success criteria, and plan boundaries.

### Existing implementation
- `data.py` — current cache handling, game-log fetching, and TECH cache behavior.
- `main.py` — current orchestration and validation loop.
- `validate.py` — current validation behavior and empty-match handling.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data._load_cached_game_logs()` — existing cache-loading entry point for game logs; likely the cleanest place to introduce metadata-aware validation or a wrapped cache envelope.
- `data.fetch_game_logs()` — existing retry, skip, and cache-write flow; natural integration point for degraded-run tracking and missing-pair summaries.
- `data.fetch_tech_per_game()` — existing TECH fetch/cache path; natural integration point for strict metadata checks and rebuild-on-mismatch behavior.
- `validate.validate()` — existing validation metrics and biggest-miss reporting; natural place to return explicit health information instead of an empty dict alone.

### Established Patterns
- The pipeline prefers continuing with best-effort external data fetches rather than hard-failing on transient NBA API issues.
- User-facing progress is printed in numbered pipeline stages from `main.py`, so reliability warnings should fit that CLI style.
- Cache files are local pickle artifacts configured through `config.py`, so any metadata solution should preserve the local file-based workflow.

### Integration Points
- `main.py` validation loop will need to react to richer validation results or degraded-health indicators from `validate.py`.
- `main.py` fetch stage can aggregate cache rebuilds and missing-log outcomes into a final run-health summary.
- `tests/test_data.py` and `tests/test_validate.py` are the obvious homes for regression coverage around cache invalidation and validation-health behavior.

</code_context>

<specifics>
## Specific Ideas

- Correctness matters more than preserving a stale cache hit; if there is any doubt about cache validity, rebuild it automatically.
- A successful process exit should not imply a fully trustworthy run when draft-relevant logs are still missing.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 01-reliability-guardrails*
*Context gathered: 2026-04-10*
