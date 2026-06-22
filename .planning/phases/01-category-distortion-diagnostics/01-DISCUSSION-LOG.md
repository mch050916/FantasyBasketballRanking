# Phase 01 Discussion Log

## 2026-05-09

### Topic: Diagnostic comparison surface

- Decision: Use exact-league historical snapshots as the primary diagnostic surface, with Yahoo as secondary context.
- Rationale: `v1.2` is explicitly optimizing the real league format, so the exact-league benchmarks should drive what counts as distortion.

### Topic: Attribution granularity

- Decision: Diagnose broad distortion families first, with raw category evidence underneath.
- Rationale: The next calibration phase needs interpretable targets, not just a flat list of noisy individual stats.

### Topic: Artifact shape

- Decision: Produce both a console summary and a saved artifact.
- Rationale: This phase is about reusable evidence, so the output needs to be visible during runs and durable for later planning/comparison.

### Topic: Evidence threshold

- Decision: Only treat a distortion family as real when it repeats across the exact-league snapshot surface.
- Rationale: Repeat appearance across the league-specific benchmarks is a better filter for real signal than one-off noise.

### Topic: Player-context depth

- Decision: Use compact representative player examples.
- Rationale: The project already has deeper miss and milestone artifacts, so the primary diagnostic surface should stay concise and actionable.
