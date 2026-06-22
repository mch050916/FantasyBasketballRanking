# Retrospective

## Milestone: v1.0 — Trustworthiness And Accuracy Baseline

**Shipped:** 2026-04-30  
**Phases:** 5  
**Plans:** 10

### What Was Built

- Reliability guardrails for cache invalidation, degraded-run detection, and validation health
- Shared deterministic identity matching and benchmark trust-tier plumbing
- Persistent benchmark baselines, top-miss CSVs, miss buckets, and milestone-contribution artifacts
- Broader projection signal logic with trend, role-growth, and decline heuristics
- Separate bounded DD/TD calibration against exact-league historical snapshots

### What Worked

- The phase-by-phase approach kept modeling changes measurable instead of speculative.
- The benchmark and miss-diagnostic layers paid off quickly by making later fixes easier to judge.
- Explicit degraded-run reporting improved trust without forcing hard failures on flaky NBA API data.

### What Was Inefficient

- Git automation was repeatedly blocked by the local `.git/index.lock` issue, so the workflow could not produce clean atomic milestone commits.
- Validation artifact conventions were not fully uniform across phases, especially early Phase 01 Nyquist paperwork.

### Patterns Established

- Prefer deterministic identity resolution with explicit overrides over fuzzy matching.
- Treat historical snapshots and direct exports as different benchmark trust classes.
- Make each model change earn its place with baseline deltas and miss-artifact review.

### Key Lessons

- Benchmark plumbing is worth investing in before aggressive model tuning.
- Honest degraded runs are far better than silently “successful” bad data.
- The remaining hardest misses are now mostly modeling questions rather than pipeline-trust failures.

## Milestone: v1.1 — Benchmark Ingestion And Data Resolution

**Shipped:** 2026-05-09  
**Phases:** 5  
**Plans:** 10

### What Was Built

- Screenshot-first benchmark ingestion through reviewed intermediate tables and validation-ready seasonal snapshots
- Structured correction fields, row/file confidence, readiness metadata, and trust-aware historical snapshot reporting
- Narrow and auditable NBA API suppression governance with severity-aware run health
- OCR-assisted season-batch ingestion that feeds the existing review-table contract
- Durable markdown UAT evidence and a dedicated non-actionable suppression maintenance report

### What Worked

- Building on the reviewed-table contract from Phase 6 kept later confidence and OCR work cohesive instead of fragmenting into parallel workflows.
- The milestone stayed honest about trust by separating OCR confidence, reviewed confidence, readiness, and suppression policy.
- Closing audit debt as explicit phases was much cleaner than burying it inside archive notes.

### What Was Inefficient

- The OCR path still stopped short of a fully live local backend because the environment had no OCR tool installed.
- The milestone had to be reopened to close audit debt that could have been planned into the original scope earlier.
- Git automation remained blocked by the same local `.git/index.lock` issue, so the archive still lacks clean commit/tag provenance.

### Patterns Established

- Treat screenshot-derived benchmark data as first-class, but only after explicit review and readiness checks.
- Keep machine extraction hints separate from human-approved trust signals.
- Put narrow suppression policy on disk with seasonal scope instead of burying it in code.

### Key Lessons

- A trustworthy benchmark workflow needs as much product design as the ranking model itself.
- Reviewability beats premature automation when the input source is messy and business-critical.
- Audit debt is easier to close when it becomes explicit roadmap work with its own UAT surface.

## Milestone: v1.2 — Category Balance Calibration

**Shipped:** 2026-06-10  
**Phases:** 2  
**Plans:** 4

### What Was Built

- Category-distortion artifacts per benchmark plus an exact-league-first cross-benchmark summary
- Console reporting for broad distortion families alongside existing miss buckets and DD/TD contribution diagnostics
- Stronger bounded `DD` and `TD` milestone calibration through existing config/model hooks
- Evidence-gated residual-family reporting with `active_target`, `monitor_narrow`, and supporting states

### What Worked

- The cleaner `v1.1` benchmark surface made this milestone much easier to judge from evidence instead of intuition.
- Family-level diagnostics gave calibration a more useful target than isolated raw-stat misses.
- The phase stopped cleanly when the residual balanced-category signal was too narrow for a broad rebalance.

### What Was Inefficient

- Phase 1's expected durable UAT artifact was missing on disk, so the audit had to record that as workflow debt.
- Hit rate softened while ordering quality improved, which made the acceptance criteria matter more than usual.
- Git automation remained blocked by the local `.git/index.lock` issue.

### Patterns Established

- Use exact-league snapshots as the primary model-calibration surface and Yahoo outputs as sanity checks.
- Diagnose distortion at the family level first, then use raw categories as supporting evidence.
- Treat narrow repeated signals as monitor-only instead of turning every repeat into a broad model change.

### Key Lessons

- Better diagnostics make smaller calibration changes feel more trustworthy.
- Exact-league ordering quality is a better primary acceptance surface for this model than trying to optimize every metric equally.
- Residual signals should stay visible even when they are not strong enough to justify immediate tuning.

## Cross-Milestone Trends

- `v1.0` established ranking trust and diagnostics.
- `v1.1` made screenshot benchmark and suppression maintenance much more durable.
- `v1.2` used that stronger evidence surface to make a bounded model-quality improvement.
- The remaining leverage now looks centered on breakout/availability modeling, local OCR backend enablement, and future benchmark-source upgrades if Yahoo ever exposes better exports.
