# Architecture

**Analysis Date:** 2026-04-10

## Pattern Overview

**Overall:** Single-command Python analytics pipeline

**Key Characteristics:**
- One entrypoint runs the full ranking flow from raw CSV inputs to ranked output.
- Data ingestion, statistical modeling, formatting, and validation are split into small modules.
- State is mostly file-backed through CSV inputs, pickle caches, and CSV outputs.
- External dependencies are limited to `pandas`, `numpy`, `scipy`, `nba_api`, and `tabulate`.

## Layers

**Orchestration Layer:**
- Purpose: Coordinate the ranking run from start to finish.
- Contains: Season file selection, configuration wiring, cache paths, validation targets, console progress output.
- Depends on: `config.py`, `data.py`, `model.py`, `output.py`, `validate.py`.
- Used by: `main.py`.

**Data Ingestion Layer:**
- Purpose: Normalize season totals CSVs and fetch API-backed player context.
- Contains: Basketball Reference CSV loading, qualification filtering, player-name normalization, NBA API game-log retrieval, TECH estimation, DD/TD derivation.
- Depends on: `pandas`, `numpy`, `nba_api`, `pickle`, `re`, `unicodedata`.
- Used by: `main.py` and the tests in `tests/test_data.py`.

**Projection and Scoring Layer:**
- Purpose: Turn season stats and game logs into league-adjusted player values.
- Contains: Trend weighting, games-played discounting, FG% blending, weekly variance (`tau`), Box-Cox transformation, DURANT G-score calculation.
- Depends on: `pandas`, `numpy`, `scipy.stats.boxcox`.
- Used by: `main.py` and the tests in `tests/test_model.py`.

**Presentation and Validation Layer:**
- Purpose: Render rankings for humans and compare them to reference CSVs.
- Contains: Console table formatting, CSV export, player-name normalization for comparison, rank-series construction, accuracy metrics.
- Depends on: `pandas`, `scipy.stats.spearmanr`, optional `tabulate`.
- Used by: `main.py` and the tests in `tests/test_validate.py`.

## Data Flow

**Ranking Run:**

1. User runs `python main.py`.
2. `main.py` loads `LEAGUE_CONFIG` from `config.py` and season totals CSVs from the project root.
3. `data.load_bbr_csv()` converts Basketball Reference totals into per-game player rows and `data.filter_qualified()` trims the pool to roster-eligible players.
4. `data.fetch_game_logs()` loads or backfills cached NBA API game logs for the top-minute players.
5. `data.derive_stats_from_logs()` converts game logs into DD and TD rates.
6. `data.fetch_tech_per_game()` estimates TECH per game from foul rate and caches the result.
7. `model.compute_tau()` measures week-to-week category volatility from the same game logs.
8. `model.project_stats()` combines season projections, trend adjustments, GP discounting, and derived stats into a single player frame.
9. `model.compute_g_scores()` scores each category, sums `TOTAL_VALUE`, and assigns `RANK`.
10. `output.format_rankings()` prints the top players and `output.save_rankings()` writes the full CSV.
11. `validate.validate()` compares the rankings to any local reference CSVs that exist.

**State Management:**
- Persistent state is file-based, not database-backed.
- `game_log_cache.pkl` and `tech_cache.pkl` store expensive NBA API results between runs.
- Projection input state comes from committed CSVs in the repository root.
- Output state is a generated CSV saved in the repository root.

## Key Abstractions

**Season Table:**
- Purpose: One player-season snapshot of per-game stats.
- Examples: DataFrames returned by `data.load_bbr_csv()`.
- Pattern: Normalized wide table keyed by `PLAYER_NAME`.

**Game Log Map:**
- Purpose: Preserve season-specific weekly history for variance and derived stats.
- Examples: `{"2024-25": {"Nikola Jokić": DataFrame}}` from `data.fetch_game_logs()`.
- Pattern: Nested dictionary keyed by season and player.

**Projection Row:**
- Purpose: Unified player record used for scoring and output.
- Examples: Rows from `model.project_stats()` with `GP_FACTOR`, category projections, `TECH`, `DD`, `TD`, `GP`, `MIN`.
- Pattern: Derived DataFrame built from season lookups and weighted calculations.

**Ranking Table:**
- Purpose: Final ordered result for humans and downstream validation.
- Examples: DataFrame returned by `model.compute_g_scores()`.
- Pattern: Sorted by `TOTAL_VALUE` descending with `RANK` assigned from row order.

## Entry Points

**CLI Entry:**
- Location: `main.py`
- Triggers: Direct execution with `python main.py`.
- Responsibilities: Load inputs, coordinate the pipeline, print progress, save rankings, run validations.

## Error Handling

**Strategy:** Fail fast for missing data, tolerate external fetch failures, and continue with best-effort caches.

**Patterns:**
- `data.fetch_game_logs()` retries API requests and skips unresolved players after repeated failures.
- `data.fetch_tech_per_game()` catches endpoint errors per season and keeps partial results.
- `main.py` skips validation targets that are not present on disk.
- `validate.validate()` returns an empty result if no player names match.

## Cross-Cutting Concerns

**Normalization:**
- Player names are normalized in both `data.py` and `validate.py` so accented or punctuated names still match.

**Caching:**
- The NBA API layer persists expensive responses to pickle files to keep repeated runs practical.

**Calibration:**
- League size, roster size, category weights, and season weights all flow from `config.py` into scoring.

**Reporting:**
- Console output is human-readable by default, with a `tabulate` fallback when the optional package is absent.

*Architecture analysis: 2026-04-10*
