# External Integrations

**Analysis Date:** 2026-04-10

## NBA Stats API

**Purpose:**
- Supplies player game logs and league-wide foul data used to derive weekly consistency and the TECH category.

**Code paths:**
- `data.py` imports `nba_api.stats.static.players` and `nba_api.stats.endpoints.playergamelogs` inside `fetch_game_logs()`.
- `data.py` imports `nba_api.stats.endpoints.leaguedashplayerstats` inside `fetch_tech_per_game()`.

**What is fetched:**
- Player game logs by player ID and season.
- League-wide per-player base stats by season, filtered by games played, then converted into TECH estimates.

**How it is used:**
- `fetch_game_logs()` returns `{season -> {player_name -> DataFrame}}` and is the source for `compute_tau()` and `derive_stats_from_logs()`.
- `fetch_tech_per_game()` estimates `TECH` as a small function of personal fouls per game and blends season weights.

**Operational details:**
- Requests are rate-limited with sleeps and retries in `data.py`.
- Results are cached locally to `game_log_cache.pkl` and `tech_cache.pkl`.
- Name matching is normalized in `normalize_player_name()` and `resolve_player_id()` so Basketball Reference names can map to NBA API player IDs.

## Basketball Reference CSVs

**Purpose:**
- Provide the season totals that feed the projection model.

**Code paths:**
- `main.py` defines `BBR_FILES` and loads them through `load_bbr_csv()` in `data.py`.
- `data.py` maps Basketball Reference column names to internal per-game columns.

**Files used:**
- `basketball_reference_2024_25_total_stats.csv`
- `basketball_reference_2023_24_total_stats.csv`

**How they are used:**
- `load_bbr_csv()` removes repeated header rows, keeps the `TOT` row for traded players, recomputes `FG%` if needed, and converts totals to per-game stats.
- `filter_qualified()` applies league minimums from `config.py` before projection.

## Validation and Market Data

**Purpose:**
- Compare projected rankings against known 14-cat snapshots and Yahoo-derived ranking data.

**Code paths:**
- `main.py` lists validation targets in `VALIDATION_TARGETS` and calls `validate.validate()`.
- `validate.py` loads the target CSVs and normalizes player names for matching.

**Files used:**
- `actual_14cat_24_25_snapshot.csv`
- `actual_14cat_23_24_snapshot.csv`
- `actual_9cat_24_25.csv`
- `yahoo_25_26_market_export.csv`

**How they are used:**
- Exact 14-cat snapshots are used as direct rank references.
- `yahoo_25_26_market_export.csv` is used twice: once as an ADP proxy via `Avg. Pick`, and once as a live snapshot via `OR`.

## Local Caches

**Purpose:**
- Avoid repeated NBA API calls and keep seasonal fetches manageable.

**Files:**
- `game_log_cache.pkl`
- `tech_cache.pkl`

**How they are used:**
- `fetch_game_logs()` backfills only missing season/player pairs when the cache already exists.
- `fetch_tech_per_game()` loads cached TECH estimates when present and only refreshes on cache deletion.

## Repository Outputs

**Purpose:**
- Persist model output in a shareable format.

**File:**
- `durant_rankings_2025_26.csv`

**Code path:**
- `save_rankings()` in `output.py` writes the final rankings DataFrame.

## Integration Characteristics

- All external integrations are pull-based, not push-based.
- There is no OAuth flow, webhook handler, queue worker, or background sync service detected.
- The repo depends on external network access only at runtime when NBA API data is fetched and caches are cold.
