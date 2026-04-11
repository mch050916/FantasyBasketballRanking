# Requirements: DURANT Fantasy Basketball Ranker

**Defined:** 2026-04-10
**Core Value:** Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## v1 Requirements

### Data Integrity

- [x] **DATA-01**: User can rerun the pipeline without silently reusing stale TECH cache data when seasons or season weights change.
- [x] **DATA-02**: User can see which player-season game logs are still missing after a run.
- [x] **DATA-03**: User can resolve draft-relevant player identity mismatches across Basketball Reference, NBA API, and validation inputs without manually rewriting source files.

### Validation

- [x] **VAL-01**: User can run the model once and compare it against season-specific 14-cat snapshots and Yahoo market-style benchmarks in the same execution.
- [x] **VAL-02**: User can tell when a validation dataset matched too few players or failed entirely instead of reading a silent success.
- [ ] **VAL-03**: User can inspect the largest rank misses per benchmark after a run to guide the next model fix.

### Projection Quality

- [ ] **PROJ-01**: User gets trend adjustments informed by more than points so non-scoring role changes can influence projections.
- [ ] **PROJ-02**: User gets a lightweight decline signal for aging veterans whose carry-forward box stats overrate next-season value.
- [ ] **PROJ-03**: User gets category calibration that keeps DD and TD from systematically overpowering the rest of the multicategory profile.
- [ ] **PROJ-04**: User can measure validation deltas after each model change to confirm whether a fix improved the benchmarks.

## v2 Requirements

### Modeling Expansion

- **MODL-01**: User can project from three or more historical seasons when enough data exists.
- **MODL-02**: User can use stable player IDs instead of name-only joins across data providers.
- **MODL-03**: User can tune category weights from observed matchup history instead of hand-set heuristics.

### Workflow

- **FLOW-01**: User can import exact Yahoo exports directly instead of maintaining screenshot-derived historical CSVs manually.
- **FLOW-02**: User can review benchmark summaries in a richer report than console output alone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Weekly lineup optimization | Not part of the pre-draft ranking objective |
| Full GUI or hosted application | The current local script form is sufficient for the immediate milestone |
| Live scraping of Yahoo pages | Adds fragility and credential complexity without improving the core model directly |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 2 | Complete |
| VAL-01 | Phase 2 | Complete |
| VAL-02 | Phase 1 | Complete |
| VAL-03 | Phase 3 | Pending |
| PROJ-01 | Phase 4 | Pending |
| PROJ-02 | Phase 4 | Pending |
| PROJ-03 | Phase 5 | Pending |
| PROJ-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 after Phase 2 completion*
