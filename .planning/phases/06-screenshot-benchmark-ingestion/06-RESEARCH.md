## User Constraints

### Implementation Decisions

- **D-01:** Screenshots are the primary historical benchmark source; do not build this phase around a direct Yahoo export path.
- **D-02:** Use a hybrid flow where screenshots are the source of truth but extraction can land in a lightweight review table.
- **D-03:** Extraction should be semi-automatic, not fully manual and not direct image-to-benchmark with no review.
- **D-04:** Human review is mandatory before benchmark generation.
- **D-05:** Organize one reviewed benchmark snapshot per season for this phase.

### The Agent's Discretion

- Exact intermediate file format and folder layout.
- Whether ingestion logic lives in a new module, script, or helper layer.
- Exact review-status vocabulary and optional confidence fields.
- Exact normalization rules for player names and season metadata before benchmark generation.

### Deferred Ideas

- Full OCR automation with no review step.
- Multiple dated snapshots per season.
- Replacing screenshots with direct league exports.
- Broader model-signal work unrelated to benchmark ingestion.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Preserve deterministic, trustworthy validation behavior.
- Keep benchmark handling explicit and explainable.
- Use planning artifacts and regression tests, not ad hoc one-off scripts with no contract.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `pathlib`, and `unittest` are sufficient for schema, normalization, and ingestion testing in this phase. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already defines validation targets as file-backed benchmark entries with `path`, `label`, `benchmark_class`, `trust_tier`, `name_col`, and `rank_col`. [VERIFIED]
- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) expects validation-ready columns and already supports benchmark metadata, saved miss artifacts, and milestone contribution artifacts. [VERIFIED]
- Current exact-league historical benchmarks are flat CSVs rather than generated artifacts, which means ingestion should terminate in a validation-ready benchmark CSV shape that existing code can consume immediately. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]

## Current Gaps

- There is no ingestion module or script for screenshot-derived benchmarks. [VERIFIED]
- There is no standard review-table schema or file naming convention for historical screenshot batches. [VERIFIED]
- There is no source metadata connecting a benchmark CSV back to its screenshot batch, review state, or extraction confidence. [VERIFIED]

## Don't Hand-Roll

- Do not bypass review and write benchmark CSVs directly from OCR output.
- Do not invent a second benchmark-consumption path when the current validation loop already works with file-backed CSVs.
- Do not assume the user can reliably export the exact-league ranking table directly from Yahoo.

## Common Pitfalls

- Screenshot-derived player names can include OCR noise, team suffixes, and row breaks, so raw extracted text should be preserved for review rather than discarded early.
- If season metadata is not captured at the review-table layer, future benchmarks can become ambiguous once multiple seasons accumulate.
- Treating review state as implicit will make it too easy for partially cleaned data to look “finished.”

## Validation Architecture

- Plan 1 should define the ingestion workflow contract, intermediate schema, and repeatable file conventions.
- Plan 2 should normalize player fields and season metadata into validation-ready benchmark CSVs that the existing `main.py` target model can consume.
- Continue automated verification with `python -m unittest discover -s tests`.

## Planning Notes

- The cleanest split remains:
  1. define the screenshot-ingestion workflow and review-table contract;
  2. normalize reviewed rows into benchmark-ready seasonal CSVs with deterministic metadata.
- Phase 7 can then build confidence scoring, correction UX, and maintenance guardrails on top of this stable ingestion surface.
