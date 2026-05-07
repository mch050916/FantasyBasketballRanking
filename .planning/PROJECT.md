# DURANT Fantasy Basketball Ranker

## What This Is

This is a brownfield Python ranking engine for a custom Yahoo head-to-head fantasy basketball league. It combines Basketball Reference season totals, NBA API game logs, and the DURANT methodology to generate pre-draft player rankings that fit this league's 14-category format better than default Yahoo ranks.

The current work is not to invent a new product from scratch. It is to harden the existing pipeline, improve benchmark quality, and reduce the model's biggest misses one high-signal fix at a time.

## Core Value

Produce trustworthy pre-draft rankings for this exact league format that are more useful than Yahoo's default ordering.

## Current State

`v1.0` is now shipped. The ranker has moved from a working-but-fragile local model into a measurably safer pipeline with explicit run-health reporting, deterministic identity matching, trust-tiered benchmark execution, persistent miss diagnostics, broader projection signals, and bounded DD/TD calibration.

The repo still centers on the same Python CLI architecture, but the current baseline is much stronger:
- stale cache reuse and silent validation failure are now surfaced explicitly
- benchmark comparisons are saved and comparable across runs
- model misses are inspectable by benchmark, player profile, and milestone-stat contribution
- remaining weaknesses are mostly genuine modeling/data edge cases, not hidden plumbing failures

## Current Milestone: v1.1 Benchmark Ingestion And Data Resolution

**Goal:** Turn screenshot-derived league history into a more maintainable and trustworthy benchmark input path while shrinking the remaining real NBA API resolution failures.

**Target features:**
- ingest and normalize season-specific benchmark data from league screenshots with less brittle manual handling
- add confidence and review checks around screenshot-derived benchmark files before validation trusts them
- harden or suppress remaining real NBA API identity/fetch failures like `Jimmy Butler`, `Bojan Bogdanovic`, and `Saddiq Bey`

## Requirements

### Validated

- ✓ Generate custom 14-category preseason fantasy rankings from historical season data and NBA API logs — existing
- ✓ Derive player consistency penalties, DD/TD rates, and TECH proxies as part of the scoring pipeline — existing
- ✓ Export rankings to CSV/console and compare them against local benchmark files — existing

### Active

- [x] Build a repeatable screenshot-to-benchmark ingestion path that fits the league’s actual Yahoo workflow.
- [x] Add benchmark confidence/review guardrails so screenshot-derived historical files are easier to trust and maintain.
- [x] Reduce the remaining unresolved NBA API identity and fetch misses without weakening degraded-run honesty.

## Next Milestone Goals

- Build around screenshot-derived league history as the primary historical benchmark source, since direct export is not reliably available.
- Reduce remaining unresolved NBA API fetch/identity edge cases such as `Jimmy Butler`, `Bojan Bogdanovic`, and `Saddiq Bey`.
- Make historical benchmark upkeep less manual and less error-prone season to season.

### Out of Scope

- In-season roster management, waiver advice, or matchup streaming guidance — this tool is for draft preparation, not live weekly management.
- A web app or draft-room UI — the current product is a local Python pipeline and that is sufficient for the immediate goal.
- Adding speculative data sources with unclear quality — new external inputs should only land if they materially improve ranking quality.

## Context

The repo already contains a working CLI pipeline built around `main.py`, `data.py`, `model.py`, `output.py`, and `validate.py`. League settings live in `config.py`, validation inputs now include exact-league 14-cat snapshot CSVs plus Yahoo market exports, and NBA API fetches are cached locally in pickle files for repeat runs.

Recent work improved FG% projection math, TECH variance handling, historical benchmark support, NBA API name matching for accented players like Alperen Sengun/Şengün, and Phase 1 reliability guardrails around cache invalidation, degraded-run reporting, and validation health states. Phase 2 added a shared deterministic identity layer, expected-missing suppression for newer players lacking older seasons, and explicit benchmark trust tiers across exact-league snapshots and Yahoo exports. Phase 3 added per-benchmark baseline history, current-vs-previous delta reporting, and saved top-miss artifacts with compact heuristic grouping. Phase 4 replaced the points-only trend path with a multicategory composite plus capped role boost and added a light veteran decline factor gated by negative trend alignment. Phase 5 then made `DD` and `TD` contribution explicit in diagnostics and added separate bounded milestone-stat calibration paths. All `v1.0` requirements are now complete and archived.

The next milestone is intentionally not built around direct Yahoo exports, because the league workflow does not reliably provide them. Instead, `v1.1` treats screenshot-derived history as the real source of truth to improve, while also tightening the remaining live data-resolution failures.

Phase 6 established the benchmark-ingestion contract: screenshot extraction lands in a reviewed intermediate table first, and only reviewed rows may become season-specific benchmark CSVs for the existing validation loop. Phase 7 then added explicit corrected fields, row/file confidence, readiness gating, metadata sidecars, and readiness-aware validation reporting so screenshot-derived benchmarks can be trusted and maintained more deliberately. Phase 8 closed the live NBA API resolution surface with narrow explicit non-actionable classifications and a severity-aware run-health summary.

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
| Persist benchmark baselines and saved miss artifacts | Model iteration should be measured from evidence instead of relying on memory or console scrollback | ✓ Implemented in Phase 3 |
| Fix heavy misses in significance order | The cleanest path to improvement is to address the strongest failure modes one at a time and measure impact after each fix | ✓ Active milestone pattern |
| Use bounded heuristics instead of a full age curve for now | The current milestone needs explainable signal upgrades, not an overfit decline model | ✓ Implemented in Phase 4 |
| Calibrate milestone stats locally instead of rewriting DURANT | `DD` and `TD` distortion could be reduced with bounded per-category scaling while preserving the core ranking framework | ✓ Implemented in Phase 5 |
| Keep unresolved data-path edge cases explicit instead of hiding them | Honest degraded runs preserve trust and make future work easier to prioritize | ✓ Good |
| Treat screenshot-derived league history as a first-class benchmark input | The actual Yahoo league workflow does not reliably support clean exports, so the tooling must adapt to screenshots instead of waiting for a better source | — Current milestone |
| Land screenshot extraction in a reviewed intermediate table before benchmark generation | Screenshot-derived truth data needs a human-check boundary, and later phases can build confidence tooling on top of that stable contract | ✓ Implemented in Phase 6 |
| Treat screenshot-derived benchmark readiness as explicit metadata, not an assumption | A benchmark file can exist on disk and still be too weak to trust, so validation needs a real ready/not-ready gate | ✓ Implemented in Phase 7 |
| Suppress current-season NBA API misses only when the case is explicitly non-actionable | Degraded-run honesty matters more than lower counts, so suppression must stay narrow and auditable | ✓ Implemented in Phase 8 |

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
*Last updated: 2026-05-07 after Phase 8 completion*
