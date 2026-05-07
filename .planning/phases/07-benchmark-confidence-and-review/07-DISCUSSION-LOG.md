# Phase 07 Discussion Log

## 2026-05-07

### Topic: Confidence model

- Decision: Track confidence at both the row level and the file level.
- Rationale: One suspicious OCR row should not poison the entire file, but the workflow still needs a quick summary of whether the benchmark file is trustworthy enough to use.

### Topic: Review workflow shape

- Decision: Use a structured CSV review model.
- Rationale: Explicit correction fields and statuses keep the review surface simple to edit while preserving auditability.

### Topic: Readiness gate

- Decision: Use a strict ready gate.
- Rationale: A screenshot-derived benchmark should only become validation input once review is complete, required fields are present, and the file-level confidence clears the minimum threshold.

### Topic: Benchmark metadata

- Decision: Carry a core provenance bundle.
- Rationale: `season`, `source_batch`, review completion counts, confidence summary, and generated-at metadata are enough to make files trustworthy and maintainable without overloading the format.

### Topic: Failure handling

- Decision: Skip not-ready benchmarks and warn clearly.
- Rationale: That protects validation quality without blocking the rest of the ranking pipeline.
