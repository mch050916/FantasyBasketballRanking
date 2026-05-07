# Phase 06 Context — Screenshot Benchmark Ingestion

## Goal

Turn Yahoo screenshot history into season-specific benchmark CSVs through one repeatable ingestion path instead of one-off manual handling.

## Decisions Locked

- Screenshots remain the source of truth, but the ingestion flow may land in a lightweight review table before benchmark generation.
- Extraction is **semi-automatic**: OCR/parsing first, then a mandatory intermediate review table.
- Required fields include the validation core plus debug context:
  - `season`
  - `player_name`
  - `rank`
  - `source_batch`
  - `review_status`
  - `raw_ocr_name`
  - `team_text`
  - optional notes/confidence fields
- Phase 6 should organize **one reviewed benchmark snapshot per season**.
- Human review is mandatory before benchmark generation.

## Current Evidence

- Historical exact-league benchmarks currently live as hand-maintained CSVs such as:
  - [actual_14cat_24_25_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_24_25_snapshot.csv)
  - [actual_14cat_23_24_snapshot.csv](/Users/chesterman/FantasyBasketballRanking/actual_14cat_23_24_snapshot.csv)
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already treats these files as `historical_snapshot / snapshot_derived` benchmarks, which means the benchmark class exists but the ingestion pipeline does not.
- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) expects simple validation-ready columns such as player name and rank, so an intermediate reviewed table should eventually normalize down into that shape.
- There is currently no screenshot-ingestion module, no review-table contract, and no maintained benchmark-source metadata beyond hardcoded validation target entries.

## Constraints

- Stay in the current Python CLI architecture.
- Preserve the existing validation loop and benchmark-trust model.
- Do not assume a clean Yahoo export path exists.
- Keep human review mandatory before screenshot-derived files are treated as benchmark truth.
- Prefer one canonical reviewed snapshot per season for this first milestone slice.

## Expected Focus

- Define the review-table schema and file conventions for screenshot-derived benchmark data.
- Add a repeatable ingestion path that can transform semi-automatic extraction output into reviewed benchmark CSVs.
- Normalize season metadata and player fields cleanly enough that later confidence/review logic in Phase 7 has a stable foundation.
