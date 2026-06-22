# Project Milestones: DURANT Fantasy Basketball Ranker

## v1.0 Trustworthiness And Accuracy Baseline (Shipped: 2026-04-30)

**Delivered:** A more trustworthy and measurable 14-category preseason ranking pipeline with explicit run health, deterministic identity matching, benchmark diagnostics, broader projection signals, and DD/TD calibration.

**Phases completed:** 1-5 (10 plans total)

**Key accomplishments:**
- Hardened cache trust and degraded-run reporting so stale or incomplete runs cannot silently pass as healthy.
- Unified player identity matching and benchmark trust-tier handling across Basketball Reference, NBA API, snapshot files, and Yahoo exports.
- Added persistent benchmark history, delta reporting, top-miss artifacts, heuristic miss buckets, and DD/TD contribution diagnostics.
- Replaced points-only trend handling with multicategory trend, bounded role boost, and light age-aligned decline logic.
- Calibrated DD and TD separately inside the scoring path using bounded compression guided by exact-league benchmarks.

**Stats:**
- 5 phases, 10 plans
- 36 passing unit tests at milestone completion
- Git range unavailable because milestone commits were blocked locally by `.git/index.lock`

---

## v1.1 Benchmark Ingestion And Data Resolution (Shipped: 2026-05-09)

**Delivered:** A screenshot-first benchmark workflow with reviewed ingestion, confidence and readiness guardrails, OCR-assisted seeding, explicit NBA API suppression governance, and durable audit evidence for the whole path.

**Phases completed:** 6-10 (10 plans total)

**Key accomplishments:**
- Added a repeatable screenshot-to-review-table-to-benchmark pipeline instead of one-off manual benchmark handling.
- Introduced structured review corrections, row/file confidence rollups, readiness gates, and provenance metadata for historical exact-league snapshots.
- Hardened NBA API resolution reporting with explicit severity splits, narrow non-actionable classifications, and season-scoped suppression governance.
- Added a pluggable OCR ingestion boundary that seeds the existing reviewed-table workflow without bypassing human review.
- Backfilled markdown UAT artifacts and added a dedicated maintenance report so milestone evidence and suppression policy stay reviewable on disk.

**Stats:**
- 5 phases, 10 plans
- 62 passing unit tests at milestone completion
- Exact-league historical snapshots now run as ready, high-confidence reviewed benchmarks
- Git range unavailable because milestone commits were blocked locally by `.git/index.lock`

---

## v1.2 Category Balance Calibration (Shipped: 2026-06-10)

**Delivered:** Exact-league-first category-distortion diagnostics plus a bounded broad-category calibration pass that reduced the dominant `milestone carry` pattern without forcing a noisy second-pass rebalance.

**Phases completed:** 1-2 (4 plans total)

**Key accomplishments:**
- Added saved per-benchmark category-distortion artifacts and an exact-league-first cross-benchmark summary.
- Surfaced broad distortion families in normal validation output while preserving existing miss buckets and DD/TD contribution diagnostics.
- Tightened bounded `DD` and `TD` milestone calibration through existing config/model hooks.
- Improved exact-league ordering quality on both primary historical snapshots.
- Marked residual `balanced category carry` as `monitor_narrow`, keeping future modeling work explicit and evidence-gated.

**Stats:**
- 2 phases, 4 plans
- 67 passing unit tests at milestone audit
- Exact-league snapshot Spearman improved to `0.676` for 2024-25 and `0.627` for 2023-24
- Git range unavailable because milestone commits were blocked locally by `.git/index.lock`

**What's next:** Define the next milestone, likely around breakout/availability misses, local OCR backend enablement, or future benchmark-source upgrades.

---
