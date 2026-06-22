# Phase 11: Breakout And Availability Diagnostics - Context

**Gathered:** 2026-06-10  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 11 is a diagnostic phase only. It should separate the remaining exact-league misses into breakout underreaction, role-growth signal, and availability overtrust evidence before any model weights or projection logic are changed in later phases.

</domain>

<decisions>
## Implementation Decisions

### Classification labels

- **D-01:** Use a richer compact label set: `breakout underreaction`, `role-growth underreaction`, `availability overtrust`, `availability undertrust`, and `unclear`.
- **D-02:** Keep labels compact enough to drive Phase 12 and Phase 13 planning without fragmenting into many tiny subtypes.

### Evidence inputs

- **D-03:** Use the combined evidence surface already available in the pipeline: existing miss artifacts, projected stats, `GP`, `MIN`, `GP_FACTOR`, year-over-year category growth, current miss buckets, and category-distortion labels.
- **D-04:** Do not build a separate diagnostic universe that ignores existing Phase 3, Phase 5, and Phase 1 evidence.

### Benchmark surface

- **D-05:** Treat the two exact-league 14-cat snapshots as the primary diagnostic surface.
- **D-06:** Include Yahoo benchmarks only as secondary supporting context and sanity checks.

### Artifact shape

- **D-07:** Write per-benchmark diagnostic CSV artifacts.
- **D-08:** Write a cross-benchmark summary artifact that rolls up the diagnostic labels across benchmark surfaces.
- **D-09:** Add a compact console summary to `python main.py` output so normal runs show the breakout/availability pattern without requiring manual CSV inspection.

### Player context depth

- **D-10:** Keep console examples compact, showing representative players and headline reasons.
- **D-11:** Put richer context in saved artifacts, including rank delta, `GP`, `MIN`, `GP_FACTOR`, growth cues, miss bucket, and category-distortion family where available.

### the agent's Discretion

- Exact heuristic thresholds, column names, and artifact filenames can be chosen during planning/implementation as long as they stay deterministic, readable, and consistent with existing diagnostics.
- The planner may decide whether to extend existing validation helpers or create small new helpers, but the output should integrate with the current `validate.py` and `main.py` diagnostic pattern.

</decisions>

<specifics>
## Specific Ideas

- The diagnostic labels should clearly separate "we missed upside" from "we overtrusted fragile production" because those map to different future model fixes.
- The phase should continue the exact-league-first acceptance pattern established in `v1.2`.
- Phase 11 should feed Phase 12 and Phase 13 with evidence, not tune projections itself.

</specifics>

<canonical_refs>
## Canonical References

### Milestone and phase scope

- `.planning/PROJECT.md` - Current `v1.3` milestone goal and constraints.
- `.planning/REQUIREMENTS.md` - `BAV-01` and `BAV-02` diagnostic requirements.
- `.planning/ROADMAP.md` - Phase 11 boundary and downstream Phase 12/13 sequencing.

### Existing diagnostic surfaces

- `validate.py` - Existing benchmark validation, miss buckets, milestone contribution artifacts, and category-distortion summary integration.
- `main.py` - Current CLI validation output and run summary surface.
- `diagnostics/top_misses/` - Existing top-miss artifacts that should inform classification.
- `diagnostics/category_distortions/` - Existing category-distortion artifacts and summary from `v1.2`.
- `diagnostics/milestone_contributions/` - Existing DD/TD contribution artifacts.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `validate.py` already builds benchmark comparison rows, top misses, miss buckets, DD/TD contribution artifacts, and category-distortion artifacts.
- `main.py` already prints compact per-benchmark diagnostic sections and a cross-benchmark category-distortion summary.
- Existing diagnostics are CSV-backed and deterministic, which is the right pattern for Phase 11 artifacts.

### Established Patterns

- Exact-league historical snapshots are the primary acceptance and diagnostic surface.
- Yahoo market/live outputs are useful secondary sanity checks, not primary targets.
- Console output should stay compact, with deeper inspection handled through saved artifacts.

### Integration Points

- Phase 11 should likely integrate into the validation loop after top misses, miss buckets, milestone contributions, and category-distortion families are available.
- The output should leave enough structured evidence for Phase 12 role-growth calibration and Phase 13 availability-risk calibration.

</code_context>

<deferred>
## Deferred Ideas

- Tuning role-growth responsiveness belongs to Phase 12.
- Adding or changing availability-risk projection logic belongs to Phase 13.
- Installing a concrete OCR backend remains outside `v1.3` unless explicitly promoted in a future milestone.

</deferred>

---

*Phase: 11-breakout-and-availability-diagnostics*  
*Context gathered: 2026-06-10*
