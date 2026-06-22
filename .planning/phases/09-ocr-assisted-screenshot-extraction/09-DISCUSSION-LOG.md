# Phase 09 Discussion Log

## 2026-05-07

### Topic: OCR engine source

- Decision: Use a pluggable OCR boundary.
- Rationale: The important contract is review-table seeding that works with Yahoo screenshots, not permanent commitment to one OCR backend.

### Topic: Extraction target shape

- Decision: OCR should target the existing review-table workflow first.
- Rationale: This keeps Phase 9 aligned with the trusted Phase 6/7 ingestion and review path instead of introducing a parallel schema.

### Topic: Batch workflow

- Decision: Treat OCR as season-batch ingestion.
- Rationale: The benchmark files are already organized one reviewed snapshot per season, so the OCR workflow should match that real operating unit.

### Topic: Confidence usage

- Decision: Keep OCR confidence separate until human review.
- Rationale: OCR certainty and reviewed benchmark trust are different signals and should not be conflated.

### Topic: Failure handling

- Decision: Emit partial rows for review when OCR cannot fully parse a player row.
- Rationale: It is better to preserve incomplete evidence for cleanup than to silently lose players.
