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

This beats a plain z-score because tau penalises volatile players —
a player who scores 30 one week and 8 the next has the same average as
a consistent 19-point scorer, but the volatile one is less valuable in
weekly H2H because that 8-point week likely loses you the category.
"""

import pandas as pd
import numpy as np
from scipy.stats import boxcox


# ── Kappa ────────────────────────────────────────────────────────────────────

def compute_kappa(roster_size: int) -> float:
    """
    Roster-size scaling factor for the variance penalty.
    Larger rosters → more players absorb variance → smaller kappa → smaller penalty.
    Formula: kappa = 1 + 1/roster_size
    """
    return 1.0 + (1.0 / roster_size)


# ── Projection ───────────────────────────────────────────────────────────────

def project_stats(season_dfs: list[pd.DataFrame],
                  weights: list[float],
                  derived_stats: dict[str, dict[str, float]],
                  tech_per_game: dict[str, float]) -> pd.DataFrame:
    """
    Compute weighted per-game projections for each player across seasons.

    Players missing from older seasons have their weights renormalised
    automatically — no manual 'young player' flags needed. A rookie with
    only one season of data gets full weight on that one season.

    FG% is weighted by FGA volume to avoid distortion from low-attempt seasons.

    DD, TD, and TECH come from game logs and the foul stats fetch — not BBR.
    """
    cats = ["FGM", "FGA", "FG%", "3PTM", "FTM", "PTS", "REB",
            "AST", "ST", "BLK", "TO", "PF"]

    all_players: set[str] = set()
    for df in season_dfs:
        all_players.update(df["PLAYER_NAME"].values)

    rows = []
    for player in all_players:
        row = {"PLAYER_NAME": player}

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
                # Weight FG% by FGA so a low-attempt season doesn't distort
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

        # DD and TD from game logs (most recent season takes precedence)
        player_derived = derived_stats.get(player, {})
        row["DD"]   = player_derived.get("DD", 0.0)
        row["TD"]   = player_derived.get("TD", 0.0)

        # TECH estimated from foul rate (0.012 × PF as proxy)
        row["TECH"] = tech_per_game.get(player, 0.05)

        # GP and MIN from most recent season only
        for df in season_dfs:
            match = df[df["PLAYER_NAME"] == player]
            if not match.empty:
                row["GP"]  = match.iloc[0].get("GP", np.nan)
                row["MIN"] = match.iloc[0].get("MIN", np.nan)
                break

        rows.append(row)

    return pd.DataFrame(rows)


# ── Tau (weekly variance) ────────────────────────────────────────────────────

def compute_tau(game_logs: dict[str, dict[str, pd.DataFrame]],
                categories: list[str],
                season_weights: list[float]) -> tuple[dict, dict]:
    """
    Compute each player's weekly variance (tau) per category from game logs.

    Uses weekly per-game averages (not weekly totals). This is important:
    if we used totals, a player who plays 4 games in a week would naturally
    show higher totals than one who plays 2 — making tau a proxy for
    games-played variance rather than true performance variance. Averages
    correctly isolate night-to-night consistency.

    Returns:
        player_tau : { player_name -> { category -> tau } }
        league_tau : { category -> median tau across all players }
                     Used as fallback for players with insufficient data.
    """
    # NBA API column name → our internal category name mapping
    API_COL_MAP = {
        "ST":   "STL",
        "TO":   "TOV",
        "3PTM": "FG3M",
        "FG%":  "FG_PCT",
        "DD":   "DD2",
        "TD":   "TD3",
    }

    seasons     = list(game_logs.keys())
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
                api_col = API_COL_MAP.get(cat, cat)
                if api_col not in logs.columns:
                    continue

                # Per-game average within each week — decouples tau from
                # how many games happened to be scheduled that week
                weekly_avg   = logs.groupby("WEEK_KEY")[api_col].mean()
                played_weeks = logs.groupby("WEEK_KEY")[api_col].count()
                weekly_avg   = weekly_avg[played_weeks >= 1]

                all_weekly[player_name][cat].extend(
                    [(val, w) for val in weekly_avg.values]
                )

    # Compute player-specific tau as weighted standard deviation
    player_tau: dict[str, dict[str, float]] = {}
    for player_name, cat_data in all_weekly.items():
        player_tau[player_name] = {}
        for cat, weighted_vals in cat_data.items():
            if len(weighted_vals) < 4:   # need at least 4 weeks for reliable variance
                continue
            vals = np.array([v for v, _ in weighted_vals])
            wts  = np.array([w for _, w in weighted_vals])
            wts  = wts / wts.sum()
            mean = np.average(vals, weights=wts)
            var  = np.average((vals - mean) ** 2, weights=wts)
            player_tau[player_name][cat] = float(np.sqrt(var))

    # League-wide median tau as fallback for players with insufficient log data
    league_tau: dict[str, float] = {}
    for cat in categories:
        all_vals = [v[cat] for v in player_tau.values() if cat in v]
        league_tau[cat] = float(np.median(all_vals)) if all_vals else 1.0

    return player_tau, league_tau


# ── G-score formula ──────────────────────────────────────────────────────────

def compute_g_scores(projected: pd.DataFrame,
                     player_tau: dict[str, dict[str, float]],
                     league_tau: dict[str, float],
                     config: dict) -> pd.DataFrame:
    """
    Apply the DURANT formula to produce per-category G-scores and total value.

    For each category:
      1. Box-Cox transform the distribution (handles skew in counting stats)
      2. Compute league mean and sigma on transformed values
      3. Look up each player's tau (player-specific, or league median fallback)
      4. G = (player_transformed - mean) / sqrt(sigma^2 + kappa * tau^2)
      5. Flip sign for 'low is better' categories
      6. For FG%: multiply by (player_FGA / league_avg_FGA) — volume weighting
      7. Clip to ±3.5 to prevent extreme outliers compressing everyone else
      8. Multiply by category weight
    """
    epsilon = 0.05
    kappa   = compute_kappa(config["roster_size"])
    cats    = config["categories"]
    weights = config["category_weights"]

    # Restrict to the realistic draft pool
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
            # All players identical in this category — contributes nothing
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