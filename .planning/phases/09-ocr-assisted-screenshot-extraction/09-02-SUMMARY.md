---
phase: 09-ocr-assisted-screenshot-extraction
plan: 02
subsystem: benchmark-ingestion
tags: [ocr, review-table, confidence-semantics, unittest]
requires:
  - 09-01
provides:
  - OCR-to-review-table translation that preserves the existing ingestion schema
  - Separate OCR confidence semantics from reviewed row confidence
  - Explicit partial-row preservation for OCR extraction cleanup
affects: [benchmark-ingestion, validation-inputs, phase-09, milestone-v1.1]
tech-stack:
  added: []
  patterns: [review-table-first OCR translation, partial-row preservation]
key-files:
  created: []
  modified: [benchmark_ingest.py, tests/test_benchmark_ingest.py]
key-decisions:
  - "Keep OCR confidence separate from reviewed ROW_CONFIDENCE"
  - "Preserve incomplete OCR rows for review instead of dropping them"
patterns-established:
  - "OCR-assisted extraction now terminates in the existing review-table contract"
  - "Machine uncertainty remains visible without being promoted to benchmark trust automatically"
requirements-completed: []
duration: 0min
completed: 2026-05-09
---

# Phase 09 Plan 02 Summary

**OCR output now lands in the trusted review-table workflow without weakening the human review gate**

## Accomplishments

- Added OCR-line translation helpers in [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py) so OCR extraction records become the existing review-table shape instead of a second ingestion schema.
- Preserved OCR-side uncertainty explicitly by keeping `OCR_CONFIDENCE` separate from reviewed `ROW_CONFIDENCE`.
- Added partial-row preservation behavior so hard-to-parse OCR rows still surface for review with:
  - raw OCR text
  - inferred row-order rank when needed
  - explicit review notes for missing team or name cleanup
- Expanded [tests/test_benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/tests/test_benchmark_ingest.py) to prove:
  - OCR confidence does not become reviewed trust automatically
  - incomplete rows are preserved instead of skipped silently
  - OCR-assisted review tables still fit the downstream benchmark workflow

## Verification

- `python -m unittest discover -s tests`

## Result

- OCR-assisted extraction now reduces manual screenshot prep without creating a parallel benchmark format.
- The review-first trust model stays intact even when OCR output is messy.
- Later maintenance phases can build on one stable review-table contract rather than reconciling multiple ingestion schemas.

## Notes

- The OCR translation layer is deliberately completeness-first. It prefers a noisy review row over silently losing a player from the benchmark seed set.
