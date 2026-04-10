# Phase 1: Reliability Guardrails - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 1-Reliability Guardrails
**Areas discussed:** Cache strictness, Missing-log policy

---

## Cache strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Targeted invalidation | Rebuild when seasons or season weights change, with minimal metadata | |
| Versioned cache contract | Add broader metadata envelope with schema/version and cache facts | |
| Aggressive safety | Rebuild often and distrust anything that does not match exactly | |
| Hybrid (targeted invalidation + aggressive safety) | Use exact metadata checks and auto-rebuild any invalid cache | ✓ |

**User's choice:** Hybrid approach combining targeted invalidation with aggressive safety behavior.
**Notes:** Follow-up decisions locked that invalid caches should auto-rebuild and continue, and that the rule should apply to both `tech_cache.pkl` and `game_log_cache.pkl`.

---

## Missing-log policy

| Option | Description | Selected |
|--------|-------------|----------|
| Warn + degraded run | Finish the run but clearly mark it degraded and list missing player-season logs | ✓ |
| Hard fail on draft-relevant misses | Stop the run when important logs remain missing | |
| Warn only | Print missing logs but otherwise treat the run as normal | |

**User's choice:** Warn + degraded run.
**Notes:** Draft relevance should be keyed off the requested game-log fetch pool, not a narrower final-draft-pool or star-only threshold.

---

## the agent's Discretion

- Final metadata schema details for cache envelopes.
- Final CLI wording and formatting for degraded-run reporting.
- Exact validation-health threshold logic beyond empty or broken validation results.

## Deferred Ideas

None.
