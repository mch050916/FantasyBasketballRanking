# Phase 3: Miss Diagnostics - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes benchmark output decision-useful after each model change. It is about reporting metric deltas, saving diagnostic artifacts, surfacing the biggest misses with compact player context, and grouping those misses into interpretable heuristic buckets. It does not change the projection model itself.

</domain>

<decisions>
## Implementation Decisions

### Baseline comparison
- **D-01:** Compare each benchmark target against the most recent saved baseline for that same benchmark.
- **D-02:** Baseline comparison should be automatic rather than requiring the user to freeze or manually select a prior run.

### Miss artifact format
- **D-03:** Keep a concise console summary for immediate feedback.
- **D-04:** Also save structured CSV artifacts for benchmark deltas and top misses so runs can be inspected and compared later.

### Miss context depth
- **D-05:** Use compact player context for biggest misses rather than full 14-category row dumps.
- **D-06:** Compact miss context should include the rank delta plus a short set of useful explanatory columns, such as projected availability and the most relevant multicategory signals.

### Miss profile grouping
- **D-07:** Group misses into a small set of explicit heuristic buckets rather than leaving interpretation fully manual.
- **D-08:** Initial buckets should include `availability miss`, `breakout/role growth`, `aging/decline`, `category-weight distortion`, and `unclear/other`.

### the agent's Discretion
- Exact CSV filenames and folder placement for the saved diagnostic artifacts.
- Exact threshold heuristics for assigning miss buckets, as long as the grouping remains interpretable and deterministic.
- Exact compact context columns, as long as they stay small and useful rather than turning into a full stat dump.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Defines Phase 3 goal, plans, and dependency on Phase 2.
- `.planning/REQUIREMENTS.md` — Defines `VAL-03` and `PROJ-04`, which Phase 3 must satisfy.
- `.planning/PROJECT.md` — Reinforces the “fix heavy misses in significance order” strategy and the need for trustworthy evidence before model changes.

### Prior phase context
- `.planning/phases/01-reliability-guardrails/01-CONTEXT.md` — Establishes correctness-first reporting and explicit degraded/validation health behavior that Phase 3 should preserve.
- `.planning/phases/02-identity-and-benchmark-fidelity/02-CONTEXT.md` — Establishes deterministic matching and benchmark trust-tier semantics that diagnostic reporting should reuse rather than reinterpret.

### Existing implementation
- `main.py` — Current validation orchestration and run-health summary output.
- `validate.py` — Current per-benchmark metrics and biggest-miss reporting path.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `validate.validate()` already computes Spearman, hit rate, MAE, matched-player count, and a sorted biggest-miss table, so it is the natural place to expose richer structured miss diagnostics.
- `main.py` already iterates over all benchmark targets in one run and collects structured validation results, which makes it the natural place to add baseline comparison and artifact saving.
- The current benchmark metadata model in `VALIDATION_TARGETS` already distinguishes benchmark classes and trust tiers, so Phase 3 can reuse that for saved diagnostics.

### Established Patterns
- User-facing reporting is CLI-first and concise, with richer detail acceptable when saved to files rather than dumped into the terminal.
- The project prefers deterministic, explicit behavior over clever opaque logic, so miss bucketing should be heuristic and explainable.
- Saved outputs are file-based artifacts in the repo root today, so Phase 3 should stay within that pattern rather than introducing a new storage system.

### Integration Points
- Baseline artifacts will likely be written after validation completes and reloaded on the next run before printing delta summaries.
- Top-miss CSVs can likely be derived from the existing `details` DataFrame returned by `validate.validate()`.
- Miss buckets should be computed from projected-player context plus benchmark deltas, not from fuzzy narrative interpretation.

</code_context>

<specifics>
## Specific Ideas

- Diagnostics should help choose the next modeling fix, not just restate that the model missed.
- Console output should stay readable during normal runs; the saved CSVs can hold the denser detail.
- The user wants compact miss context, not a full category spreadsheet for every miss.

</specifics>

<deferred>
## Deferred Ideas

- Statistical clustering of miss profiles is deferred; Phase 3 should use explicit heuristic buckets first.
- Manual named baselines are deferred; automatic last-run comparison is the Phase 3 baseline strategy.
- Rich markdown or HTML diagnostic reports are deferred in favor of CSV artifacts plus CLI summaries.

</deferred>

---
*Phase: 03-miss-diagnostics*
*Context gathered: 2026-04-28*
