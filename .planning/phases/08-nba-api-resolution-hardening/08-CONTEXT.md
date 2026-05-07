# Phase 08 Context — NBA API Resolution Hardening

## Goal

Reduce the remaining real NBA API identity and fetch failures without weakening degraded-run honesty or hiding current-season data gaps behind broad suppressions.

## Decisions Locked

- Use **deterministic resolution first**, then add **explicit suppression** only for narrowly classified non-actionable cases.
- Suppress unresolved misses **only** when the failure is explicitly classified as non-actionable.
- Treat **current-season unresolved misses as higher severity** than historical misses unless they fall into a narrow documented exception.
- Measure success primarily by **reducing real degraded current-season misses**, with clearer classification as secondary evidence.

## Current Evidence

- The live pipeline now reports only two unresolved current-season game-log fetch misses in [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) runs:
  - `Bojan Bogdanović (2024-25)`
  - `Saddiq Bey (2024-25)`
- [data.py](/Users/chesterman/FantasyBasketballRanking/data.py) already supports:
  - deterministic player-name normalization
  - explicit expected-missing suppression for newer players lacking older seasons
  - degraded-run health reporting with missing pair counts
- `Jimmy Butler` remains a known identity edge case noted throughout the planning artifacts, even though the current degraded set has already been reduced substantially.
- Phase 7 completed the screenshot benchmark trust layer, so the remaining milestone work is now cleanly centered on the live NBA API resolution surface rather than benchmark quality.

## Constraints

- Stay in the current Python CLI and NBA API fetch architecture.
- Keep degraded-run reporting honest and explicit.
- Do not reduce degraded counts through broad or opaque suppression.
- Preserve the expected-missing logic for older seasons while keeping current-season failures prominent.
- Prefer deterministic, auditable rules over fuzzy or hard-to-explain recovery behavior.

## Expected Focus

- Strengthen deterministic identity/fetch resolution for the remaining stubborn players.
- Introduce narrow, explicit non-actionable suppression only where justified.
- Differentiate current-season unresolved failures from older-season incompleteness more clearly in health reporting.
- Re-measure degraded-run counts after the changes so the improvement is evidence-backed.
