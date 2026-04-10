# Coding Conventions

**Analysis Date:** 2026-04-10

## Project Shape

- Keep the codebase in small, single-purpose modules:
  - `main.py` orchestrates the pipeline.
  - `data.py` owns CSV loading, NBA API fetches, and derived stat helpers.
  - `model.py` owns projection and G-score math.
  - `validate.py` owns rank comparison utilities.
  - `output.py` owns display and CSV writing.
- Preserve the current "helpers first, orchestration last" style. Most logic lives in reusable functions rather than long script blocks.

## File and Module Style

- Use module docstrings that describe the file's role in a short banner format, as seen in `main.py`, `data.py`, `model.py`, `validate.py`, and `output.py`.
- Separate major sections with visual dividers using `# ── ... ──` comments.
- Keep top-level constants in uppercase, usually grouped near the top of the file, as in `BBR_FILES`, `OUTPUT_FILE`, and `LEAGUE_CONFIG`.
- Prefer explicit imports over wildcard imports. The codebase uses direct imports from local modules and standard libraries.

## Naming

- Use `snake_case` for functions, local variables, and helper names.
- Use `UPPER_SNAKE_CASE` for configuration objects and constants.
- Use descriptive names that reflect basketball domain concepts directly, such as `player_tau`, `league_tau`, `gp_factor`, `derived_stats`, and `tech_per_game`.
- Keep player-name normalization helpers consistent across modules:
  - `normalize_player_name` in `data.py`
  - `normalize_player_name` in `validate.py`
- Prefer names that reveal whether a value is raw, projected, weighted, derived, or cached.

## Typing

- Annotate function signatures with parameter and return types.
- Use modern union syntax like `str | None` and `list[str]`.
- Type complex collections where it improves readability, especially dicts keyed by player or season.
- Return new objects with explicit types instead of mutating ambiguous inputs when practical.

## DataFrame Conventions

- Use `pandas` DataFrames as the main data structure for season totals, projections, and validation comparisons.
- Copy DataFrames before mutating them in helper functions that should not alter caller state.
- Reset indexes after filtering or deduplication when the result is meant to be consumed downstream.
- Convert numeric columns with `pd.to_numeric(..., errors="coerce")` before doing arithmetic.
- Treat player identity as a normalized key when joining across sources.
- Keep per-game and total-stat semantics clear in column names:
  - `_T` suffix for totals from Basketball Reference
  - per-game columns without suffix
  - derived columns like `DD`, `TD`, and `TECH`

## Season and League Logic

- Centralize league settings in `config.py` and treat that file as the main season-edit point.
- Preserve category direction metadata in `LEAGUE_CONFIG["categories"]`.
- Use explicit season ordering, with the most recent season first, when combining projections or cache lookups.
- Normalize weights before projection so they sum to 1.0.
- Keep category-specific behavior close to the model layer:
  - volume weighting for `FG%`
  - direction flipping for low-is-better categories
  - variance penalty through `tau`

## Comments and Documentation

- Use comments to explain intent, tradeoffs, and business rules, not to restate obvious syntax.
- Preserve the current habit of documenting the "why" around domain choices, especially where the model makes basketball-specific assumptions.
- Keep examples and workflow notes in README-style docs or module docstrings, not inline in function bodies unless the logic is non-obvious.

## I/O and Caching

- Use `pathlib.Path` for file existence checks and cache handling.
- Cache expensive API work to pickle files, and keep the cache filenames in config.
- Keep generated outputs deterministic and file-based where possible, as in `output.py` and `main.py`.
- Treat generated CSVs and cache pickles as runtime artifacts rather than source.

## Error Handling

- Prefer local fallback behavior over hard failure when external data is incomplete:
  - missing CSV columns are tolerated when possible
  - API failures are retried or skipped
  - validation files are optional
- Keep try/except blocks narrow around external integrations, especially NBA API calls.

## Output and CLI Style

- Print progress in numbered pipeline stages, as in `main.py`.
- Keep user-facing CLI output concise and informative.
- Format tables for console display in `output.py`, with a graceful fallback when optional formatting dependencies are missing.

## Practical Editing Rules

- Match the existing formatting style in the touched file rather than introducing a new style locally.
- Prefer small, testable helpers over larger inline blocks.
- Keep new basketball-domain terminology consistent with the current column names and category labels.
