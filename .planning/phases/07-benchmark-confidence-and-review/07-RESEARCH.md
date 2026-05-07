## User Constraints

### Implementation Decisions

- **D-01:** Confidence must exist at both the row level and the file level.
- **D-02:** Review should stay CSV-based, but use explicit correction fields and statuses instead of freeform edits only.
- **D-03:** Screenshot-derived benchmarks are only ready when review is complete, required fields are present, and the file-level confidence clears a threshold.
- **D-04:** Generated benchmark artifacts should carry core provenance metadata.
- **D-05:** Not-ready screenshot-derived benchmarks should be skipped with a clear warning rather than used silently or turned into hard pipeline failures.

### The Agent's Discretion

- Exact correction-field names and review-state vocabulary beyond the locked intent.
- Whether file-level confidence travels as extra CSV columns, a sidecar artifact, or both.
- Exact readiness-threshold formula and rollup logic from row-level confidence to file-level summary.
- Exact CLI and validation-report wording for skip reasons and readiness summaries.

### Deferred Ideas

- Full UI tooling for screenshot review beyond CSV-based editing.
- Fuzzy matching or OCR-driven confidence inference unrelated to the reviewed-table contract.
- Replacing screenshot-derived benchmarks with direct Yahoo exports.
- Broader model-tuning changes unrelated to benchmark trust and review.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Keep validation behavior deterministic, explicit, and trustworthy.
- Preserve the Phase 6 reviewed-table contract rather than introducing a separate benchmark-ingestion stack.
- Keep benchmark trust auditable from files on disk, not hidden in transient runtime state.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `pathlib`, `unittest`, and existing CSV-based helpers remain sufficient for review-state, confidence, and readiness work. [VERIFIED]

## Architecture Patterns

- [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py) already owns the screenshot review-table schema and benchmark generation path. [VERIFIED]
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already defines historical snapshot validation targets as file-backed benchmark entries. [VERIFIED]
- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) already supports benchmark classes, trust tiers, persisted history, and explicit status reporting, which makes it the right place to surface readiness-aware skip behavior. [VERIFIED]

## Current Gaps

- The review table does not yet support explicit correction fields beyond notes. [VERIFIED]
- There is no row-level confidence contract or file-level readiness rollup for screenshot-derived benchmarks. [VERIFIED]
- Validation cannot yet distinguish “file exists but is not ready for trust” from ordinary skipped/missing benchmark cases. [VERIFIED]
- Historical screenshot benchmarks have canonical filenames, but not yet a strong maintainability/provenance summary for future seasonal upkeep. [VERIFIED]

## Don't Hand-Roll

- Do not silently treat all reviewed rows as equally trustworthy.
- Do not let low-confidence screenshot-derived files look equivalent to stronger benchmark sources.
- Do not force not-ready screenshot benchmarks through validation just because the CSV exists.
- Do not duplicate benchmark metadata logic in a second reporting path when `validate.py` already owns benchmark output semantics.

## Common Pitfalls

- If corrections overwrite raw OCR context with no separate audit field, later review becomes much harder.
- If readiness is based only on “all rows reviewed,” a fully reviewed but low-confidence file can still look cleaner than it really is.
- If provenance is not persisted alongside generated benchmark files, future seasons will be hard to compare or maintain consistently.
- If skip reasons are vague, users may confuse “not ready” with “missing file” and lose trust in the benchmark loop.

## Validation Architecture

- Plan 1 should extend the Phase 6 review-table contract with explicit correction and confidence fields plus file-level readiness rollups.
- Plan 2 should integrate readiness and provenance into benchmark generation, validation target handling, and user-facing skip/confidence reporting.
- Continue automated verification with `python -m unittest discover -s tests`.

## Planning Notes

- The cleanest split remains:
  1. strengthen the review-table and readiness contract in `benchmark_ingest.py`;
  2. surface readiness/confidence/provenance cleanly through generated benchmark artifacts and validation reporting.
- Phase 8 can then focus on NBA API resolution hardening without mixing in more screenshot-trust work.
