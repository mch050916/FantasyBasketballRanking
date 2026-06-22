## User Constraints

### Implementation Decisions

- **D-01:** Persist verification evidence as markdown-first artifacts.
- **D-02:** Keep non-actionable suppressions in an explicit on-disk registry.
- **D-03:** Make suppressions season-scoped so future seasons must reaffirm them deliberately.
- **D-04:** Surface maintenance information in both run health and a dedicated maintenance artifact.
- **D-05:** Backfill current milestone debt in a reusable pattern for future phases.

### The Agent's Discretion

- Exact file layout for the suppression registry and maintenance reports.
- Whether the reusable evidence pattern lives in planning docs only or also in one small helper function/module.
- The exact report shape for “expired”, “active”, and “needs review” suppressions.

### Deferred Ideas

- A fully structured JSON or database-backed audit ledger.
- Automatic suppression approval without explicit seasonal review.
- Collapsing audit trail and runtime reporting into one giant artifact.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Keep degraded-run honesty more important than cosmetic count reduction.
- Use small explicit helpers and durable files rather than hidden workflow state.
- Keep milestone planning and execution artifacts in sync with the repo state.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED]
- `pandas`, `pathlib`, and `unittest` remain sufficient for registry loading, maintenance reporting, and regression coverage. [VERIFIED]
- The repo already uses markdown planning artifacts as the dominant durable evidence surface. [VERIFIED]

## Architecture Patterns

- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already prints the run-health summary and severity split. [VERIFIED]
- [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) already classifies missing pairs and attaches explicit non-actionable reasons. [VERIFIED]
- Phase summary artifacts already exist consistently for phases `06-09`, but `*-UAT.md` coverage is missing for phases `06-08`. [VERIFIED]
- The planning directory is already the natural home for durable verification artifacts and review docs. [VERIFIED]

## Current Gaps

- There is no dedicated markdown UAT artifact on disk for phases `06`, `07`, or `08`. [VERIFIED]
- The current non-actionable suppression policy is explicit in code and output, but not yet governed by a season-reviewable registry. [VERIFIED]
- There is no dedicated maintenance artifact that shows which suppressions are active, expired, or need reaffirmation. [VERIFIED]

## Don’t Hand-Roll

- Do not hide current-season misses by broadening suppression rules.
- Do not make suppressions indefinite by default.
- Do not create a maintenance system that only exists in thread memory or console scrollback.
- Do not replace the existing run-health surface with a separate opaque reporting flow.

## Common Pitfalls

- If Phase 10 only backfills old markdown files without defining a reusable pattern, the same audit debt will return later.
- If suppression review is only documented in a registry file but never surfaced during normal runs, it will be easy to forget.
- If registry state overrides runtime truth too aggressively, honest degraded reporting can become stale or misleading.

## Validation Architecture

- Plan 1 should backfill and standardize durable markdown verification artifacts for the current milestone phases.
- Plan 2 should add the seasonal suppression registry, maintenance artifact, and live reporting integration.
- Continue automated verification with `python -m unittest discover -s tests`.
- Keep at least one manual verification centered on whether the maintenance surface is understandable without reading code.

## Planning Notes

- The cleanest split is:
  1. make the missing milestone evidence durable and reusable;
  2. make seasonal suppression policy explicit and maintainable.
- This phase should close the milestone’s remaining audit debt without reopening modeling or ingestion complexity.
