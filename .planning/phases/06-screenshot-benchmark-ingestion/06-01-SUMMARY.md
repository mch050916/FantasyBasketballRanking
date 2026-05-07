---
phase: 06-screenshot-benchmark-ingestion
plan: 01
subsystem: benchmark-ingestion
tags: [screenshots, benchmarks, review-table, validation, unittest]
requires: []
provides:
  - A canonical review-table schema for screenshot-derived benchmark rows
  - A repeatable ingestion entry point for one screenshot batch per season
  - Regression tests for schema shape, season organization, and file naming
affects: [benchmark-ingestion, validation-trust, phase-06]
tech-stack:
  added: [benchmark_ingest.py]
  patterns: [review-table contract, one-snapshot-per-season ingestion]
key-files:
  created: [benchmark_ingest.py, tests/test_benchmark_ingest.py]
  modified: [.planning/PROJECT.md]
key-decisions:
  - "Use a reviewed intermediate table as the mandatory landing zone for screenshot extraction output"
  - "Keep one ingestion batch mapped to one season-specific snapshot contract"
patterns-established:
  - "Screenshot-derived benchmark rows preserve noisy OCR text for review instead of normalizing it away too early"
  - "Canonical filename helpers define one review table and one benchmark snapshot per season"
requirements-completed: [INGEST-01]
duration: 0min
completed: 2026-05-07
---

# Phase 06 Plan 01 Summary

**A stable screenshot review-table contract now exists for historical benchmark ingestion**

## Accomplishments

- Added [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py) with a canonical intermediate schema, review statuses, filename conventions, and one-batch ingestion helpers.
- Added [tests/test_benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/tests/test_benchmark_ingest.py) to protect schema shape, season-batch organization, and file naming.
- Updated [PROJECT.md](/Users/chesterman/FantasyBasketballRanking/.planning/PROJECT.md) so the reviewed-table ingestion contract is part of shared project context rather than code-only knowledge.

## Verification

- `python -m unittest discover -s tests`

## Result

- Screenshot-derived benchmark rows now have one explicit review-table shape with required fields for season, source batch, player, rank, raw OCR text, team text, review status, notes, and optional confidence.
- One ingestion batch now maps deterministically to one season-specific review table.
- The project has canonical naming for:
  - review tables like `actual_14cat_24_25_review.csv`
  - benchmark snapshots like `actual_14cat_24_25_snapshot.csv`

## Notes

- Phase 6 still intentionally stops short of raw OCR implementation; the public contract accepts semi-automatic parsed rows and preserves noisy source text for review.

