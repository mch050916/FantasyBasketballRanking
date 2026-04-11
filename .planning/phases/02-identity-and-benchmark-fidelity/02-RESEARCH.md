## User Constraints

### Implementation Decisions

- **D-01:** Use deterministic normalized-name matching plus an explicit manual override map as the identity source of truth for cross-source player resolution.
- **D-02:** Do not attempt a full player-ID migration in this phase.
- **D-03:** Treat older-season absences as expected when a player was not yet in the NBA, and exclude those expected-missing cases from degraded-run warnings.
- **D-04:** Keep genuinely unresolved player-season misses visible in degraded-run reporting.
- **D-05:** Keep screenshot-derived historical 14-cat files in the validation flow, but label them explicitly as lower-trust snapshot benchmarks.
- **D-06:** Treat direct CSV exports as the higher-trust benchmark tier and make that difference visible in reporting.
- **D-07:** Use a deterministic benchmark matching order: explicit override map first, normalized-name matching second, and otherwise no match.
- **D-08:** Do not introduce fuzzy matching in this phase.

### The Agent's Discretion

- The exact file/module split for the shared identity helpers and override map.
- The exact shape of benchmark trust metadata as long as the console output and structured validation data make the trust tier explicit.

### Deferred Ideas

- Full provider-ID unification across all sources.
- Fuzzy benchmark matching.

## Project Constraints (from AGENTS.md)

- Keep the project in the current Python CLI architecture — do not introduce a framework migration.
- Keep Basketball Reference CSVs and NBA API game logs as the core data sources.
- Rankings must degrade honestly when data is incomplete.
- Preserve the small-helper, single-purpose-module style already used in the repo.
- Use `pathlib.Path` for file handling and keep generated outputs deterministic and file-based.
- Keep user-facing CLI output concise and informative.
- Prefer localized fallback behavior over hard failure when external data is incomplete.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `pandas`, `numpy`, and `scipy` remain the core data/validation libraries. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `nba_api` remains the external source for player logs and foul-derived context. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]
- `unittest` is the current test framework and should remain the verification surface for this phase. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/AGENTS.md]

## Architecture Patterns

- `main.py` orchestrates all benchmark configuration and reporting, so benchmark trust labeling should plug into `VALIDATION_TARGETS` rather than add a second output path. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- `data.py` currently owns NBA API name resolution and degraded-run reporting, so expected-missing season logic belongs near the fetch-health path. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `validate.py` currently rebuilds its own normalized-name keys and benchmark rank series, making it the natural place to centralize stricter deterministic matching once a shared helper exists. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- Phase 1 established explicit health/status reporting; Phase 2 should extend that explicitness to benchmark trust tiers and identity match handling instead of introducing silent heuristics. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/01-reliability-guardrails/01-02-SUMMARY.md]

## Don't Hand-Roll

- Do not add fuzzy matching heuristics; the phase decision explicitly rejects them. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/02-identity-and-benchmark-fidelity/02-CONTEXT.md]
- Do not leave identity overrides duplicated independently across `data.py` and `validate.py`; Phase 2 should create a single deterministic source of truth. [ASSUMED]
- Do not suppress all older-season misses automatically; only expected missing seasons for not-yet-in-NBA players should be removed from degraded-run noise. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/02-identity-and-benchmark-fidelity/02-CONTEXT.md]
- Do not present screenshot-derived snapshots as equivalent to direct exports; trust tier must stay explicit. [CITED: /Users/chesterman/FantasyBasketballRanking/.planning/phases/02-identity-and-benchmark-fidelity/02-CONTEXT.md]

## Common Pitfalls

- `resolve_player_id()` in `data.py` only tries exact and normalized NBA API names today, which is why `Jimmy Butler` can still fall through when the upstream name surface differs unexpectedly. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `fetch_game_logs()` currently treats every requested player-season pair as equally degradative, which over-reports older-season misses for newer players. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `validate.py` currently rebuilds benchmark keys using only normalized names, with no deterministic override layer and no benchmark trust metadata in the result object. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]
- `main.py` currently labels benchmark targets mostly by filename/note strings, so trust-tier semantics are present informally but not normalized into a consistent reporting model. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]

## Code Examples

- A new shared helper module such as `identity.py` is the cleanest seam for a deterministic override map because both `data.py` and `validate.py` need the same player-key logic. [ASSUMED]
- `data.fetch_game_logs()` already calculates `missing_pairs`; adding an `expected_missing_pairs` filter there would let degraded-run summaries stay honest without flagging impossible older-season data. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/data.py]
- `main.VALIDATION_TARGETS` already carries per-target notes and config, so adding an explicit trust-tier field there is lower-risk than inventing a second benchmark registry. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/main.py]
- `validate.validate()` already returns structured dictionaries after Phase 1, so extending that structure with benchmark trust metadata and deterministic match bookkeeping fits the current pattern. [VERIFIED: /Users/chesterman/FantasyBasketballRanking/validate.py]

## Validation Architecture

- Phase 2 should keep the current `python -m unittest discover -s tests` loop as both quick and full verification because the repo still has a small standard-library suite.
- Add focused unit coverage for the shared identity helper layer, including normalized names, explicit overrides, and deterministic no-match behavior.
- Add fetch-health tests that prove expected-missing older seasons for not-yet-in-NBA players do not count toward degraded-run summaries, while genuine misses still do.
- Add benchmark-validation tests that prove trust tiers are surfaced consistently and that exact-league snapshots and Yahoo exports run through one normalized target model.
- End-to-end verification should still include `python main.py`, with acceptance based on seeing Phase 2’s clearer trust labeling and cleaner degraded-run output in addition to a successful exit.

## Planning Notes

- The cleanest two-plan split is:
  1. build the deterministic identity layer and expected-missing fetch policy;
  2. normalize benchmark target handling and trust-tier reporting on top of that layer.
- Plan 1 should establish the single identity source of truth first so Plan 2 can consume it rather than duplicate matching logic.
- Because `VALIDATION_TARGETS` already centralizes benchmark configuration, Plan 2 should likely standardize that structure instead of introducing ad hoc per-target branches in `main.py`.
- The biggest correctness risk is silent overmatching, so every matching rule in Phase 2 should be explainable from code and covered by tests.
