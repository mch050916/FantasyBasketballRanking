# Roadmap: DURANT Fantasy Basketball Ranker

## Milestones

- ✅ **v1.0 Trustworthiness And Accuracy Baseline** — Phases 1-5 (shipped 2026-04-30) — see [archive](/Users/chesterman/FantasyBasketballRanking/.planning/milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 Benchmark Ingestion And Data Resolution** — Phases 6-8 (planned)

## Archived Phases

<details>
<summary>✅ v1.0 Trustworthiness And Accuracy Baseline (Phases 1-5) — SHIPPED 2026-04-30</summary>

- [x] Phase 1: Reliability Guardrails (2/2 plans) — completed 2026-04-10
- [x] Phase 2: Identity And Benchmark Fidelity (2/2 plans) — completed 2026-04-10
- [x] Phase 3: Miss Diagnostics (2/2 plans) — completed 2026-04-28
- [x] Phase 4: Projection Signal Upgrades (2/2 plans) — completed 2026-04-30
- [x] Phase 5: Category Calibration (2/2 plans) — completed 2026-04-30

</details>

## Active Phases

- [x] **Phase 6: Screenshot Benchmark Ingestion** - Build a repeatable path for converting Yahoo screenshot history into season-specific benchmark CSVs. (completed 2026-05-07)
- [x] **Phase 7: Benchmark Confidence And Review** - Add confidence, review, and maintenance guardrails for screenshot-derived benchmark files. (completed 2026-05-07)
- [x] **Phase 8: NBA API Resolution Hardening** - Reduce the remaining true identity/fetch failures without weakening degraded-run honesty. (completed 2026-05-07)

## Phase Details

### Phase 6: Screenshot Benchmark Ingestion
**Goal**: User can turn league screenshots into season-specific benchmark CSVs through one repeatable ingestion path instead of one-off manual handling.
**Depends on**: Phase 5
**Requirements**: INGEST-01, INGEST-02
**Success Criteria** (what must be TRUE):
  1. User can produce validation-ready benchmark rows from screenshot-derived league history with season identity preserved.
  2. User can regenerate benchmark CSVs using the same ingestion path for future seasons.
  3. Ingested benchmark files keep rank order and player identity data consistent enough for validation use.
**Plans**: 2 plans

Plans:
- [x] 06-01: Create a structured screenshot-to-benchmark ingestion workflow and file format.
- [x] 06-02: Normalize player fields and season metadata from ingested screenshot benchmarks.

### Phase 7: Benchmark Confidence And Review
**Goal**: User can understand how trustworthy a screenshot-derived benchmark file is before using it to judge model accuracy.
**Depends on**: Phase 6
**Requirements**: INGEST-03, BTRUST-01, BTRUST-02
**Success Criteria** (what must be TRUE):
  1. User can review and correct suspicious or incomplete screenshot-derived rows before validation consumes them.
  2. Validation output distinguishes screenshot-derived benchmark confidence from direct-export trust.
  3. Historical screenshot benchmarks stay organized and maintainable across seasons.
**Plans**: 2 plans

Plans:
- [x] 07-01: Add benchmark review and correction support for ingested screenshot data.
- [x] 07-02: Add confidence/completeness reporting and maintenance conventions for screenshot-derived benchmarks.

### Phase 8: NBA API Resolution Hardening
**Goal**: User can shrink the remaining real unresolved NBA API fetch failures while keeping degraded-run reporting honest.
**Depends on**: Phase 7
**Requirements**: DRES-01, DRES-02, DRES-03
**Success Criteria** (what must be TRUE):
  1. User can resolve or explicitly suppress known stubborn fetch cases like `Jimmy Butler`, `Bojan Bogdanovic`, and `Saddiq Bey`.
  2. User can distinguish expected unavailable seasons from true current-season resolution failures for problematic players.
  3. Reruns show whether degraded-run counts improved after resolution changes without masking real misses.
**Plans**: 2 plans

Plans:
- [x] 08-01: Harden the identity/fetch path for the remaining unresolved NBA API players.
- [x] 08-02: Improve degraded-run classification and rerun measurement for stubborn fetch failures.

## Progress

| Milestone | Phases | Plans | Status | Shipped |
|-----------|--------|-------|--------|---------|
| v1.0 Trustworthiness And Accuracy Baseline | 5 | 10 | Complete | 2026-04-30 |
| v1.1 Benchmark Ingestion And Data Resolution | 3 | 6 | In Progress | - |
