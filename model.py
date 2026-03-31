"""
model.py — Projection and DURANT G-score formula
==================================================
Contains the core statistical engine:
  - compute_kappa: roster-size scaling factor
  - project_stats: weighted per-game projections across seasons
  - compute_tau: weekly variance per player per category
  - compute_g_scores: the DURANT formula itself

The DURANT formula for each category:
    G = (player_stat - league_mean) / sqrt(sigma^2 + kappa * tau^2)

Where:
    sigma = std dev across the rostered player pool (how spread out the league is)
    tau   = player's own week-to-week variance (their consistency)
    kappa = roster-size scaling factor (1 + 1/roster_size)

Key modelling decisions:
    - Projections are GP-adjusted so injury-prone players are discounted
      automatically — no player names hardcoded anywhere.
    - Season weights are trend-adjusted per player: breakout players get
      more recent-season weight, declining players get less.
    - Tau uses weekly per-game averages to measure true consistency,
      not games-played-driven variance.
"""

import pandas as pd
import numpy as np
from scipy.stats import boxcox


# ── Kappa ─────────────────────────────────────────────────────────────────────

def compute_kappa(roster_size: int) -> float:
    """
    Roster-size scaling factor for the variance penalty.
    Larger rosters → more players absorb variance → smaller kappa.
    Formula: kappa = 1 + 1/roster_size
    """
    return 1.0 + (1.0 / roster_size)


# ── Trend detection ───────────────────────────────────────────────────────────

def compute_trend_weights(player_season_stats: dict[str, pd.Series],
                           available_seasons: list[str],
                           base_weights: list[float],
                           trend_threshold: float = 0.15,
                           trend_boost: float = 0.15) -> list[float]:
    """
    Adjust season weights based on a player's performance trajectory.

    Logic:
      - Compute a baseline projection using the base weights as-is.
      - Compare the most recent season's PTS to that baseline.
      - If improved by >trend_threshold (default 15%): boost recent weight.
        Catches breakout players like Jalen Johnson, Payton Pritchard.
      - If declined by >trend_threshold: reduce recent weight.
        Trusts multi-year average more for declining vets.
      - Stable players use base weights unchanged.

    Returns renormalised weights that sum to 1.0.
    """
    if len(available_seasons) < 2:
        return base_weights   # already normalised, nothing to adjust

    # Baseline weighted PTS
    pts_vals, pts_wts = [], []
    for season, w in zip(available_seasons, base_weights):
        pts = player_season_stats[season].get("PTS", np.nan)
        if pd.notna(pts):
            pts_vals.append(pts)
            pts_wts.append(w)

    if not pts_vals:
        return base_weights

    total_w  = sum(pts_wts)
    baseline = sum(v * w for v, w in zip(pts_vals, pts_wts)) / total_w

    recent_pts = player_season_stats[available_seasons[0]].get("PTS", np.nan)
    if pd.isna(recent_pts) or baseline == 0:
        return base_weights

    pct_change = (recent_pts - baseline) / baseline

    adjusted = list(base_weights)
    if pct_change > trend_threshold:
        # Breakout — trust recent season more
        adjusted[0] = min(adjusted[0] + trend_boost, 0.80)
    elif pct_change < -trend_threshold:
        # Declining — trust multi-year average more
        adjusted[0] = max(adjusted[0] - trend_boost, 0.30)

    total = sum(adjusted)
    return [w / total for w in adjusted]


# ── GP adjustment ─────────────────────────────────────────────────────────────

