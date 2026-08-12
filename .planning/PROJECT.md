# DURANT Fantasy Basketball Ranker

## What This Is

This is a brownfield Python ranking engine for a custom Yahoo head-to-head fantasy basketball league. It combines Basketball Reference season totals, NBA API game logs, and the DURANT methodology to generate pre-draft player rankings that fit this league's 14-category format better than default Yahoo ranks.

The current work is not to invent a new product from scratch. It is to harden the existing pipeline, improve benchmark quality, and reduce the model's biggest misses one high-signal fix at a time.

## Core Value

Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## Current State

`v1.0`, `v1.1`, and `v1.2` are shipped. The ranker has moved from a working-but-fragile local model into a safer, more measurable Python CLI pipeline with explicit run-health reporting, deterministic identity matching, trust-tiered benchmark execution, persistent miss diagnostics, screenshot-first benchmark governance, OCR-assisted ingestion hooks, season-scoped suppression maintenance, and family-level category-balance diagnostics.

The current baseline is much stronger:

- stale cache reuse and silent validation failure are surfaced explicitly
- benchmark comparisons are saved and comparable across runs
- model misses are inspectable by benchmark, player profile, milestone-stat contribution, and category-distortion family
- screenshot-derived historical benchmarks flow through explicit review, confidence, readiness, and provenance checks
- exact-league category-balance misses can be grouped into repeat-supported family patterns
- remaining weaknesses are mostly genuine modeling/data edge cases, local OCR-backend availability, or future-season maintenance work rather than hidden plumbing failures

## Current Milestone: v1.3 Breakout And Availability Modeling

**Goal:** Improve ranking quality on the remaining breakout, role-growth, and availability miss cluster without destabilizing the exact-league benchmark gains from `v1.2`.

**Target features:**

- identify which misses are true breakout underreactions versus availability or injury-risk overtrust
- improve role-growth responsiveness for players with stronger minutes, usage, or multicategory growth signals
- add a bounded availability-risk adjustment so fragile or low-availability profiles are not over-carried
- rerun exact-league snapshots as the primary acceptance surface, with Yahoo outputs as secondary sanity checks

## Requirements

### Validated

- ✓ Generate custom 14-category preseason fantasy rankings from historical season data and NBA API logs — existing
- ✓ Derive player consistency penalties, DD/TD rates, and TECH proxies as part of the scoring pipeline — existing
- ✓ Export rankings to CSV/console and compare them against local benchmark files — existing
- ✓ Maintain screenshot-derived benchmark review, confidence, OCR-assisted seeding, and seasonal suppression governance — shipped in `v1.1`
- ✓ Diagnose category-balance distortions against exact-league 14-cat benchmarks — shipped in `v1.2`
- ✓ Recalibrate dominant category influence without rewriting the core DURANT pipeline — shipped in `v1.2`
- ✓ Keep exact-league 14-cat snapshots as the primary acceptance surface while checking Yahoo outputs as secondary sanity checks — shipped in `v1.2`
- ✓ Distinguish breakout underreaction, role-growth signal, and availability overtrust in the biggest exact-league misses — shipped in `v1.3` Phase 11

### Active

- [ ] Improve bounded role-growth responsiveness without letting one recent season fully dominate projections. — Phase 12 next
- [ ] Add a bounded availability-risk adjustment for fragile or low-availability profiles.
- [ ] Rerun exact-league benchmarks and secondary Yahoo sanity checks after breakout and availability changes.

## Candidate Future Goals

- `balanced category carry` was upgraded from `monitor_narrow` to `active_target` on 2026-08-12 once the duplicated 23-24/24-25 benchmark data was fixed and gave it real independent repeat evidence (4 hits / 2 genuine snapshots) — no longer just a "future" watch item, it's active evidence for upcoming model work.
- Install and support a concrete OCR backend locally behind the existing adapter boundary.
- Continue using screenshot-derived benchmark history as the primary exact-league source unless Yahoo exposes a reliable export path.
- Incorporate incoming rookies with no prior NBA statistical history (e.g. AJ Dybantsa, Cam Boozer, and the rest of the 2026 draft class once known) into the ranking model ahead of `26-27` season prep. This needs a different projection path than the current trend/season-history model, since rookies have no `BBR_FILES`/game-log history to weight against — likely some kind of draft-capital/college-production/comparable-archetype proxy. Not scoped or designed yet; revisit when `26-27` season prep begins.

