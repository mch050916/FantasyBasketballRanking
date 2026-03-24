"""
data.py — Data loading and NBA API fetching
=============================================
Handles:
  - Loading Basketball Reference season CSV files
  - Fetching per-player game logs from the NBA API (with caching)
  - Fetching TECH stats (estimated from foul rate)
  - Deriving DD and TD per game from game logs

You should rarely need to edit this file. If the NBA API column names change
or Basketball Reference changes their CSV format, fixes go here.
"""

import pandas as pd
import numpy as np
import time
import pickle
from pathlib import Path


# ── Basketball Reference CSV loading ────────────────────────────────────────

BBR_COL_MAP = {
    "Player": "PLAYER_NAME",
    "G":      "GP",
    "MP":     "MIN_TOTAL",
    "FG":     "FGM_T",
    "FGA":    "FGA_T",
    "FG%":    "FG%",
    "3P":     "3PTM_T",
    "FT":     "FTM_T",
    "TRB":    "REB_T",
    "AST":    "AST_T",
    "STL":    "ST_T",
    "BLK":    "BLK_T",
    "TOV":    "TO_T",
    "PF":     "PF_T",
    "PTS":    "PTS_T",
}


def load_bbr_csv(path: str) -> pd.DataFrame:
    """
    Load a Basketball Reference season totals CSV and convert to per-game stats.

    Handles:
    - Repeated header rows mid-file (BBR quirk)
    - Traded players: keeps the TOT (full-season aggregate) row only
    - Missing FG%: recomputes from FGM/FGA if needed
    """
    df = pd.read_csv(path, skipinitialspace=True)
    df = df.dropna(subset=["Player"])
    df = df[df["Player"] != "Player"]   # BBR repeats header row mid-file

    # For traded players, BBR has one row per team + a TOT aggregate row.
    # Keep only TOT — it's the accurate full-season picture.
    df["_is_tot"] = (df["Team"] == "TOT").astype(int)
    df = df.sort_values("_is_tot", ascending=False)
    df = df.drop_duplicates(subset="Player", keep="first")
    df = df.drop(columns=["_is_tot"])

    available = {k: v for k, v in BBR_COL_MAP.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    for col in df.columns:
        if col != "PLAYER_NAME":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["GP"])
    df["GP"] = df["GP"].astype(int)

    # Convert totals to per-game
    gp = df["GP"].replace(0, np.nan)
    df["MIN"]  = df["MIN_TOTAL"] / gp
    df["FGM"]  = df["FGM_T"] / gp
    df["FGA"]  = df["FGA_T"] / gp
    df["3PTM"] = df["3PTM_T"] / gp
    df["FTM"]  = df["FTM_T"] / gp
    df["REB"]  = df["REB_T"] / gp
    df["AST"]  = df["AST_T"] / gp
    df["ST"]   = df["ST_T"] / gp
    df["BLK"]  = df["BLK_T"] / gp
    df["TO"]   = df["TO_T"] / gp
    df["PF"]   = df["PF_T"] / gp
    df["PTS"]  = df["PTS_T"] / gp

    if "FG%" not in df.columns or df["FG%"].isna().all():
        df["FG%"] = df["FGM"] / df["FGA"].replace(0, np.nan)
    df["FG%"] = pd.to_numeric(df["FG%"], errors="coerce")

    # DD, TD, TECH come from game logs — initialise to 0 as placeholders
    for cat in ["TECH", "DD", "TD"]:
        df[cat] = 0.0

    drop_cols = [c for c in df.columns if c.endswith("_T") or c == "MIN_TOTAL"]
    df = df.drop(columns=drop_cols, errors="ignore")

    return df