def compute_gp_factor(player_season_stats: dict[str, pd.Series],
                       available_seasons: list[str],
                       weights: list[float],
                       full_season_games: int = 82) -> float:
    """
    Compute a games-played availability factor for a player.

    Converts per-game projections into draft-day expected value by accounting
    for how often a player historically suits up. Injury-prone players
    discount themselves through their own data — no names hardcoded.

    Examples with typical historical GPs:
      Kawhi Leonard  (~45 GP/season avg) → factor ~0.55
      Joel Embiid    (~55 GP/season avg) → factor ~0.67
      Nikola Jokić   (~73 GP/season avg) → factor ~0.89
      SGA            (~73 GP/season avg) → factor ~0.89

    Capped at [0.50, 1.0] — even the most injury-prone players
    get some credit, and no one can exceed a full season.
    """
    gp_vals, gp_wts = [], []
    for season, w in zip(available_seasons, weights):
        gp = player_season_stats[season].get("GP", np.nan)
        if pd.notna(gp) and gp > 0:
            gp_vals.append(gp)
            gp_wts.append(w)

    if not gp_vals:
        return 1.0

    total_w      = sum(gp_wts)
    weighted_gp  = sum(g * w for g, w in zip(gp_vals, gp_wts)) / total_w
    availability = weighted_gp / full_season_games

    return float(np.clip(availability, 0.50, 1.0))


# ── Percentage helpers ────────────────────────────────────────────────────────

def compute_weighted_fg_pct(player_season_stats: dict[str, pd.Series],
                            available_seasons: list[str],
                            weights: list[float]) -> float:
    """
    Compute a multi-season FG% projection weighted by shot volume.

    This preserves percentage semantics by blending made shots and attempts,
    rather than averaging raw percentages or accidentally returning attempts.
    """
    weighted_fgm = 0.0
    weighted_fga = 0.0

    for season, w in zip(available_seasons, weights):
        fga = player_season_stats[season].get("FGA", np.nan)
        pct = player_season_stats[season].get("FG%", np.nan)
        if pd.notna(fga) and pd.notna(pct) and fga > 0:
            weighted_fga += fga * w
            weighted_fgm += fga * pct * w

    if weighted_fga <= 0:
        return np.nan

    return weighted_fgm / weighted_fga


# ── Projection ────────────────────────────────────────────────────────────────

