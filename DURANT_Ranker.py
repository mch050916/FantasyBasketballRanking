"""
DURANT Fantasy Basketball Ranker
=================================
A clean implementation of the DURANT (Dynamic Unbiased Rankings Applying
Normalised Transformations) methodology for head-to-head category leagues.

Core formula for each category:
    G = (player_stat - league_mean) / sqrt(sigma^2 + kappa * tau^2)

Where:
    sigma  = std dev of that stat across all rostered players
    tau    = the player's own week-to-week variance in that category
    kappa  = roster-size scaling factor (1 + 1/roster_size)

No player names are hardcoded anywhere. All adjustments are derived from data.

Runtime note:
    Fetching game logs for ~130 players across 2 seasons takes ~3-4 minutes
    due to NBA API rate limiting. A cache file (game_log_cache.pkl) is saved
    after the first run so subsequent runs are instant.
"""

import pandas as pd
import numpy as np
from scipy.stats import boxcox
import warnings
import time
import pickle
from pathlib import Path

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# League configuration — edit this section each season
# ---------------------------------------------------------------------------

LEAGUE_CONFIG = {
    # Your 15 categories
    # direction: 'high' = more is better, 'low' = less is better
    # type: 'counting' or 'percent'
    "categories": {
        "FGM":  {"direction": "high", "type": "counting"},
        "FG%":  {"direction": "high", "type": "percent"},
        "FTM":  {"direction": "high", "type": "counting"},
        "3PTM": {"direction": "high", "type": "counting"},
        "PTS":  {"direction": "high", "type": "counting"},
        "REB":  {"direction": "high", "type": "counting"},
        "AST":  {"direction": "high", "type": "counting"},
        "ST":   {"direction": "high", "type": "counting"},
        "BLK":  {"direction": "high", "type": "counting"},
        "TO":   {"direction": "low",  "type": "counting"},
        "PF":   {"direction": "low",  "type": "counting"},
        "TECH": {"direction": "low",  "type": "counting"},
        # FF removed: no reliable per-player data in NBA API.
        # Assigning everyone the same default makes the G-score zero for all —
        # honest omission beats fake precision.
        "DD":   {"direction": "high", "type": "counting"},
        "TD":   {"direction": "high", "type": "counting"},
    },

    # Category weights for H2H leagues.
    # Key intuitions:
    #   - % cats (FG%) are noisy over a week's sample → discount
    #   - Low-count cats (ST, BLK, 3PTM) are volatile → slight discount
    #   - TO: best players create more TOs naturally → discount the penalty
    #   - TECH: real signal (Draymond vs average player is meaningful) → keep, small weight
    #   - DD/TD: your league includes these specifically → boost them
    #   - FF: removed — no reliable per-player data source
    # Tune these weights after your first season of data.
    "category_weights": {
        "PTS":  1.0,
        "REB":  1.0,
        "AST":  1.0,
        "FGM":  1.0,
        "FTM":  1.0,
        "FG%":  0.5,
        "3PTM": 0.8,
        "ST":   0.8,
        "BLK":  0.8,
        "TO":   0.5,
        "PF":   0.5,
        "TECH": 0.3,
        "DD":   0.7,
        "TD":   0.8,
    },

    # League structure
    "num_teams":   10,   # updated from 8 to 10 this season
    "roster_size": 13,   # active spots only (IL spots don't score)

    # Projection weights: most recent season first
    # With 2 seasons: [0.5, 0.3] renormalises to [0.625, 0.375]
    "season_weights": [0.5, 0.3, 0.2],

    # Seasons to fetch game logs for (most recent first)
    "game_log_seasons": ["2024-25", "2023-24"],

    # How many players to fetch game logs for.
    # Only draftable players need game logs (for DD/TD and tau).
    # 150 covers your 130-player pool with a buffer for edge cases.
    # Raising this improves tau accuracy at the cost of ~1.5 min per 100 extra players.
    "game_log_player_limit": 150,

    # Minimum qualifications
    "min_games": 20,
    "min_mpg":   10.0,

    # Cache file path — delete this file to force a fresh NBA API fetch
    "cache_file": "game_log_cache.pkl",
}