def filter_qualified(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Keep only players who meet minimum games and minutes thresholds."""
    mask = (df["GP"] >= config["min_games"]) & (df["MIN"] >= config["min_mpg"])
    return df[mask].reset_index(drop=True)


# ── NBA API: game log fetching ───────────────────────────────────────────────

def fetch_game_logs(player_names: list[str],
                    seasons: list[str],
                    cache_file: str) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Fetch per-game logs for each player for each season from the NBA API.

    Returns: { season -> { player_name -> DataFrame } }

    Caches results to disk — delete the cache file to force a fresh fetch.
    Uses retry logic with exponential backoff to handle NBA API rate limiting.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        print(f"   Loading game logs from cache: {cache_file}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    print(f"   No cache found — fetching from NBA API (~6-8 min for 150 players)...")
    print(f"   This only runs once. Results saved to {cache_file}")

    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelogs

    all_players = nba_players.get_players()
    name_to_id  = {p["full_name"]: p["id"] for p in all_players}

    result = {season: {} for season in seasons}
    total  = len(player_names) * len(seasons)
    done   = 0

    for player_name in player_names:
        player_id = name_to_id.get(player_name)

        if player_id is None:
            # Try case-insensitive match for name variations (accents, etc.)
            lower   = player_name.lower()
            matches = [p for p in all_players if p["full_name"].lower() == lower]
            if matches:
                player_id = matches[0]["id"]
            else:
                done += len(seasons)
                continue

        for season in seasons:
            done += 1
            pct = done / total * 100

            for attempt in range(3):
                try:
                    time.sleep(1.5 + attempt * 3)   # 1.5s → 4.5s → 7.5s
                    logs = playergamelogs.PlayerGameLogs(
                        player_id_nullable=player_id,
                        season_nullable=season,
                    )
                    df = logs.get_data_frames()[0]
                    if not df.empty:
                        result[season][player_name] = df
                    print(f"   [{pct:4.0f}%] {player_name} {season}   ", end="\r")
                    break

                except Exception as e:
                    if attempt < 2:
                        wait = 5 + attempt * 5   # 5s → 10s between retries
                        print(f"\n   [retry {attempt+1}] {player_name} {season} — waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"\n   [skip] {player_name} {season}: failed after 3 attempts")

    print()

    with open(cache_path, "wb") as f:
        pickle.dump(result, f)
    print(f"   Game logs cached to {cache_file}")

    return result


# ── NBA API: TECH stats ──────────────────────────────────────────────────────

def fetch_tech_per_game(seasons: list[str],
                        cache_file: str,
                        season_weights: list[float]) -> dict[str, float]:
    """
    Estimate technical fouls per game for each player.

    The NBA API does not expose per-player technical fouls in any clean
    endpoint. We estimate from PF rate using the base stats endpoint:
        TECH ≈ 0.012 × PF_per_game

    This gives ~0.042 TECH/game for foul-prone players (PF ~3.5) and
    ~0.018 for disciplined players (PF ~1.5) — meaningfully differentiated
    without scraping. The TECH category weight of 0.3 limits error impact.

    Returns: { player_name -> estimated_tech_per_game }
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        print("   Loading TECH from cache...")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    from nba_api.stats.endpoints import leaguedashplayerstats

    combined: dict[str, list] = {}

    for i, season in enumerate(seasons):
        try:
            time.sleep(1.5)
            print(f"   Fetching foul stats for {season} (TECH estimation)...")
            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                measure_type_detailed_defense="Base",
            )
            df = stats.get_data_frames()[0]
            df = df[df["GP"] >= 10]

            w = season_weights[i] if i < len(season_weights) else season_weights[-1]
            for _, row in df.iterrows():
                name = row["PLAYER_NAME"]
                pf   = float(row.get("PF", 2.5))
                tech_estimate = max(0.01, 0.012 * pf)
                if name not in combined:
                    combined[name] = []
                combined[name].append((tech_estimate, w))

            print(f"   TECH estimated for {len(df)} players in {season}")

        except Exception as e:
            print(f"   [warn] TECH fetch failed for {season}: {e}")

    result = {}
    for name, vals in combined.items():
        total_w = sum(w for _, w in vals)
        result[name] = sum(v * w for v, w in vals) / total_w if total_w > 0 else 0.05

    with open(cache_path, "wb") as f:
        pickle.dump(result, f)
    print(f"   TECH data cached for {len(result)} players")

    return result


# ── Derive DD and TD from game logs ──────────────────────────────────────────

def derive_stats_from_logs(game_logs: dict[str, dict[str, pd.DataFrame]]) \
        -> dict[str, dict[str, float]]:
    """
    Compute DD and TD per game from raw game logs.

    The NBA API game log already provides DD2 (double-double) and TD3
    (triple-double) columns — no manual category counting needed.

    For players appearing in multiple seasons, uses the most recent season's
    value rather than averaging, since recency matters most for projection.

    Returns: { player_name -> { 'DD': float, 'TD': float } }
    """
    derived: dict[str, dict[str, float]] = {}

    # Iterate seasons in order (most recent first, as game_logs is ordered)
    for season, season_logs in game_logs.items():
        for player_name, logs in season_logs.items():
            if logs.empty:
                continue

            gp = len(logs)
            if gp == 0:
                continue

            # Only set if not already set by a more recent season
            if player_name not in derived:
                derived[player_name] = {}

            if "DD" not in derived[player_name] and "DD2" in logs.columns:
                derived[player_name]["DD"] = logs["DD2"].sum() / gp

            if "TD" not in derived[player_name] and "TD3" in logs.columns:
                derived[player_name]["TD"] = logs["TD3"].sum() / gp

    return derived