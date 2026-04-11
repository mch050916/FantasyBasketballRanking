# Phase 2: Identity And Benchmark Fidelity - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Make cross-source player matching and benchmark execution trustworthy. This phase is about identity resolution, benchmark trust labeling, and benchmark matching policy. It is not a projection-model upgrade phase.

</domain>

<decisions>
## Implementation Decisions

### Player identity source of truth
- **D-01:** Use deterministic normalized-name matching plus an explicit manual override map as the identity source of truth for cross-source player resolution.
- **D-02:** Do not attempt a full player-ID migration in this phase. Stable IDs can remain a later expansion once the current name-based edge cases are under control.

### Missing-season benchmark policy
- **D-03:** Treat older-season absences as expected when a player was not yet in the NBA, and exclude those expected-missing cases from degraded-run warnings.
- **D-04:** Keep genuinely unresolved player-season misses visible in degraded-run reporting.

### Historical benchmark trust rules
- **D-05:** Keep screenshot-derived historical 14-cat files in the validation flow, but label them explicitly as lower-trust snapshot benchmarks.
- **D-06:** Treat direct CSV exports as the higher-trust benchmark tier and make that difference visible in reporting.

### Benchmark matching strictness
- **D-07:** Use a deterministic fallback order for benchmark matching: explicit override map first, normalized-name matching second, and otherwise no match.
- **D-08:** Do not introduce fuzzy matching in this phase because false positives would damage benchmark trust more than a lower match count.

### the agent's Discretion
- Exact file/module split for the override map and trust-label plumbing.
- How benchmark trust labels are surfaced in console output vs helper metadata, as long as the tiers remain explicit.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Defines Phase 2 scope, goals, success criteria, and dependency on Phase 1.
- `.planning/REQUIREMENTS.md` — Defines `DATA-03` and `VAL-01`, which this phase is expected to satisfy.
- `.planning/PROJECT.md` — Captures the product goal of trustworthy exact-league rankings and the requirement to degrade honestly when data is incomplete.

### Prior phase context
- `.planning/phases/01-reliability-guardrails/01-CONTEXT.md` — Establishes the correctness-first stance for cache trust and degraded-run honesty that Phase 2 should preserve.
- `.planning/phases/01-reliability-guardrails/01-02-SUMMARY.md` — Documents the current degraded-run behavior and the remaining identity-related misses exposed by Phase 1.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data.py`: already contains normalized player-name helpers and NBA API name resolution logic that Phase 2 can extend with deterministic overrides.
- `validate.py`: already contains normalized benchmark matching and structured validation status output, making it the natural place to centralize stricter benchmark matching rules.
- `main.py`: already supports multiple benchmark targets and notes per target, so it can carry benchmark trust-tier labels without changing the overall CLI shape.

### Established Patterns
- The pipeline is correctness-first and explicit about degraded states after Phase 1; Phase 2 should continue that pattern rather than hiding ambiguity behind “best effort” matching.
- Validation and fetch logic are file-based and deterministic, with small helpers preferred over large orchestration rewrites.
- League and benchmark reporting are surfaced directly in CLI output, so trust labels should stay visible there rather than being hidden only in metadata.

### Integration Points
- Identity overrides will likely sit between raw source names and the existing normalization flow in `data.py` and `validate.py`.
- Expected-missing season logic should plug into the game-log health reporting path introduced in `data.py`.
- Trust-tier benchmark labeling should integrate with the `VALIDATION_TARGETS` structure in `main.py` and the reporting path in `validate.py`.

</code_context>

<specifics>
## Specific Ideas

- Deterministic matching is more important than maximizing match count.
- The user wants honest benchmark quality labels instead of pretending screenshot-derived data is as trustworthy as direct exports.
- Expected missing seasons should stop generating noisy degraded-run output for players who simply were not in the league yet.

</specifics>

<deferred>
## Deferred Ideas

- Full stable-ID migration across all providers remains a later expansion once the current manual-override approach has paid off.
- Fuzzy benchmark matching is explicitly deferred because it increases the risk of silent false matches.

</deferred>

---
*Phase: 02-identity-and-benchmark-fidelity*
*Context gathered: 2026-04-10*
