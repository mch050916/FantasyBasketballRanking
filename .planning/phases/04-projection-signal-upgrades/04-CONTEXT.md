# Phase 4: Projection Signal Upgrades - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase upgrades the projection engine so it responds to broader player growth, role expansion, and veteran decline instead of leaning too heavily on points-only carry-forward. It is a model-signal phase, not a benchmark plumbing phase.

</domain>

<decisions>
## Implementation Decisions

### Trend signals
- **D-01:** Replace the current points-only trend logic with a broad multicategory trend score.
- **D-02:** Use a single composite trend score rather than separate per-category trend systems.
- **D-03:** The composite trend score should draw from changes in `PTS`, `AST`, `REB`, `3PTM`, `ST`, `BLK`, and `MIN`.

### Decline model
- **D-04:** Use a light age-based decline penalty rather than a hard or aggressive fade.
- **D-05:** The decline penalty should become meaningfully stronger only when veteran age and a negative recent trend line up.

### Role-change detection
- **D-06:** Treat role change as important enough to receive an extra breakout-style boost on top of the composite trend score.
- **D-07:** Minutes and related role growth should not be only passive ingredients inside the composite score; they should also be allowed to trigger an additional positive breakout response.

### Conservatism vs responsiveness
- **D-08:** Keep the system moderately responsive rather than highly reactive or overly conservative.
- **D-09:** Strong breakout signals may move recent-season trust noticeably, but recent-season dominance must still be capped.

### the agent's Discretion
- Exact composite-score weighting across the chosen stats.
- Exact age threshold and penalty magnitude for the decline model.
- Exact thresholds and caps for the extra role-change boost, as long as they remain moderate and bounded.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Defines Phase 4 goal, plans, and dependency on Phase 3.
- `.planning/REQUIREMENTS.md` — Defines `PROJ-01` and `PROJ-02`, which Phase 4 must satisfy.
- `.planning/PROJECT.md` — Confirms the priority is reducing heavy misses in significance order, not redesigning the whole scoring framework.

### Prior phase context
- `.planning/phases/03-miss-diagnostics/03-CONTEXT.md` — Establishes that heavy misses are now measured and grouped, so Phase 4 should use those diagnostics as the evidence base for model upgrades.
- `.planning/phases/02-identity-and-benchmark-fidelity/02-CONTEXT.md` — Keeps benchmark trust assumptions stable while model signals change.
- `.planning/phases/01-reliability-guardrails/01-CONTEXT.md` — Preserves the correctness-first stance; model changes should not weaken honest degraded-run behavior.

### Existing implementation
- `model.py` — Current `compute_trend_weights()` and `compute_gp_factor()` logic are the main Phase 4 touchpoints.
- `validate.py` — Current benchmark deltas and miss artifacts provide the measurement loop Phase 4 should preserve.
- `diagnostics/top_misses/*.csv` — Current miss artifacts provide the concrete evidence for what player types this phase needs to improve.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `model.compute_trend_weights()` already provides the seam where trend logic can be broadened beyond `PTS` only.
- `model.compute_gp_factor()` already captures availability separately, so the decline model should complement it rather than duplicate it.
- `main.py` and `validate.py` already provide rerun metrics and miss artifacts, which means Phase 4 can be judged directly against saved baselines.

### Established Patterns
- The model layer uses small, explicit helpers rather than large opaque formulas.
- The project prefers deterministic, explainable heuristics over black-box modeling.
- Existing season weighting is still bounded and normalized, so Phase 4 upgrades should preserve that shape rather than replace it with unconstrained weighting.

### Integration Points
- The composite trend score will likely replace or extend the current `compute_trend_weights()` internals.
- The age/decline penalty likely belongs close to the projection step in `project_stats()`, where it can influence projected counting stats without altering the DURANT scoring formula itself.
- The extra role-change boost should integrate with recent-season weighting rather than creating a second disconnected projection pathway.

</code_context>

<specifics>
## Specific Ideas

- The user wants broader trend detection, not just more points sensitivity.
- Breakout response should be stronger than it is today, but not so strong that one season fully takes over.
- Veteran decline should be real but modest, with extra caution not to blindly fade productive older stars.

</specifics>

<deferred>
## Deferred Ideas

- Per-category trend systems are deferred; this phase should use one composite signal.
- Fully data-driven age curves are deferred; this phase should use a lighter heuristic decline model.
- Category-calibration fixes for DD/TD remain deferred to Phase 5.

</deferred>

---
*Phase: 04-projection-signal-upgrades*
*Context gathered: 2026-04-30*