def project_stats(season_dfs: list[pd.DataFrame],
                  weights: list[float],
                  derived_stats: dict[str, dict[str, float]],
                  tech_per_game: dict[str, float],
                  seasons: list[str] | None = None) -> pd.DataFrame:
    """
    Compute GP-adjusted, trend-aware per-game projections for each player.

    Two improvements over a flat weighted average:

    1. Trend-aware weights: each player's season weights shift based on their
       trajectory. Breakout players get more recent-season weight; declining
       players get less. Detected from PTS change vs weighted baseline.

    2. GP adjustment: all counting stats multiplied by (weighted_GP / 82).
       Converts per-game value into expected season contribution, naturally
       discounting injury-prone players without any hardcoding.

    Percentage categories (FG%) are not GP-adjusted — they're ratios
    independent of games played.
    """
    if seasons is None:
        seasons = [f"season_{i}" for i in range(len(season_dfs))]

    counting_cats = ["FGM", "FGA", "3PTM", "FTM", "PTS", "REB",
                     "AST", "ST", "BLK", "TO", "PF"]

    # Build season lookup for fast access
    season_lookup: dict[str, dict[str, pd.Series]] = {}
    for season, df in zip(seasons, season_dfs):
        season_lookup[season] = {
            row["PLAYER_NAME"]: row
            for _, row in df.iterrows()
        }

    all_players: set[str] = set()
    for df in season_dfs:
        all_players.update(df["PLAYER_NAME"].values)

    rows = []
    for player in all_players:

        # Collect stats for seasons this player appeared in
        player_season_stats: dict[str, pd.Series] = {
            s: season_lookup[s][player]
            for s in seasons
            if player in season_lookup.get(s, {})
        }
        if not player_season_stats:
            continue

        available_seasons = [s for s in seasons if s in player_season_stats]
        raw_weights       = [weights[seasons.index(s)] for s in available_seasons]
        total_w           = sum(raw_weights)
        norm_weights      = [w / total_w for w in raw_weights]

        # Step 1: trend-aware weight adjustment
        final_weights = compute_trend_weights(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            base_weights=norm_weights,
        )

        # Step 2: GP availability factor
        gp_factor = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        row = {"PLAYER_NAME": player, "GP_FACTOR": round(gp_factor, 3)}

        # ── Counting categories — GP-adjusted ───────────────────────────
        for cat in counting_cats:
            vals, wts = [], []
            for season, w in zip(available_seasons, final_weights):
                v = player_season_stats[season].get(cat, np.nan)
                if pd.notna(v):
                    vals.append(v)
                    wts.append(w)

            if not vals:
                row[cat] = np.nan
                continue

            wt        = sum(wts)
            projected = sum(v * w for v, w in zip(vals, wts)) / wt
            row[cat]  = projected * gp_factor   # GP adjustment applied here

        # ── FG% — volume-weighted, no GP adjustment ──────────────────────
        row["FG%"] = compute_weighted_fg_pct(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        # ── DD and TD — GP-adjusted ──────────────────────────────────────
        player_derived = derived_stats.get(player, {})
        row["DD"] = player_derived.get("DD", 0.0) * gp_factor
        row["TD"] = player_derived.get("TD", 0.0) * gp_factor

        # ── TECH — GP-adjusted ───────────────────────────────────────────
        row["TECH"] = tech_per_game.get(player, 0.05) * gp_factor

        # ── GP and MIN — raw, for filtering and display ──────────────────
        first = available_seasons[0]
        row["GP"]  = player_season_stats[first].get("GP", np.nan)
        row["MIN"] = player_season_stats[first].get("MIN", np.nan)

        rows.append(row)

    return pd.DataFrame(rows)


# ── Tau (weekly variance) ─────────────────────────────────────────────────────

def compute_tau(game_logs: dict[str, dict[str, pd.DataFrame]],
                categories: list[str],
                season_weights: list[float]) -> tuple[dict, dict]:
    """
    Compute each player's weekly variance (tau) per category from game logs.

    Uses weekly per-game averages (not totals) to measure true consistency,
    decoupled from how many games happened to be scheduled that week.

    TECH is proxied from weekly PF rate using the same relationship as the
    projection layer (TECH ~= 0.012 x PF/game), so its variance is no longer
    an arbitrary fallback for every player.

    Returns:
        player_tau : { player_name -> { category -> tau } }
        league_tau : { category -> median tau across all players }
    """
    API_COL_MAP = {
        "ST":   "STL",
        "TO":   "TOV",
        "3PTM": "FG3M",
        "FG%":  "FG_PCT",
        "DD":   "DD2",
        "TD":   "TD3",
    }

    seasons    = list(game_logs.keys())
    all_weekly: dict[str, dict[str, list]] = {}

    for i, season in enumerate(seasons):
        w           = season_weights[i] if i < len(season_weights) else season_weights[-1]
        season_logs = game_logs[season]

        for player_name, logs in season_logs.items():
            if logs.empty:
                continue

            logs = logs.copy()
            logs["GAME_DATE"] = pd.to_datetime(logs["GAME_DATE"])
            iso = logs["GAME_DATE"].dt.isocalendar()
            logs["WEEK_KEY"] = iso["year"].astype(str) + "_" + iso["week"].astype(str)

            if player_name not in all_weekly:
                all_weekly[player_name] = {cat: [] for cat in categories}

            for cat in categories:
                if cat == "TECH":
                    if "PF" not in logs.columns:
                        continue
                    weekly_avg = logs.groupby("WEEK_KEY")["PF"].mean() * 0.012
                    weekly_avg = weekly_avg.clip(lower=0.01)
                    played_weeks = logs.groupby("WEEK_KEY")["PF"].count()
                else:
                    api_col = API_COL_MAP.get(cat, cat)
                    if api_col not in logs.columns:
                        continue
                    weekly_avg = logs.groupby("WEEK_KEY")[api_col].mean()
                    played_weeks = logs.groupby("WEEK_KEY")[api_col].count()

                weekly_avg   = weekly_avg[played_weeks >= 1]

                all_weekly[player_name][cat].extend(
                    [(val, w) for val in weekly_avg.values]
                )

    player_tau: dict[str, dict[str, float]] = {}
    for player_name, cat_data in all_weekly.items():
        player_tau[player_name] = {}
        for cat, weighted_vals in cat_data.items():
            if len(weighted_vals) < 4:
                continue
            vals = np.array([v for v, _ in weighted_vals])
            wts  = np.array([w for _, w in weighted_vals])
            wts  = wts / wts.sum()
            mean = np.average(vals, weights=wts)
            var  = np.average((vals - mean) ** 2, weights=wts)
            player_tau[player_name][cat] = float(np.sqrt(var))

    league_tau: dict[str, float] = {}
    for cat in categories:
        all_vals = [v[cat] for v in player_tau.values() if cat in v]
        league_tau[cat] = float(np.median(all_vals)) if all_vals else 1.0

    return player_tau, league_tau


# ── G-score formula ───────────────────────────────────────────────────────────

def compute_g_scores(projected: pd.DataFrame,
                     player_tau: dict[str, dict[str, float]],
                     league_tau: dict[str, float],
                     config: dict) -> pd.DataFrame:
    """
    Apply the DURANT formula to produce per-category G-scores and total value.

    Steps per category:
      1. Box-Cox transform (handles skew in counting stats)
      2. Compute league mean and sigma on transformed values
      3. Player tau lookup (player-specific → league median fallback)
      4. G = (player_transformed - mean) / sqrt(sigma^2 + kappa * tau^2)
      5. Flip sign for 'low is better' categories
      6. FG%: multiply by (player_FGA / league_avg_FGA) — volume weighting
      7. Clip to ±3.5 — prevents one outlier compressing everyone else
      8. Multiply by category weight
    """
    epsilon = 0.05
    kappa   = compute_kappa(config["roster_size"])
    cats    = config["categories"]
    weights = config["category_weights"]

    pool_size = config["num_teams"] * config["roster_size"]
    df = projected.dropna(subset=["PTS"]).copy()
    df = df.nlargest(pool_size, "MIN").reset_index(drop=True)

    league_avg_fga = df["FGA"].median()
    total_g        = np.zeros(len(df))

    for cat, meta in cats.items():
        if cat not in df.columns:
            print(f"  [warn] {cat} missing from projections, skipping")
            continue

        raw     = df[cat].fillna(0.0).values.astype(float)
        shifted = raw + epsilon

        try:
            transformed, _ = boxcox(shifted) if np.all(shifted > 0) \
                              else (np.log(shifted + 1e-6), None)
        except Exception:
            transformed = np.log(shifted + 1e-6)

        league_mean  = transformed.mean()
        league_sigma = transformed.std()

        if league_sigma < 1e-8:
            df[f"{cat}_G"] = 0.0
            continue

        g_scores = []
        for i, row in df.iterrows():
            player = row["PLAYER_NAME"]
            tau    = player_tau.get(player, {}).get(cat, league_tau.get(cat, 1.0))

            denom = np.sqrt(league_sigma ** 2 + kappa * tau ** 2)
            g     = (transformed[df.index.get_loc(i)] - league_mean) / denom

            if meta["direction"] == "low":
                g = -g

            if cat == "FG%":
                fga = row.get("FGA", league_avg_fga)
                g  *= (fga / league_avg_fga) if league_avg_fga > 0 else 1.0

            g = np.clip(g, -3.5, 3.5)
            g_scores.append(g * weights.get(cat, 1.0))

        df[f"{cat}_G"] = g_scores
        total_g += np.array(g_scores)

    df["TOTAL_VALUE"] = total_g
    df = df.sort_values("TOTAL_VALUE", ascending=False).reset_index(drop=True)
    df["RANK"] = df.index + 1

    return df
