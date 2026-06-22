# Phase 09 Context — OCR-Assisted Screenshot Extraction

## Goal

Reduce manual benchmark upkeep by adding a first-class OCR/parsing entry point that seeds the existing reviewed-table workflow for one full season screenshot batch at a time.

## Decisions Locked

- Use a **pluggable OCR boundary** rather than hardcoding Phase 9 to one OCR engine.
- Make OCR target the **existing review-table contract first**, not a richer alternate schema.
- Treat the main OCR workflow as **season-batch ingestion**, not one-off single-image extraction.
- Keep **OCR confidence separate** from reviewed `ROW_CONFIDENCE`; machine extraction confidence should inform review, not become trusted benchmark confidence automatically.
- When OCR cannot fully parse a row, **emit a partial row for review** instead of silently skipping the player.

## Current Evidence

- Phase 6 already established the canonical reviewed-table contract in [benchmark_ingest.py](/Users/chesterman/FantasyBasketballRanking/benchmark_ingest.py), including season, source batch, player, rank, raw OCR name, team text, and review-state fields.
- Phase 7 already treats benchmark trust as a reviewed concept with explicit corrections, readiness, and file-level confidence rollups.
- The current benchmark workflow is still seeded from semi-automatic parsed rows rather than a first-class OCR/parsing step.
- The active benchmark organization is one season-specific snapshot per reviewed batch, so the OCR step should fit that same season-level unit of work.

## Constraints

- Stay inside the current Python CLI architecture and existing benchmark ingestion surface.
- Do not invent a second benchmark schema or bypass the reviewed-table gate.
- Keep human review mandatory before benchmark generation.
- Preserve raw OCR evidence and source-batch provenance for cleanup and auditability.
- Favor completeness and explicit review work over silently dropping hard-to-parse rows.

## Expected Focus

- Define a stable OCR extraction/import boundary that can support different backends over time.
- Convert one season’s screenshot batch into the existing review-table contract in a single run.
- Preserve raw extraction text and OCR-side confidence separately from reviewed trust fields.
- Ensure ambiguous or partial OCR output still lands in the review workflow instead of disappearing.
