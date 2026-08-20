# DURANT Fantasy Basketball Ranker

A fantasy basketball ranking tool for custom head-to-head category leagues, built around the DURANT (Dynamic Unbiased Rankings Applying Normalised Transformations) methodology.

Designed for leagues with non-standard categories — this one scores 14 categories including double-doubles, triple-doubles, technical fouls, personal fouls, and flagrant fouls alongside the standard stats.

## Why DURANT instead of Yahoo's rankings

Yahoo uses plain z-scores, which measure how much a player produces relative to the league average. DURANT adds a variance penalty that makes it specifically suited to weekly head-to-head leagues:

```
G = (player_stat − league_mean) / √(σ² + κ · τ²)
```

- **σ** — standard deviation across the rostered player pool
- **τ** — the player's own week-to-week variance in that category
- **κ** — a roster-size scaling factor (`1 + 1/roster_size`)

The key insight: a player who scores 30 points one week and 8 the next has the same season average as a consistent 19-point scorer — but the volatile player is less valuable in H2H because that 8-point week likely loses you the category. DURANT penalises that volatility. Yahoo ignores it entirely.

## League setup

This tool is configured for a 10-team, 13-player roster league with these 14 categories:

| Category | Direction | Notes |
|----------|-----------|-------|
| FGM | High | |
| FG% | High | Volume-weighted by FGA |
| FTM | High | |
| 3PTM | High | |
| PTS | High | |
| REB | High | |
| AST | High | |
| ST | High | |
| BLK | High | |
| TO | Low | Lower is better |
| PF | Low | Lower is better |
| TECH | Low | Estimated from foul rate |
| DD | High | Double-doubles per game |
| TD | High | Triple-doubles per game |

FF (flagrant fouls) was considered but removed — the NBA API has no reliable per-player data source, and assigning everyone the same default value produces a G-score of zero for all players (fake precision).

## Project structure

```
├── main.py          # Entry point — run this
├── config.py        # League settings — edit this each season
├── data.py          # Data loading: BBR CSVs + NBA API fetching
├── model.py         # Core DURANT formula: projections, tau, G-scores
├── output.py        # Formatting and saving rankings
├── validate.py      # Accuracy checks against known rankings
└── requirements.txt
```

## Trade analyzer

Given all 10 league rosters, evaluates a two-team trade by how it changes each
side's expected categories won per week against the league field.

```bash
python scripts/analyze_trade.py --team "Chester" --partner "Bob" \
    --give "Jalen Johnson,Kyrie Irving" --get "Alperen Sengun"
```

Copy `rosters_example.csv` to `rosters.csv` and fill in all 10 rosters first.
Run `main.py` at least once beforehand so the game-log cache exists — the
analyzer reads that cache rather than fetching, and on a cold cache it would
only pull the rostered players, giving a thinner league-wide sample than the
full pipeline builds.

A simulated week resamples each player's real observed weeks from the cached
game logs, rescaled to this season's projection — rather than assuming a
normal distribution, which reports a confident coin flip on sparse categories
like TD and TECH where both teams realistically finish level. Ties count as
half a win and are reported per category.

This changes no player's score: `durant_rankings_2026_27.csv` is unaffected.

## Setup

```bash
git clone https://github.com/chesterman/durant-fantasy-ranker
cd durant-fantasy-ranker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Data

Download season totals CSVs from [Basketball Reference](https://www.basketball-reference.com/leagues/NBA_2025_totals.html) (use the Share > CSV option). Place them in the project root:

```
basketball_reference_2024_25_total_stats.csv
basketball_reference_2023_24_total_stats.csv
```

Update `BBR_FILES` in `main.py` and `game_log_seasons` in `config.py` to match.

## Usage

```bash
python main.py
```

On first run, the script fetches game logs for the top 150 players from the NBA API. This takes around 6–8 minutes. Results are cached to `game_log_cache.pkl` — subsequent runs are instant.

Output is printed to the console and saved to `durant_rankings_2025_26.csv`.

## Updating for a new season

1. Download the new Basketball Reference CSV
2. Add it to `BBR_FILES` in `main.py` (most recent first)
3. Update `game_log_seasons` in `config.py`
4. Delete `game_log_cache.pkl` and `tech_cache.pkl`
5. Run `python main.py`

The only file you need to edit regularly is `config.py` — category weights, league size, and roster settings all live there.

## Tuning category weights

The weights in `config.py` encode how much each category matters in weekly H2H matchups. Some principles:

- **FG%** is weekly noise — discounted to 0.5
- **ST, BLK, 3PTM** are low-count and volatile — discounted to 0.8
- **TO** — elite players naturally create more turnovers; the penalty is discounted to 0.5
- **DD/TD** — currently set to 0.8; increase if double-doubles frequently decide your matchups

After each season, check which categories your team won and lost most often. If you're consistently losing a category you expected to win, its weight may be understated.

## Validation

The repo includes `actual_9cat_24_25.csv` — Yahoo's actual 2024-25 rankings for a standard 9-category league. Running `main.py` automatically compares our 14-category projections against this as a directional accuracy check (Spearman correlation, hit rate within ±5 ranks, MAE).

Since the category sets differ, perfect agreement isn't expected — but correlation above 0.65 and a hit rate above 30% suggests the model is broadly sensible.
