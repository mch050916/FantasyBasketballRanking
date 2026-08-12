# Requirements: DURANT Fantasy Basketball Ranker

**Defined:** 2026-06-10  
**Core Value:** Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## v1.3 Requirements

### Breakout And Availability Diagnostics

- [x] **BAV-01**: User can distinguish breakout underreaction, role-growth signal, and availability overtrust in the biggest exact-league misses.
- [x] **BAV-02**: User can inspect saved diagnostic artifacts that explain why a player was classified as breakout-driven, role-growth-driven, availability-driven, or unclear.

### Role-Growth Responsiveness

- [ ] **BAV-03**: User can improve model responsiveness to minutes, usage, and multicategory growth signals without allowing one recent season to fully dominate projections.
- [ ] **BAV-04**: User can confirm role-growth changes preserve the `v1.2` exact-league category-balance gains and do not reintroduce major milestone or category distortion.

### Availability Risk

- [ ] **BAV-05**: User can apply a bounded availability-risk adjustment so fragile or low-availability profiles are not over-carried by per-game production alone.
- [ ] **BAV-06**: User can rerun the full ranking and validation loop after breakout and availability changes and see exact-league-first benchmark deltas plus secondary Yahoo sanity checks.

## v2 Requirements

### Modeling

- **MODL-01**: User can revisit residual balanced-category carry now that it is an `active_target` with real repeat evidence.
- **MODL-02**: User can incorporate a concrete local OCR backend behind the existing adapter boundary if benchmark upkeep still needs more automation.
- **MODL-03**: User can revisit richer historical benchmark sources if Yahoo ever exposes a reliable league export path.
- **MODL-04**: User can rank incoming rookies with no prior NBA statistical history (e.g. `26-27` draft class) alongside returning players, using a projection path that doesn't depend on the current trend/season-history model.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full projection-engine rewrite | `v1.3` should keep the bounded, measurable model-iteration pattern that worked in `v1.2`. |
| New benchmark ingestion workflows | `v1.1` already established screenshot review, confidence, OCR adapter, and suppression governance. |
| In-season injury news scraping | This milestone should use available historical availability signals, not add a volatile news-ingestion dependency. |
| Draft-room UI or live roster assistant | The product remains a local pre-draft ranking pipeline. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BAV-01 | Phase 11 | Shipped |
| BAV-02 | Phase 11 | Shipped |
| BAV-03 | Phase 12 | Pending |
| BAV-04 | Phase 12 | Pending |
| BAV-05 | Phase 13 | Pending |
| BAV-06 | Phase 13 | Pending |

**Coverage:**
- v1.3 requirements: 6 total
- Mapped to phases: 6
- Unmapped: 0

---
*Requirements defined: 2026-06-10*
*Last updated: 2026-07-03 after Phase 11 planning*
