# DURANT Fantasy Basketball Ranker

## What This Is

This is a brownfield Python ranking engine for a custom Yahoo head-to-head fantasy basketball league. It combines Basketball Reference season totals, NBA API game logs, and the DURANT methodology to generate pre-draft player rankings that fit this league's 14-category format better than default Yahoo ranks.

The current work is not to invent a new product from scratch. It is to harden the existing pipeline, improve benchmark quality, and reduce the model's biggest misses one high-signal fix at a time.

## Core Value

Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## Requirements

### Validated

- ✓ Generate custom 14-category preseason fantasy rankings from historical season data and NBA API logs — existing
- ✓ Derive player consistency penalties, DD/TD rates, and TECH proxies as part of the scoring pipeline — existing
- ✓ Export rankings to CSV/console and compare them against local benchmark files — existing

### Active

- [ ] Improve projection accuracy by fixing the highest-impact causes of heavy misses one by one.
- [x] Make validation outputs trustworthy enough to distinguish historical accuracy from Yahoo-market similarity.
- [x] Reduce remaining player-identity gaps and noisy benchmark mismatches so degraded runs are high-signal instead of just honest.

### Out of Scope

- In-season roster management, waiver advice, or matchup streaming guidance — this tool is for draft preparation, not live weekly management.
- A web app or draft-room UI — the current product is a local Python pipeline and that is sufficient for the immediate goal.
- Adding speculative data sources with unclear quality — new external inputs should only land if they materially improve ranking quality.

## Context

The repo already contains a working CLI pipeline built around `main.py`, `data.py`, `model.py`, `output.py`, and `validate.py`. League settings live in `config.py`, validation inputs now include exact-league 14-cat snapshot CSVs plus Yahoo market exports, and NBA API fetches are cached locally in pickle files for repeat runs.

Recent work improved FG% projection math, TECH variance handling, historical benchmark support, NBA API name matching for accented players like Alperen Sengun/Şengün, and Phase 1 reliability guardrails around cache invalidation, degraded-run reporting, and validation health states. Phase 2 added a shared deterministic identity layer, expected-missing suppression for newer players lacking older seasons, and explicit benchmark trust tiers across exact-league snapshots and Yahoo exports. The current investigation is now focused on remaining large misses that appear to come from projection logic rather than benchmark plumbing.

## Constraints

- **Tech stack**: Stay within the current Python CLI architecture — the project already works as a local analytics script and does not need a framework migration.
- **Data dependency**: Basketball Reference CSVs and NBA API game logs remain the core data sources — the model depends on those inputs each season.
- **Reliability**: Rankings must degrade honestly when data is missing — silent cache drift or silent validation failure is worse than a noisy but explicit warning.
- **League specificity**: The ranking logic must optimize for this exact custom 14-category format — generic 9-cat assumptions are not sufficient.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep DURANT as the scoring foundation | The variance-aware framework is the product's core differentiator from Yahoo | ✓ Good |
| Treat this as a brownfield improvement project | The ranking engine already exists and the current need is iteration, not greenfield ideation | ✓ Good |
| Use exact-league 14-cat snapshot files alongside Yahoo exports | Historical snapshots and market proxies answer different validation questions and should both be available | ✓ Good |
| Make degraded runs explicit instead of failing hard | Trustworthy output matters more than pretending every NBA API fetch is complete | ✓ Implemented in Phase 1 |
| Use one shared deterministic identity layer with explicit overrides and no fuzzy fallback | Trustworthy matching matters more than squeezing out a few ambiguous joins | ✓ Implemented in Phase 2 |
| Label benchmark files with explicit class and trust tier | Historical snapshots and direct exports are both useful, but they should not look equally authoritative | ✓ Implemented in Phase 2 |
| Fix heavy misses in significance order | The cleanest path to improvement is to address the strongest failure modes one at a time and measure impact after each fix | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after Phase 2 completion*