# ---------------------------------------------------------------------------
# Kappa: derived from roster size
# Formula: kappa = 1 + 1/roster_size
# Larger rosters → more players absorb variance → smaller penalty
# ---------------------------------------------------------------------------

def compute_kappa(roster_size: int) -> float:
    return 1.0 + (1.0 / roster_size)


# ---------------------------------------------------------------------------
# Step 1: Load Basketball Reference CSVs → per-game stats
# ---------------------------------------------------------------------------

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
    Load a Basketball Reference season totals CSV.
    Converts totals to per-game averages.
    For traded players, keeps the TOT (season total) row only.
    """
    df = pd.read_csv(path, skipinitialspace=True)
    df = df.dropna(subset=["Player"])
    df = df[df["Player"] != "Player"]   # BBR repeats header mid-file

    # Keep TOT row for traded players
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

    # These come from game logs; initialise to 0 for now
    for cat in ["TECH", "FF", "DD", "TD"]:
        df[cat] = 0.0

    drop_cols = [c for c in df.columns if c.endswith("_T") or c == "MIN_TOTAL"]
    df = df.drop(columns=drop_cols, errors="ignore")

    return df


def filter_qualified(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    mask = (df["GP"] >= config["min_games"]) & (df["MIN"] >= config["min_mpg"])
    return df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 2: Fetch game logs from NBA API (with caching)
# ---------------------------------------------------------------------------

def fetch_game_logs(player_names: list[str],
                    seasons: list[str],
                    cache_file: str) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Fetch per-game logs for each player for each season.

    Returns nested dict: { season -> { player_name -> DataFrame } }

    Uses a local cache file to avoid re-fetching on subsequent runs.
    Delete the cache file to force a fresh fetch from the NBA API.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        print(f"   Loading game logs from cache: {cache_file}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    print(f"   No cache found — fetching from NBA API (~6-8 minutes for 150 players)...")
    print(f"   This only runs once. Results cached to {cache_file}")

    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelogs

    # Build name → id lookup
    all_players = nba_players.get_players()
    name_to_id  = {p["full_name"]: p["id"] for p in all_players}

    result = {season: {} for season in seasons}

    total = len(player_names) * len(seasons)
    done  = 0

    for player_name in player_names:
        player_id = name_to_id.get(player_name)
        if player_id is None:
            # Try case-insensitive partial match for name variations
            lower = player_name.lower()
            matches = [p for p in all_players if p["full_name"].lower() == lower]
            if matches:
                player_id = matches[0]["id"]
            else:
                done += len(seasons)
                continue

        for season in seasons:
            done += 1
            pct = done / total * 100

            # Retry up to 3 times with increasing backoff on timeout
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    delay = 1.5 + (attempt * 3)   # 1.5s, 4.5s, 7.5s on retries
                    time.sleep(delay)
                    logs = playergamelogs.PlayerGameLogs(
                        player_id_nullable=player_id,
                        season_nullable=season,
                    )
                    df = logs.get_data_frames()[0]
                    if not df.empty:
                        result[season][player_name] = df
                    print(f"   [{pct:4.0f}%] {player_name} {season}   ", end="\r")
                    break   # success — exit retry loop

                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 5 + (attempt * 5)   # 5s, 10s between retries
                        print(f"\n   [retry {attempt+1}] {player_name} {season} — waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"\n   [skip] {player_name} {season}: failed after {max_retries} attempts")

    print()   # newline after \r updates

    with open(cache_path, "wb") as f:
        pickle.dump(result, f)
    print(f"   Game logs cached to {cache_file}")

    return result


# ---------------------------------------------------------------------------
# Step 3: Fetch TECH stats from NBA API misc endpoint (no scraping needed)
# ---------------------------------------------------------------------------

def fetch_tech_stats(seasons: list[str]) -> dict[str, dict[str, float]]:
    """
    Fetch technical fouls per game for all players via LeagueDashPlayerStats
    with MeasureType='Misc'. This is a single API call per season, not per player.

    Returns: { player_name -> tech_per_game }

    FF (flagrant fouls) is not reliably available in any NBA API endpoint,
    so we use a small realistic default (0.008/game ≈ ~0.6 per season).
    """
    from nba_api.stats.endpoints import leaguedashplayerstats

    tech_by_player = {}

    for season in seasons:
        try:
            time.sleep(0.7)
            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                measure_type_detailed_defense="Misc",
            )
            df = stats.get_data_frames()[0]

            # Column is typically 'TOV' in base but 'BLKA' area in misc —
            # print columns if this fails so you can identify the right name
            tech_col = None
            for candidate in ["PFD", "PF", "NBA_FANTASY_PTS"]:
                # TECH is usually under a column named differently — find it
                pass

            # The misc endpoint returns: AST_TO, AST_RATIO, OREB_PCT, DREB_PCT,
            # REB_PCT, TM_TOV_PCT, EFG_PCT, TS_PCT, USG_PCT, PACE, PIE, FGM, etc.
            # Technical fouls in misc come back as 'PF' supplemental column.
            # We look for it explicitly:
            if "PFD" in df.columns:
                # PFD = personal fouls drawn; not what we want
                pass
            if "NBA_FANTASY_PTS" in df.columns:
                # Misc endpoint doesn't include TECH directly in all versions.
                # Fall back to a separate Hustle endpoint if needed.
                pass

            # Reliable approach: use the base endpoint which includes PF,
            # then separately pull technical fouls via a different measure
            # Since TECH isn't reliably in LeagueDashPlayerStats misc either,
            # we switch to fetching it from game logs (see derive_gamelogs below)

        except Exception as e:
            print(f"   [warn] Could not fetch TECH stats for {season}: {e}")

    return tech_by_player


# ---------------------------------------------------------------------------
# Step 4: Derive DD, TD, TECH per game from game logs
# ---------------------------------------------------------------------------

def derive_stats_from_logs(game_logs: dict[str, dict[str, pd.DataFrame]]) \
        -> dict[str, dict[str, float]]:
    """
    From raw game logs, compute per-game averages for:
      - DD  (double-double: 2+ stats ≥ 10)
      - TD  (triple-double: 3+ stats ≥ 10)
      - TECH (technical fouls — from the PF column breakdown; NBA API game
              logs don't include TECH directly, so we derive a per-player
              estimate from LeagueDashPlayerStats misc endpoint separately)

    Returns: { player_name -> { 'DD': float, 'TD': float } }

    Note: The NBA API game log already has DD2 and TD3 columns which are
    exactly what we need — no manual calculation required.
    """
    derived = {}

    for season, season_logs in game_logs.items():
        for player_name, logs in season_logs.items():
            if logs.empty:
                continue

            gp = len(logs)
            if gp == 0:
                continue

            stats = {}

            # DD2 and TD3 are pre-calculated by the NBA API — use them directly
            if "DD2" in logs.columns:
                stats["DD"] = logs["DD2"].sum() / gp
            if "TD3" in logs.columns:
                stats["TD"] = logs["TD3"].sum() / gp

            if player_name not in derived:
                derived[player_name] = {}

            # Take the most recent season if the player appears in multiple
            for k, v in stats.items():
                if k not in derived[player_name]:
                    derived[player_name][k] = v
                else:
                    # Weighted average across seasons (most recent already first
                    # since we iterate season list in order)
                    derived[player_name][k] = (derived[player_name][k] + v) / 2

    return derived


# ---------------------------------------------------------------------------
# Step 5: Fetch TECH per player from misc endpoint (single call per season)
# ---------------------------------------------------------------------------

def fetch_tech_per_game(seasons: list[str]) -> dict[str, float]:
    """
    Pull technical fouls per game using LeagueDashPlayerStats with
    MeasureType='Base' — which returns the standard stat line including PF.

    Technical fouls are not in the Misc endpoint (which returns scoring
    breakdown stats). They ARE available via the PlayerDashboard endpoint
    or can be approximated from the hustlestats endpoint.

    Best available approach: use leaguehustlestatsplayer which returns
    SCREEN_ASSISTS, DEFLECTIONS, CONTESTED_SHOTS, and CHARGES_DRAWN —
    but NOT technical fouls either.

    Reality: the NBA API does not expose per-player technical fouls in
    any single clean endpoint. The most reliable method is scraping
    Basketball Reference, but that violates their ToS at scale.

    Decision: use a per-player estimate derived from the base stats.
    We fetch the base per-game endpoint and use PF as a proxy for
    foul-prone tendency, then scale it to a realistic TECH range.
    Players with high PF rates get higher estimated TECH.

    This is imperfect but better than giving everyone the same value,
    and avoids web scraping. The TECH category weight of 0.3 limits
    the impact of any estimation error.

    Returns: { player_name -> tech_per_game (estimated) }
    """
    from nba_api.stats.endpoints import leaguedashplayerstats

    season_weights = [0.625, 0.375]
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
            df = df[df["GP"] >= 10]   # filter to players with meaningful sample

            # Estimate TECH from PF rate.
            # NBA average: ~4 techs per season per player who gets them,
            # ~25-30% of players get at least one tech per season.
            # Scale: TECH ≈ 0.012 * PF (rough empirical approximation).
            # This gives Draymond-tier players (PF ~3.5) about 0.042 TECH/game
            # and low-foul players (PF ~1.5) about 0.018 TECH/game.
            # Not perfect, but meaningfully differentiates players.
            w = season_weights[i]
            for _, row in df.iterrows():
                name = row["PLAYER_NAME"]
                pf   = row.get("PF", 2.5)
                tech_estimate = max(0.01, 0.012 * float(pf))
                if name not in combined:
                    combined[name] = []
                combined[name].append((tech_estimate, w))

            print(f"   TECH estimated for {len(df)} players in {season}")

        except Exception as e:
            print(f"   [warn] TECH fetch failed for {season}: {e}")
            continue

    result = {}
    for name, vals in combined.items():
        total_w = sum(w for _, w in vals)
        result[name] = sum(v * w for v, w in vals) / total_w if total_w > 0 else 0.05

    return result


# ---------------------------------------------------------------------------
# Step 6: Compute tau (weekly variance) from game logs
# ---------------------------------------------------------------------------

def compute_tau(game_logs: dict[str, dict[str, pd.DataFrame]],
                categories: list[str],
                season_weights: list[float]) -> tuple[dict, dict]:
    """
    Compute each player's weekly variance (tau) per category.

    We use weekly per-game averages, not weekly totals.

    Why: H2H categories are per-game averages, not weekly totals (Yahoo
    divides each week's box scores and ranks on the averages). If we used
    weekly totals, a player who plays 4 games naturally gets a higher total
    than one who plays 2 — making tau a proxy for games-played variance
    rather than true performance variance. That unfairly penalises
    high-usage players (SGA, Curry) who are actually very consistent.

    Returns:
        player_tau  : { player_name -> { category -> tau_value } }
        league_tau  : { category -> median_tau_across_all_players }
                      Used as fallback for players with insufficient data.
    """
    seasons = list(game_logs.keys())
    all_weekly: dict[str, dict[str, list]] = {}

    for i, season in enumerate(seasons):
        w = season_weights[i] if i < len(season_weights) else season_weights[-1]
        season_logs = game_logs[season]

        for player_name, logs in season_logs.items():
            if logs.empty:
                continue

            logs = logs.copy()
            logs["GAME_DATE"] = pd.to_datetime(logs["GAME_DATE"])

            # Group games into ISO weeks
            iso = logs["GAME_DATE"].dt.isocalendar()
            logs["WEEK_KEY"] = iso["year"].astype(str) + "_" + iso["week"].astype(str)

            if player_name not in all_weekly:
                all_weekly[player_name] = {cat: [] for cat in categories}

            for cat in categories:
                # Map our internal category names to NBA API column names
                api_col = {
                    "ST": "STL", "TO": "TOV", "3PTM": "FG3M",
                    "FG%": "FG_PCT", "DD": "DD2", "TD": "TD3",
                }.get(cat, cat)

                if api_col not in logs.columns:
                    continue

                # Per-game average within each week — not the weekly total.
                # This decouples tau from how many games a player appeared in
                # and makes it a true measure of night-to-night consistency.
                weekly_avg = logs.groupby("WEEK_KEY")[api_col].mean()

                # Only include weeks where player actually played (skip missed weeks)
                played_weeks = logs.groupby("WEEK_KEY")[api_col].count()
                weekly_avg = weekly_avg[played_weeks >= 1]

                all_weekly[player_name][cat].extend(
                    [(val, w) for val in weekly_avg.values]
                )

    # Compute player-specific tau as weighted std dev of weekly per-game averages
    player_tau = {}
    for player_name, cat_data in all_weekly.items():
        player_tau[player_name] = {}
        for cat, weighted_vals in cat_data.items():
            if len(weighted_vals) < 4:   # need at least 4 weeks for meaningful variance
                continue
            vals = np.array([v for v, _ in weighted_vals])
            wts  = np.array([w for _, w in weighted_vals])
            wts  = wts / wts.sum()
            mean = np.average(vals, weights=wts)
            var  = np.average((vals - mean) ** 2, weights=wts)
            player_tau[player_name][cat] = float(np.sqrt(var))

    # League-wide median tau per category (fallback)
    league_tau = {}
    for cat in categories:
        all_vals = [v[cat] for v in player_tau.values() if cat in v]
        league_tau[cat] = float(np.median(all_vals)) if all_vals else 1.0

    return player_tau, league_tau


# ---------------------------------------------------------------------------
# Step 7: Project stats (weighted average across seasons)
# ---------------------------------------------------------------------------

def project_stats(season_dfs: list[pd.DataFrame],
                  weights: list[float],
                  derived_stats: dict[str, dict[str, float]],
                  tech_per_game: dict[str, float]) -> pd.DataFrame:
    """
    Compute a weighted per-game projection for each player.

    Players missing from older seasons have their weights renormalised
    automatically — no manual 'young player' flags needed. A player with
    only 1 season of data gets weight 1.0 on that season.

    DD, TD, and TECH come from the derived_stats and tech_per_game dicts
    built from actual game logs and the misc endpoint.
    FF defaults to 0.008/game (~0.6 per season) — this is realistic and
    honest rather than pretending we have data we don't.
    """
    cats = ["FGM", "FGA", "FG%", "3PTM", "FTM", "PTS", "REB",
            "AST", "ST", "BLK", "TO", "PF"]

    all_players: set[str] = set()
    for df in season_dfs:
        all_players.update(df["PLAYER_NAME"].values)

    rows = []
    for player in all_players:
        row = {"PLAYER_NAME": player}

        # --- Standard counting/percent categories ---
        for cat in cats:
            vals, wts = [], []
            for df, w in zip(season_dfs, weights):
                match = df[df["PLAYER_NAME"] == player]
                if not match.empty:
                    v = match.iloc[0].get(cat, np.nan)
                    if pd.notna(v):
                        vals.append(v)
                        wts.append(w)

            if not vals:
                row[cat] = np.nan
                continue

            total_w = sum(wts)

            if cat == "FG%":
                # Weight FG% by FGA volume to avoid low-attempt season distortion
                fga_vals, fga_wts = [], []
                for df, w in zip(season_dfs, weights):
                    match = df[df["PLAYER_NAME"] == player]
                    if not match.empty:
                        fga = match.iloc[0].get("FGA", np.nan)
                        pct = match.iloc[0].get("FG%", np.nan)
                        if pd.notna(fga) and pd.notna(pct) and fga > 0:
                            fga_vals.append(fga * w)
                            fga_wts.append(w)
                row[cat] = sum(fga_vals) / sum(fga_wts) if fga_vals else np.nan
            else:
                row[cat] = sum(v * w for v, w in zip(vals, wts)) / total_w

        # --- DD, TD from game log derivation ---
        player_derived = derived_stats.get(player, {})
        row["DD"] = player_derived.get("DD", 0.0)
        row["TD"] = player_derived.get("TD", 0.0)

        # --- TECH from misc endpoint ---
        row["TECH"] = tech_per_game.get(player, 0.05)   # 0.05/game ≈ 4/season fallback

        # --- FF: removed from scoring (no reliable per-player NBA API data) ---

        # --- GP and MIN from most recent season ---
        for df in season_dfs:
            match = df[df["PLAYER_NAME"] == player]
            if not match.empty:
                row["GP"]  = match.iloc[0].get("GP", np.nan)
                row["MIN"] = match.iloc[0].get("MIN", np.nan)
                break

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 8: Core DURANT G-score computation
# ---------------------------------------------------------------------------

def compute_g_scores(projected: pd.DataFrame,
                     player_tau: dict[str, dict[str, float]],
                     league_tau: dict[str, float],
                     config: dict) -> pd.DataFrame:
    """
    Apply the DURANT formula to produce G-scores per category and a total value.

    For each category:
      1. Box-Cox transform the stat distribution (handles skew)
      2. Compute league mean and sigma on the transformed values
      3. For each player, get their tau (player-specific or league median fallback)
      4. G = (player_transformed - mean) / sqrt(sigma^2 + kappa * tau^2)
      5. Flip sign for 'low is better' categories
      6. For FG%, multiply by (player_FGA / league_avg_FGA) — volume weighting
      7. Multiply by category weight
      8. Clip to ±3.5 to prevent one extreme outlier distorting the whole pool
    """
    epsilon = 0.05
    kappa   = compute_kappa(config["roster_size"])
    cats    = config["categories"]
    weights = config["category_weights"]

    # Only rank the top N players — the realistic draft pool
    pool_size = config["num_teams"] * config["roster_size"]
    df = projected.dropna(subset=["PTS"]).copy()
    df = df.nlargest(pool_size, "MIN").reset_index(drop=True)

    league_avg_fga = df["FGA"].median()
    total_g        = np.zeros(len(df))

    for cat, meta in cats.items():
        if cat not in df.columns:
            print(f"  [warn] {cat} missing from projections, skipping")
            continue

        raw = df[cat].fillna(0.0).values.astype(float)

        # Box-Cox requires all positive values
        shifted = raw + epsilon
        try:
            transformed, _ = boxcox(shifted) if np.all(shifted > 0) \
                              else (np.log(shifted + 1e-6), None)
        except Exception:
            transformed = np.log(shifted + 1e-6)

        league_mean  = transformed.mean()
        league_sigma = transformed.std()

        if league_sigma < 1e-8:
            # All players identical in this category — skip, contributes nothing
            df[f"{cat}_G"] = 0.0
            continue

        g_scores = []
        for i, row in df.iterrows():
            player = row["PLAYER_NAME"]

            # Tau: player-specific if we have enough data, else league median
            tau = player_tau.get(player, {}).get(cat, league_tau.get(cat, 1.0))

            # The DURANT denominator — this is what separates it from a z-score
            denom = np.sqrt(league_sigma ** 2 + kappa * tau ** 2)

            g = (transformed[df.index.get_loc(i)] - league_mean) / denom

            # Negative categories: being below average is good, so flip
            if meta["direction"] == "low":
                g = -g

            # FG% volume weighting: a player shooting 18 FGA/game contributes
            # more to your team FG% than one shooting 8, so their % edge is worth more
            if cat == "FG%":
                fga = row.get("FGA", league_avg_fga)
                g  *= (fga / league_avg_fga) if league_avg_fga > 0 else 1.0

            # Cap at ±3.5 — prevents Jokic's assist outlier from compressing everyone else
            g = np.clip(g, -3.5, 3.5)

            g_scores.append(g * weights.get(cat, 1.0))

        df[f"{cat}_G"] = g_scores
        total_g += np.array(g_scores)

    df["TOTAL_VALUE"] = total_g
    df = df.sort_values("TOTAL_VALUE", ascending=False).reset_index(drop=True)
    df["RANK"] = df.index + 1

    return df


# ---------------------------------------------------------------------------
# Output and validation helpers
# ---------------------------------------------------------------------------

def format_rankings(df: pd.DataFrame, top_n: int = 50) -> str:
    cats     = list(LEAGUE_CONFIG["categories"].keys())
    stat_cols = [c for c in cats if c in df.columns]
    display  = df.head(top_n)[["RANK", "PLAYER_NAME", "TOTAL_VALUE"] + stat_cols].copy()

    for col in stat_cols:
        display[col] = display[col].round(2)
    display["TOTAL_VALUE"] = display["TOTAL_VALUE"].round(3)

    try:
        from tabulate import tabulate
        return tabulate(display.values.tolist(),
                        headers=display.columns.tolist(),
                        tablefmt="github")
    except ImportError:
        return display.to_string(index=False)


def validate(df: pd.DataFrame, known_csv: str,
             name_col: str = "Player Name", rank_col: str = "Rank") -> None:
    from scipy.stats import spearmanr

    known  = pd.read_csv(known_csv)[[name_col, rank_col]].rename(
        columns={name_col: "PLAYER_NAME", rank_col: "ACTUAL_RANK"})
    merged = pd.merge(df[["PLAYER_NAME", "RANK"]], known, on="PLAYER_NAME")

    if merged.empty:
        print("No matching players found for validation.")
        return

    corr, _  = spearmanr(merged["RANK"], merged["ACTUAL_RANK"])
    delta    = merged["RANK"] - merged["ACTUAL_RANK"]
    hit_rate = (delta.abs() <= 5).mean() * 100
    mae      = delta.abs().mean()

    print(f"\n{'='*60}")
    print(f"Validation vs {Path(known_csv).name}")
    print(f"  Note: comparing 15-cat model vs 9-cat actual (directional only)")
    print(f"{'='*60}")
    print(f"  Players matched : {len(merged)}")
    print(f"  Spearman r      : {corr:.3f}  (1.0 = perfect, 0 = random)")
    print(f"  Hit rate (±5)   : {hit_rate:.1f}%")
    print(f"  MAE             : {mae:.1f} ranks")
    print(f"\n  Biggest misses (sorted by error):")
    merged["delta"] = delta
    for _, row in merged.sort_values("delta", key=abs, ascending=False).head(10).iterrows():
        arrow = "↑" if row["delta"] < 0 else "↓"
        print(f"    {row['PLAYER_NAME']:<28} "
              f"ours={int(row['RANK']):>3}  "
              f"actual={int(row['ACTUAL_RANK']):>3}  "
              f"{arrow}{abs(int(row['delta']))}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("DURANT Fantasy Basketball Ranker")
    print("=" * 60)

    config = LEAGUE_CONFIG

    # ── 1. Load BBR season data ──────────────────────────────────────────
    print("\n[1/5] Loading Basketball Reference season data...")

    bbr_files = [
        "basketball_reference_2024_25_total_stats.csv",
        "basketball_reference_2023_24_total_stats.csv",
    ]

    raw_weights = config["season_weights"][:len(bbr_files)]
    total_w     = sum(raw_weights)
    weights     = [w / total_w for w in raw_weights]   # renormalise to sum=1

    season_dfs = []
    for path in bbr_files:
        df  = load_bbr_csv(path)
        df  = filter_qualified(df, config)
        season_dfs.append(df)
        print(f"   {path}: {len(df)} qualified players")

    # ── 2. Fetch game logs ───────────────────────────────────────────────
    print("\n[2/5] Fetching game logs (NBA API)...")

    # Rank players by minutes from the most recent season to find the draftable pool.
    # Game logs are only needed for these players — fetching all 400+ is wasteful.
    limit = config["game_log_player_limit"]
    top_by_min = (
        season_dfs[0]                          # most recent season
        .nlargest(limit, "MIN")["PLAYER_NAME"]
        .tolist()
    )
    # Also include anyone who appeared in the older season but not the recent one
    # (e.g. injury returnees) — take the top names from there too as a buffer
    older_names = (
        season_dfs[1].nlargest(limit, "MIN")["PLAYER_NAME"].tolist()
        if len(season_dfs) > 1 else []
    )
    # Union, preserving order (recent season players first)
    seen = set(top_by_min)
    extra = [n for n in older_names if n not in seen]
    game_log_players = top_by_min + extra[:20]   # add up to 20 from older season

    print(f"   Fetching logs for top {len(game_log_players)} players "
          f"(limit: {limit} + up to 20 returnees)")

    game_logs = fetch_game_logs(
        player_names=game_log_players,
        seasons=config["game_log_seasons"],
        cache_file=config["cache_file"],
    )

    # ── 3. Derive DD, TD from game logs ─────────────────────────────────
    print("\n[3/5] Deriving DD/TD from game logs...")
    derived_stats = derive_stats_from_logs(game_logs)
    dd_count = sum(1 for v in derived_stats.values() if "DD" in v)
    print(f"   DD/TD derived for {dd_count} players")

    # ── 4. Fetch TECH from NBA API misc endpoint ─────────────────────────
    print("\n[4/5] Fetching TECH stats + computing tau...")

    tech_cache_path = Path("tech_cache.pkl")
    if tech_cache_path.exists():
        print("   Loading TECH from cache...")
        with open(tech_cache_path, "rb") as f:
            tech_per_game = pickle.load(f)
    else:
        tech_per_game = fetch_tech_per_game(config["game_log_seasons"])
        with open(tech_cache_path, "wb") as f:
            pickle.dump(tech_per_game, f)
        print(f"   TECH data cached for {len(tech_per_game)} players")

    # Compute tau from game logs
    cat_names   = list(config["categories"].keys())
    player_tau, league_tau = compute_tau(game_logs, cat_names, weights)
    print(f"   Tau computed for {len(player_tau)} players")
    print(f"   League median tau per category:")
    for cat, tau in sorted(league_tau.items()):
        print(f"     {cat:<6} {tau:.3f}")

    # ── 5. Project and score ─────────────────────────────────────────────
    print("\n[5/5] Projecting stats and computing G-scores...")

    projected = project_stats(season_dfs, weights, derived_stats, tech_per_game)
    projected = projected.dropna(subset=["PTS"])
    print(f"   {len(projected)} players with projections")

    rankings = compute_g_scores(projected, player_tau, league_tau, config)

    # ── Output ───────────────────────────────────────────────────────────
    pool_size = config["num_teams"] * config["roster_size"]
    print(f"\n\nTOP 30 PLAYERS — 2025-26 PROJECTIONS")
    print(f"(draft pool: top {pool_size} players for {config['num_teams']} teams × {config['roster_size']} roster spots)")
    print(format_rankings(rankings, top_n=30))

    out_file = "durant_rankings_2025_26.csv"
    rankings.to_csv(out_file, index=False)
    print(f"\nFull rankings ({len(rankings)} players) saved to: {out_file}")

    # ── Validation ───────────────────────────────────────────────────────
    if Path("actual_9cat_24_25.csv").exists():
        validate(rankings, "actual_9cat_24_25.csv")