## Out of Scope

- In-season roster management, waiver advice, or matchup streaming guidance — this tool is for draft preparation, not live weekly management.
- A web app or draft-room UI — the current product is a local Python pipeline and that is sufficient for the immediate goal.
- Adding speculative data sources with unclear quality — new external inputs should only land if they materially improve ranking quality.
- In-season injury news scraping — `v1.3` should use stable historical availability signals rather than volatile news feeds.

## Context

The repo contains a working CLI pipeline built around [main.py](/Users/chesterman/FantasyBasketballRanking/main.py), [data.py](/Users/chesterman/FantasyBasketballRanking/data.py), [model.py](/Users/chesterman/FantasyBasketballRanking/model.py), [output.py](/Users/chesterman/FantasyBasketballRanking/output.py), and [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py). League settings live in [config.py](/Users/chesterman/FantasyBasketballRanking/config.py), validation inputs include exact-league 14-cat snapshot CSVs plus Yahoo market exports, and NBA API fetches are cached locally in pickle files for repeat runs.

`v1.0` established the safer and more measurable ranking baseline: cache guardrails, deterministic identity matching, persistent diagnostics, broader projection signals, and bounded DD/TD calibration. `v1.1` made the real league benchmark workflow much more maintainable by treating screenshot-derived history as a first-class source with reviewed ingestion, confidence/readiness governance, OCR-assisted seeding, and explicit seasonal suppression maintenance. `v1.2` shifted back to model quality by adding exact-league-first category-distortion diagnostics and a bounded broad-category calibration pass.

The most recent milestone, `v1.2`, improved exact-league ordering quality on both primary historical snapshots while leaving residual `balanced category carry` as an explicit `monitor_narrow` signal for future modeling work. `v1.3` now targets the remaining breakout and availability miss cluster while preserving those category-balance gains.

## Constraints

- **Tech stack**: Stay within the current Python CLI architecture.
- **Data dependency**: Basketball Reference CSVs and NBA API game logs remain the core data sources.
- **Reliability**: Rankings must degrade honestly when data is missing.
- **League specificity**: Ranking logic must optimize for this exact custom 14-category format.
- **Model discipline**: Keep changes bounded, explainable, and measurable against exact-league snapshots before treating Yahoo outputs as secondary context.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep DURANT as the scoring foundation | The variance-aware framework is the product's core differentiator from Yahoo | ✓ Good |
| Treat this as a brownfield improvement project | The ranking engine already exists and the current need is iteration, not greenfield ideation | ✓ Good |
| Use exact-league 14-cat snapshot files alongside Yahoo exports | Historical snapshots and market proxies answer different validation questions and should both be available | ✓ Good |
| Make degraded runs explicit instead of failing hard | Trustworthy output matters more than pretending every NBA API fetch is complete | ✓ Implemented |
| Use deterministic identity resolution with explicit overrides | Trustworthy matching matters more than squeezing out ambiguous joins | ✓ Implemented |
| Treat screenshot-derived league history as a first-class benchmark input | The actual Yahoo league workflow does not reliably support clean exports | ✓ Implemented in `v1.1` |
| Keep OCR behind a pluggable review-table-first boundary | OCR engine availability is environment-dependent | ✓ Implemented in `v1.1` |
| Use exact-league 14-cat snapshots as the primary acceptance surface for category calibration | The benchmark path is strong enough to tune for the real league format | ✓ Implemented in `v1.2` |
| Diagnose category balance through family-level distortion evidence before recalibrating | Calibration needed interpretable repeat patterns, not another raw-stat-only miss list | ✓ Implemented in `v1.2` |
| Treat narrow residual repeat families as monitor-only | A single repeated exact-league player can justify monitoring without justifying a broad rebalance | ✓ Implemented in `v1.2` |
| Tackle breakout and availability together in `v1.3` | The remaining miss cluster includes both underreaction to role growth and overtrust in fragile profiles, so the next model pass should reason about both | — Active |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-08-12 after Phase 11 completion*
