## User Constraints

### Implementation Decisions

- **D-01:** Apply strict metadata validation to both `tech_cache.pkl` and `game_log_cache.pkl`, not just the TECH cache.
- **D-02:** Treat missing metadata, malformed metadata, unreadable cache content, or metadata mismatch as "do not trust this cache".
- **D-03:** When a cache is invalid, auto-rebuild and continue the run instead of stopping for manual intervention.
- **D-04:** If any player-season log is still missing after fetch attempts for a player in the requested game-log fetch pool, complete the run but explicitly mark the run as degraded.
- **D-05:** A degraded run must list the missing player-season pairs so the user can see exactly what data remained unavailable.
- **D-06:** The degraded-run trigger should use the requested fetch pool, not a narrower final draft-pool heuristic.

### The Agent's Discretion

- The exact metadata envelope format for caches can be chosen during planning as long as it supports strict validation and rebuild-on-mismatch behavior.
- The exact console wording and formatting for degraded-run messaging can be chosen during planning as long as the warnings are prominent and specific.
- Validation health thresholds beyond "empty or obviously broken" were not locked in this discussion and can be refined in planning or a later Phase 1 follow-up.

### Deferred Ideas

- None — discussion stayed within phase scope.

## Project Constraints (from AGENTS.md)

- Keep the project in the current Python CLI shape; do not introduce a framework migration.
- Keep Basketball Reference CSVs and NBA API game logs as the core data sources.
- Fail honestly when data is missing; noisy explicit warnings are preferred over silent cache drift or silent validation failure.
- Optimize ranking logic for the custom 14-category league format, not generic 9-cat assumptions.
- Preserve the "helpers first, orchestration last" module style.
- Keep top-level constants uppercase and group them near the top of files.
- Use `pathlib.Path` for file existence checks and cache handling.
- Cache expensive NBA API work to pickle files and keep cache filenames in `config.py`.
- Prefer local fallback behavior over hard failure when external data is incomplete.
- Keep try/except blocks narrow around external integrations.
- Print progress in numbered pipeline stages from `main.py`.
- Keep user-facing CLI output concise and informative.
- Preserve the current naming, typing, and DataFrame conventions already established in the codebase.

## Standard Stack

- Python 3.12 is the runtime target for the CLI pipeline and tests. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `numpy`, and `scipy` are the core data and statistics libraries used across loading, projection, and validation. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `nba_api` is the external integration layer for player game logs and foul-related season stats. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `unittest` is the current test framework. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `tabulate` is optional for console table formatting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- Runtime caches are local pickle files, not a database or remote cache. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- `main.py` is the single orchestration entrypoint that loads season data, fetches logs, computes projections, and runs validation. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- `data.py` owns Basketball Reference ingestion, NBA API fetching, and cache persistence. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `validate.py` owns benchmark comparison and rank-miss reporting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- Current cache access is file-based and pickle-based, with no schema wrapper around the stored object today. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- The pipeline already prefers best-effort completion over hard failure for transient NBA API issues. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- Numbered progress output is already established in `main.py`, so reliability messaging should fit that console style. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]

## Don't Hand-Roll

- Do not invent a separate cache subsystem; extend the existing pickle-backed helpers in `data.py`. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- Do not make validation success depend only on a silent empty dict; the validation layer needs an explicit health signal. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- Do not infer missing logs only from the final draft pool; the phase decision explicitly says the requested fetch pool is the trigger. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]
- Do not require manual cache deletion as the normal recovery path after a stale or malformed cache is detected. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]

## Common Pitfalls

- `data.fetch_tech_per_game()` currently returns cached TECH values immediately when the file exists, without checking whether seasons or season weights changed. That is the direct stale-cache risk behind DATA-01. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `_load_cached_game_logs()` currently trusts whatever pickle object it can load and only normalizes by requested seasons; there is no metadata/version validation yet. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `fetch_game_logs()` currently backfills only missing season/player pairs, then silently persists whatever it could fetch; unresolved pairs are only visible as skip messages during the run. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `validate.validate()` currently returns `{}` after printing "No matching players found for validation." when the merged set is empty, which is too easy to miss in a larger pipeline run. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- `main.py` currently skips missing validation CSVs entirely, so a run can finish without exercising every configured benchmark target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- The current test suite covers normalization and a few happy-path calculations, but it does not exercise cache invalidation, degraded-run reporting, or validation-health reporting. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/tests/test_data.py]

## Code Examples

- `data._load_cached_game_logs(cache_path, seasons)` is the cleanest seam for adding metadata-aware cache loading because every game-log read already flows through it. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `data.fetch_game_logs(player_names, seasons, cache_file)` is the best place to collect missing player-season pairs and return or print a degraded-run summary because it already knows the requested fetch pool and retry results. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `data.fetch_tech_per_game(seasons, cache_file, season_weights)` is the natural seam for metadata checks on TECH because it already depends on the season list and weights that can go stale. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `validate.validate(...)` should be extended to report a health state such as matched count / empty-match / too-few-matches instead of only returning metrics. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]
- `main.main()` should aggregate cache rebuild warnings, missing-log pairs, and validation health into one final run summary so the user can tell whether the output is trustworthy. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]

## Planning Notes

- The biggest implementation choice is the cache envelope shape, but the phase already locks the behavior: strict validation, auto-rebuild, and no silent trust in stale or malformed cache contents. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]
- Missing-log reporting should be based on the exact `player_names × seasons` request set, not on a downstream draft cutoff, so the user sees all incomplete fetches that affected the run. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-CONTEXT.md]
- Validation needs to distinguish "worked but weak" from "effectively failed" so a successful exit does not imply trustworthy benchmark coverage. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/REQUIREMENTS.md]
- The safest plan is likely to add small helper functions for cache metadata validation and run-health summarization, then thread those results through `main.py` without changing the projection model. [ASSUMED]
