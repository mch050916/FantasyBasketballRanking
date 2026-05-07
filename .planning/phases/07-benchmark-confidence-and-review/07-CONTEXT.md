# Phase 07 Context — Benchmark Confidence And Review

## Goal

Make screenshot-derived benchmark files trustworthy enough to maintain and use in validation without treating every reviewed CSV as equally reliable by default.

## Decisions Locked

- Confidence should exist at **both the row level and the file level**.
- The review workflow should use a **structured CSV review model** with explicit correction fields and statuses.
- A benchmark is only **ready** when:
  - all rows are reviewed
  - required fields are present
  - the file-level confidence summary clears a minimum threshold
- Generated benchmark snapshots should carry a **core provenance bundle**:
  - `season`
  - `source_batch`
  - review completion counts
  - confidence summary
  - generated-at metadata
- If a screenshot-derived benchmark is **not ready**, validation should **skip it and warn clearly** instead of treating it as trusted input or failing the entire run.

## Current Evidence

- Phase 6 created a canonical screenshot-ingestion path in [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py) with:
  - reviewed intermediate tables
  - mandatory review before benchmark generation
  - canonical season-specific filenames
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already consumes season-specific historical snapshot targets, so Phase 7 can extend trust metadata and readiness handling without inventing a second benchmark system.
- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) already distinguishes benchmark classes and trust tiers, but screenshot-derived confidence and readiness are not yet modeled explicitly.
- Historical benchmark truth still depends on screenshot-derived season snapshots, so confidence/review metadata needs to be visible enough that weak files do not silently influence model decisions.

## Constraints

- Stay within the current Python CLI workflow and existing validation surface.
- Preserve the reviewed-table contract from Phase 6 rather than replacing it.
- Keep the workflow auditable: corrections and confidence should be understandable from files on disk.
- Do not let low-confidence or incomplete screenshot-derived files silently act as benchmark truth.
- Avoid blocking the entire ranking run when a screenshot-derived benchmark is not ready; skip it with explicit reporting instead.

## Expected Focus

- Add structured correction and confidence fields to the review-table workflow.
- Define file-level readiness and confidence rollups from row-level review data.
- Carry provenance and confidence metadata into generated benchmark snapshots or their companion artifacts.
- Teach validation and run reporting to skip not-ready screenshot-derived benchmarks with clear reasons.
