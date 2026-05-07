## User Constraints

### Implementation Decisions

- **D-01:** Use deterministic resolution first, then explicit suppression only for narrowly classified non-actionable misses.
- **D-02:** Suppress unresolved players only when the failure is explicitly classified as non-actionable.
- **D-03:** Treat current-season unresolved misses as higher severity than historical misses.
- **D-04:** Measure success primarily by reducing real degraded current-season misses, with clearer classification as secondary evidence.

### The Agent's Discretion

- Exact structure of the remaining stubborn-player resolution map or lookup layer.
- Exact classification vocabulary for unresolved player-season failures.
- Whether suppression metadata is stored inline in config, identity helpers, or `data.py`.
- Exact rerun-report wording for current-season vs historical unresolved misses.

### Deferred Ideas

- Broad fuzzy matching or heuristic identity recovery beyond deterministic overrides.
- Suppressing all repeated failures just to lower degraded counts.
- New modeling work unrelated to NBA API resolution hardening.
- Replacing NBA API with a different live data provider.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture and existing NBA API pipeline.
- Keep degraded-run reporting explicit and trustworthy.
- Prefer deterministic, auditable behavior over noisy cleverness.
- Do not hide real current-season fetch failures behind broad suppressions.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `pickle`, `pathlib`, `unittest`, and existing `nba_api` usage remain sufficient for this phase. [VERIFIED]

## Architecture Patterns

- [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) already owns:
  - deterministic cache loading and rebuilding
  - player-name resolution through shared identity helpers
  - expected-missing suppression for older seasons
  - degraded-run health reporting
- [identity.py](/Users/chesterman/FantasyBasketballRanking/identity.py) already provides canonical normalization and explicit override-backed player matching. [VERIFIED by existing Phase 2/Phase 7 behavior]
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already surfaces run-health summaries, so Phase 8 can improve the classification and measurement without inventing a new reporting channel.

## Current Gaps

- `fetch_game_logs()` still treats all unresolved non-expected misses uniformly, even when some are current-season failures and others are older-context gaps. [VERIFIED]
- The remaining stubborn cases are not yet carried through a dedicated deterministic resolution/suppression contract. [VERIFIED]
- Reruns show degraded counts, but not yet a richer classification that separates real current-season blockers from narrower non-actionable misses. [VERIFIED]

## Don't Hand-Roll

- Do not use broad suppressions to make degraded counts look better.
- Do not downgrade current-season misses into generic noise when they still affect the live projection surface.
- Do not bypass the shared identity layer with ad hoc name hacks buried inside the fetch loop.
- Do not make failure classification so dynamic that it becomes hard to audit.

## Common Pitfalls

- A “known player” list with no explicit reason model can become a silent suppression bucket.
- Treating current-season and historical misses the same makes the health summary less actionable.
- If the rerun summary does not distinguish improved resolution from mere reclassification, Phase 8 can over-claim success.

## Validation Architecture

- Plan 1 should strengthen deterministic resolution and explicit classification for the remaining stubborn player-season fetches.
- Plan 2 should improve degraded-run reporting and rerun measurement so current-season unresolved misses remain prominent and measurable.
- Continue automated verification with `python -m unittest discover -s tests`, and keep one `python main.py` rerun in the phase closeout.

## Planning Notes

- The cleanest split remains:
  1. harden deterministic identity/fetch resolution plus narrow non-actionable classification;
  2. surface the new classification clearly in run health and measure whether the true degraded current-season set shrank.
- This keeps the final milestone phase focused on real data reliability rather than cosmetic count reduction.
