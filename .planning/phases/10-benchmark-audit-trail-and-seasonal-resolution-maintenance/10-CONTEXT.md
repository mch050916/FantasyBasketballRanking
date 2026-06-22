# Phase 10 Context — Benchmark Audit Trail And Seasonal Resolution Maintenance

## Goal

Close the remaining `v1.1` audit debt by making screenshot-workflow verification evidence durable on disk and by moving narrow non-actionable NBA API suppressions into an explicit seasonal review surface.

## Decisions Locked

- Use **markdown-first verification artifacts** rather than introducing a structured reporting system first.
- Keep non-actionable suppressions in an **explicit on-disk registry** instead of leaving them implicit in code and console output.
- Make suppressions **season-scoped**, so each future season requires deliberate reaffirmation.
- Surface suppression review in **both live run health and a dedicated maintenance artifact**.
- Backfill the current milestone debt in a way that becomes a **reusable pattern for future phases**, not just a one-off cleanup.

## Current Evidence

- The `v1.1` milestone audit in [v1.1-MILESTONE-AUDIT.md](/Users/chesterman/FantasyBasketballRanking/.planning/v1.1-MILESTONE-AUDIT.md) calls out two remaining debt items this phase is meant to close:
  - missing dedicated `*-UAT.md` artifacts for phases `06-08`
  - two current-season non-actionable suppressions that should stay reviewable season to season
- Phase summaries already exist on disk for phases `06-09`, but milestone verification evidence is incomplete because several UAT results only live in thread history.
- The run-health surface in [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) and pair classification in [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) already distinguish actionable, expected, and non-actionable misses.
- The current non-actionable cases are narrow and explicit:
  - `Bojan Bogdanović (2024-25)`
  - `Saddiq Bey (2024-25)`

## Constraints

- Stay within the existing Python CLI and file-backed planning workflow.
- Do not weaken degraded-run honesty just to reduce maintenance noise.
- Keep the suppression policy explicit, reviewable, and season-scoped.
- Prefer readable markdown artifacts over heavier machine-oriented reporting for this phase.
- Avoid inventing a second maintenance workflow separate from the existing run-health and planning surfaces.

## Expected Focus

- Backfill durable markdown verification artifacts for the screenshot-benchmark milestone work.
- Establish a reusable artifact pattern so future phases do not repeat this audit gap.
- Add one explicit suppression registry file with season, player, reason, and review context.
- Update run health and/or maintenance reporting so future season reviews can see what needs reaffirmation or expiry.
