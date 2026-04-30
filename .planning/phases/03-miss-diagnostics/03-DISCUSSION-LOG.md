# Phase 3 Discussion Log

**Date:** 2026-04-28  
**Phase:** 03 — Miss Diagnostics

## Decisions Captured

### Miss context depth
- Chosen: compact context
- Rationale: keep biggest-miss diagnostics readable while still exposing the key signals that explain why the miss happened

### Miss profile grouping
- Chosen: heuristic buckets
- Rationale: the user wants diagnostics that point toward the next modeling fix rather than a raw list of errors

### Baseline comparison
- Chosen: last saved run per benchmark
- Rationale: automatic “did this help?” feedback is more useful than manual baseline management for frequent model iteration

### Artifact format
- Chosen: console summary plus saved CSV artifacts
- Rationale: the console should stay concise, while CSVs preserve enough detail for later inspection and comparison

## Deferred

- No data-driven clustering in this phase
- No markdown-only reporting path in this phase
- No manual named baseline workflow in this phase
