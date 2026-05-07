# Phase 06 Discussion Log

## 2026-05-07

### Topic: Ingestion source format

- Decision: Use a hybrid input path.
- Rationale: Screenshots are the real source of truth, but the workflow needs a lightweight reviewed table when extraction is messy.

### Topic: Extraction strategy

- Decision: Use a semi-automatic extraction flow.
- Rationale: OCR/parsing should help, but the workflow must always stop at an intermediate review table before benchmark generation.

### Topic: Required fields

- Decision: Keep the validation core and add debug context.
- Rationale: Keeping `raw_ocr_name`, `team_text`, and `review_status` will make screenshot cleanup and auditability much easier than a minimal rank-only contract.

### Topic: Season organization

- Decision: One reviewed benchmark snapshot per season.
- Rationale: The current historical validation flow is season-based, and one canonical snapshot per season keeps filenames and maintenance simple.

### Topic: Human review boundary

- Decision: Mandatory review before benchmark generation.
- Rationale: Screenshot-derived files become validation truth data, so trust matters more than fully automatic speed.
