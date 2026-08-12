# Roadmap: DURANT Fantasy Basketball Ranker

## Milestones

- ✅ **v1.0 Trustworthiness And Accuracy Baseline** — Phases 1-5 (shipped 2026-04-30) — see [archive](/Users/chesterman/FantasyBasketballRanking/.planning/milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Benchmark Ingestion And Data Resolution** — Phases 6-10 (shipped 2026-05-09) — see [archive](/Users/chesterman/FantasyBasketballRanking/.planning/milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Category Balance Calibration** — Phases 1-2 (shipped 2026-06-10) — see [archive](/Users/chesterman/FantasyBasketballRanking/.planning/milestones/v1.2-ROADMAP.md)
- 🚧 **v1.3 Breakout And Availability Modeling** — Phase 11 planned

## Active Phases

- [x] **Phase 11: Breakout And Availability Diagnostics** - Separate the remaining exact-league misses into breakout underreaction, role-growth signal, and availability overtrust evidence before changing model weights. — planned 2026-07-03, completed 2026-08-12
- [ ] **Phase 12: Role-Growth Responsiveness Calibration** - Improve bounded responsiveness to minutes, usage, and multicategory growth without destabilizing the exact-league category-balance gains from `v1.2`.
- [ ] **Phase 13: Availability Risk Calibration And Rerun** - Add a bounded availability-risk adjustment, rerun exact-league benchmarks, and judge the combined breakout/availability change against saved baselines.

## Progress

| Milestone | Phases | Plans | Status | Shipped |
|-----------|--------|-------|--------|---------|
| v1.0 Trustworthiness And Accuracy Baseline | 5 | 10 | Complete | 2026-04-30 |
| v1.1 Benchmark Ingestion And Data Resolution | 5 | 10 | Complete | 2026-05-09 |
| v1.2 Category Balance Calibration | 2 | 4 | Complete | 2026-06-10 |
| v1.3 Breakout And Availability Modeling | 3 | 2 complete | Phase 11 complete | - |

### Phase 11: Breakout And Availability Diagnostics

**Goal:** Separate the remaining exact-league misses into breakout underreaction, role-growth signal, and availability overtrust evidence before changing model weights.  
**Requirements:** BAV-01, BAV-02  
**Depends on:** v1.2 category-balance diagnostics and saved miss artifacts  
**Plans:** 2 plans — complete 2026-08-12

Plans:
- [x] 11-01: Build the deterministic breakout/availability classifier and per-benchmark diagnostic artifact.
- [x] 11-02: Save artifacts, build the cross-benchmark summary, and add compact console reporting.

### Phase 12: Role-Growth Responsiveness Calibration

**Goal:** Improve bounded responsiveness to minutes, usage, and multicategory growth without destabilizing the exact-league category-balance gains from `v1.2`.  
**Requirements:** BAV-03, BAV-04  
**Depends on:** Phase 11  
**Plans:** not planned yet

### Phase 13: Availability Risk Calibration And Rerun

**Goal:** Add a bounded availability-risk adjustment, rerun exact-league benchmarks, and judge the combined breakout/availability change against saved baselines.  
**Requirements:** BAV-05, BAV-06  
**Depends on:** Phase 12  
**Plans:** not planned yet
