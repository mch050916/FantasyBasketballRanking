# Requirements: DURANT Fantasy Basketball Ranker

**Defined:** 2026-04-30
**Core Value:** Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## v1.1 Requirements

### Benchmark Ingestion

- [x] **INGEST-01**: User can maintain season-specific exact-league benchmark CSVs from Yahoo screenshots through one repeatable ingestion path instead of ad hoc manual transcription.
- [x] **INGEST-02**: User can preserve season identity, rank order, and relevant player fields when converting screenshot-derived benchmark data into validation-ready files.
- [x] **INGEST-03**: User can review and correct screenshot-derived player rows before benchmark files are treated as trustworthy inputs.

### Benchmark Trust

- [x] **BTRUST-01**: User can see confidence or completeness signals for screenshot-derived benchmark files before relying on their validation metrics.
- [x] **BTRUST-02**: User can keep screenshot-derived benchmarks versioned and maintainable season by season without confusing them with direct-export sources.

### Data Resolution

- [x] **DRES-01**: User can resolve or explicitly suppress the remaining real NBA API identity/fetch edge cases such as `Jimmy Butler`, `Bojan Bogdanovic`, and `Saddiq Bey`.
- [x] **DRES-02**: User can distinguish expected unavailable player-season history from truly unresolved current-season fetch failures for problematic players.
- [x] **DRES-03**: User can rerun the pipeline after resolution changes and see whether degraded-run counts improved without hiding real failures.

## v2 Requirements

### Modeling

- **MODL-01**: User can improve the remaining breakout and availability miss cluster once the benchmark inputs and data-resolution surface are cleaner.
- **MODL-02**: User can bring in richer historical benchmark sources if Yahoo ever exposes a reliable league export path.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Replacing screenshot benchmarks with direct Yahoo exports | The exact league workflow does not reliably provide a clean export path today |
| Full OCR automation with no human review | Screenshot-derived data still needs a confidence and correction layer to stay trustworthy |
| New model-signal experiments unrelated to benchmark ingestion or data resolution | This milestone is about cleaner truth data and cleaner fetch coverage first |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 6 | Complete |
| INGEST-02 | Phase 6 | Complete |
| INGEST-03 | Phase 7 | Complete |
| BTRUST-01 | Phase 7 | Complete |
| BTRUST-02 | Phase 7 | Complete |
| DRES-01 | Phase 8 | Complete |
| DRES-02 | Phase 8 | Complete |
| DRES-03 | Phase 8 | Complete |

**Coverage:**
- v1.1 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-30*
*Last updated: 2026-05-07 after Phase 8 completion*
