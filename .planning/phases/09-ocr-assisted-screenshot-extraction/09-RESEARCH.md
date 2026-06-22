## User Constraints

### Implementation Decisions

- **D-01:** Use a pluggable OCR boundary rather than hardcoding Phase 9 to one OCR engine.
- **D-02:** OCR should target the existing review-table workflow first, not a richer alternate schema.
- **D-03:** Treat the OCR workflow as season-batch ingestion.
- **D-04:** Keep OCR confidence separate from reviewed `ROW_CONFIDENCE`.
- **D-05:** Emit partial rows for review instead of silently skipping hard-to-parse rows.

### The Agent's Discretion

- Exact module split between OCR helpers and existing benchmark ingestion helpers.
- Exact representation for OCR extraction records before they become review-table rows.
- How aggressively to preprocess images before handing them to an OCR backend.
- Whether the first backend is a local library adapter, a shellable binary adapter, or both behind the same interface.

### Deferred Ideas

- Full automatic benchmark generation from screenshots with no review gate.
- Rich extraction of all visible Yahoo stat columns beyond the current review-table contract.
- Fuzzy auto-correction that turns OCR guesses directly into benchmark trust.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Preserve the existing review-table and readiness workflow as the benchmark truth path.
- Keep data quality explicit and reviewable rather than clever but opaque.
- Use tests and planning artifacts, not one-off scripts with no durable contract.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `pathlib`, and `unittest` remain sufficient for review-table generation and normalization. [VERIFIED]
- `PIL` is available in the environment and can support image loading/cropping/preprocessing. [VERIFIED by local import check]
- No dedicated OCR Python package is currently installed (`pytesseract`, `easyocr`, `rapidocr_onnxruntime` absent), and no `tesseract` binary is currently available on PATH. [VERIFIED by local import/tool checks]

## Architecture Patterns

- [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py) already owns:
  - the canonical review-table schema
  - one-batch-per-season normalization
  - review gating before benchmark generation
  - metadata sidecars and readiness summaries
- OCR should therefore terminate in the existing `build_review_table(...)` / `write_review_table(...)` path rather than creating a second ingestion format. [VERIFIED]
- Raw OCR context already has first-class homes in the schema through `RAW_OCR_NAME`, `TEAM_TEXT`, `OCR_CONFIDENCE`, and `REVIEW_NOTES`. [VERIFIED]
- Historical benchmark generation is already season-keyed and source-batch-aware, so OCR batch execution should produce one season review-table artifact per run. [VERIFIED]

## Current Gaps

- There is no first-class OCR adapter contract in the repo today. [VERIFIED]
- There is no season-batch screenshot ingestion entry point that starts from image files instead of semi-manual parsed rows. [VERIFIED]
- There is no parsing layer that can transform raw OCR output into partial review-table rows while preserving extraction uncertainty and provenance. [VERIFIED]
- The environment currently lacks a bundled OCR backend, so the first implementation must not assume a single installed engine. [VERIFIED]

## Don't Hand-Roll

- Do not let OCR output bypass the reviewed-table gate and write benchmark snapshots directly.
- Do not collapse OCR confidence into reviewed benchmark confidence.
- Do not silently drop rows or players that OCR struggles to parse.
- Do not hardcode the entire feature around one unavailable local OCR dependency.

## Common Pitfalls

- If Phase 9 invents a second intermediate schema, it will drift away from the trusted Phase 6/7 benchmark path.
- If OCR output is completeness-first without preserving uncertainty, cleanup will become harder rather than easier.
- If season-batch orchestration is weak, multi-image Yahoo history will become ambiguous or out of order before review begins.
- If no backend abstraction exists, a poor first OCR engine choice can freeze the workflow into a brittle path.

## Validation Architecture

- Plan 1 should define the OCR extraction boundary, season-batch contract, and deterministic handoff into the existing review-table flow.
- Plan 2 should transform OCR output into partial-but-reviewable rows with preserved raw text, separate OCR confidence, and strong regression coverage.
- Continue automated verification with `python -m unittest discover -s tests`.
- Keep at least one manual phase check centered on whether a real screenshot batch now lands in a usable review table with fewer manual steps.

## Planning Notes

- The cleanest split is:
  1. establish the OCR adapter/batch orchestration boundary without committing to one engine forever;
  2. translate OCR output into the existing review-table contract while preserving uncertainty and partial rows.
- Because no OCR backend is currently installed, the plan should leave room for a graceful “backend unavailable” surface instead of assuming image parsing will always succeed on every machine.
