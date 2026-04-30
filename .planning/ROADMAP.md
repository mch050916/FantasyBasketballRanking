# Roadmap: DURANT Fantasy Basketball Ranker

## Overview

This roadmap treats the existing ranking engine as working brownfield software and focuses the next milestone on trustworthiness and accuracy. The path starts by making stale or incomplete runs explicit, then improves cross-source identity and benchmarking, then adds the feedback loop needed to measure changes, and only after that moves into the higher-variance model changes that can materially reduce the biggest ranking misses.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Reliability Guardrails** - Make stale caches, missing logs, and broken validation impossible to miss. (completed 2026-04-10)
- [x] **Phase 2: Identity And Benchmark Fidelity** - Make cross-source player matching and benchmark execution trustworthy. (completed 2026-04-10)
- [x] **Phase 3: Miss Diagnostics** - Surface benchmark deltas and biggest misses so each model change is measurable. (completed 2026-04-28)
- [ ] **Phase 4: Projection Signal Upgrades** - Improve trend and decline signals that drive the heaviest misses.
- [ ] **Phase 5: Category Calibration** - Rebalance DD/TD influence against the rest of the multicategory profile.

## Phase Details

### Phase 1: Reliability Guardrails
**Goal**: User can trust that a successful run did not quietly rely on stale TECH cache data, hidden missing logs, or silently broken validation.
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, VAL-02
**Success Criteria** (what must be TRUE):
  1. User can rerun the pipeline and get refreshed TECH cache behavior when season inputs or weighting assumptions change.
  2. User can see which player-season logs are still missing after a run instead of inferring it from bad outputs.
  3. User can see when a validation file failed or matched too few players to be trustworthy.
**Plans**: 2 plans

Plans:
- [x] 01-01: Add cache metadata and invalidation rules for TECH and other fragile fetch artifacts.
- [x] 01-02: Add explicit missing-log and validation-health reporting to pipeline output and tests.

### Phase 2: Identity And Benchmark Fidelity
**Goal**: User can compare the same player population across Basketball Reference, NBA API, and benchmark files without brittle manual cleanup.
**Depends on**: Phase 1
**Requirements**: DATA-03, VAL-01
**Success Criteria** (what must be TRUE):
  1. User can run the pipeline without draft-relevant players dropping out because of avoidable naming mismatches.
  2. User can execute season-specific 14-cat and Yahoo-style validations in one pass with clearly labeled outputs.
  3. User can trust benchmark inputs to represent the same players the model ranked.
**Plans**: 2 plans

Plans:
- [x] 02-01: Strengthen player identity resolution and add deterministic fallbacks for known cross-source mismatches.
- [x] 02-02: Normalize benchmark target handling so exact-league and Yahoo comparison paths are explicit and consistent.

### Phase 3: Miss Diagnostics
**Goal**: User can see the benchmark impact and largest misses after every run so the next fix is chosen from evidence instead of guesswork.
**Depends on**: Phase 2
**Requirements**: VAL-03, PROJ-04
**Success Criteria** (what must be TRUE):
  1. User can inspect the largest misses for each benchmark directly from the run artifacts.
  2. User can compare new metrics against a prior baseline after a model change.
  3. User can identify which player profiles still dominate the error distribution.
**Plans**: 2 plans

Plans:
- [x] 03-01: Add benchmark delta reporting that compares current metrics with the previous baseline.
- [x] 03-02: Add top-miss summaries per validation target with enough context to drive the next modeling fix.

### Phase 4: Projection Signal Upgrades
**Goal**: User gets projections that respond to broader role change and aging decline instead of leaning too heavily on points carry-forward.
**Depends on**: Phase 3
**Requirements**: PROJ-01, PROJ-02
**Success Criteria** (what must be TRUE):
  1. User gets trend adjustments informed by more than raw scoring movement.
  2. User sees obvious over-carried veterans discounted when decline signals are present.
  3. User can rerun validations and see whether the upgraded projection signals improved the target benchmarks.
**Plans**: 2 plans

Plans:
- [ ] 04-01: Expand trend weighting to consider broader category and role movement.
- [ ] 04-02: Add a lightweight age and decline adjustment with focused regression tests.

### Phase 5: Category Calibration
**Goal**: User gets final rankings whose DD and TD contribution is calibrated against historical results instead of overpowering the rest of the profile.
**Depends on**: Phase 4
**Requirements**: PROJ-03
**Success Criteria** (what must be TRUE):
  1. User can see DD and TD contribution reviewed against historical benchmark misses.
  2. User gets recalibrated category influence when DD or TD is dominating rankings unfairly.
  3. User can rerun validations after calibration and judge whether the ranking spread improved.
**Plans**: 2 plans

Plans:
- [ ] 05-01: Analyze DD and TD contribution against benchmark miss patterns.
- [ ] 05-02: Adjust scoring/calibration and verify the effect with rerun metrics.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Reliability Guardrails | 2/2 | Complete    | 2026-04-10 |
| 2. Identity And Benchmark Fidelity | 2/2 | Complete | 2026-04-10 |
| 3. Miss Diagnostics | 2/2 | Complete | 2026-04-28 |
| 4. Projection Signal Upgrades | 0/2 | Not started | - |
| 5. Category Calibration | 0/2 | Not started | - |
