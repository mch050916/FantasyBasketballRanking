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


TREND_SIGNAL_WEIGHTS = {
    "PTS": 0.24,
    "AST": 0.18,
    "REB": 0.14,
    "3PTM": 0.14,
    "ST": 0.10,
    "BLK": 0.08,
    "MIN": 0.12,
}

TREND_SIGNAL_SCALES = {
    "PTS": 10.0,
    "AST": 3.0,
    "REB": 4.0,
    "3PTM": 1.0,
    "ST": 0.6,
    "BLK": 0.5,
    "MIN": 24.0,
}

RECENT_WEIGHT_MIN = 0.30
RECENT_WEIGHT_MAX = 0.85
ROLE_BOOST_SATURATION = 0.18


# ── Kappa ─────────────────────────────────────────────────────────────────────

def compute_kappa(roster_size: int) -> float:
    """
    Roster-size scaling factor for the variance penalty.
    Larger rosters → more players absorb variance → smaller kappa.
    Formula: kappa = 1 + 1/roster_size
    """
    return 1.0 + (1.0 / roster_size)


# ── Trend detection ───────────────────────────────────────────────────────────

def _compute_weighted_stat_baseline(player_season_stats: dict[str, pd.Series],
                                    seasons: list[str],
                                    weights: list[float],
                                    stat: str) -> float:
    """Weighted baseline for one stat using older available seasons only."""
    vals, wts = [], []
    for season, weight in zip(seasons[1:], weights[1:]):
        value = player_season_stats[season].get(stat, np.nan)
        if pd.notna(value):
            vals.append(float(value))
            wts.append(float(weight))

    if not vals:
        return np.nan

    total_weight = sum(wts)
    if total_weight <= 0:
        return np.nan

    return sum(value * weight for value, weight in zip(vals, wts)) / total_weight


def _compute_relative_change(recent_value: float,
                             baseline_value: float,
                             scale_floor: float) -> float:
    """Clip relative change to avoid small-denominator noise dominating the score."""
    if pd.isna(recent_value) or pd.isna(baseline_value):
        return np.nan

    denom = max(abs(float(baseline_value)), float(scale_floor), 1e-6)
    return float(np.clip((float(recent_value) - float(baseline_value)) / denom, -1.0, 1.0))


def _rebalance_recent_weight(base_weights: list[float],
                             desired_recent_weight: float) -> list[float]:
    """Move weight toward or away from the recent season while preserving a 1.0 sum."""
    if not base_weights:
        return base_weights
    if len(base_weights) == 1:
        return [1.0]

    desired_recent_weight = float(np.clip(desired_recent_weight, RECENT_WEIGHT_MIN, RECENT_WEIGHT_MAX))
    remaining_weight = 1.0 - desired_recent_weight
    other_total = sum(base_weights[1:])

    if other_total <= 0:
        return [1.0] + [0.0] * (len(base_weights) - 1)

    scaled_others = [weight / other_total * remaining_weight for weight in base_weights[1:]]
    return [desired_recent_weight] + scaled_others


def compute_trend_profile(player_season_stats: dict[str, pd.Series],
                          available_seasons: list[str],
                          base_weights: list[float],
                          trend_boost: float = 0.14,
                          role_boost_cap: float = 0.12) -> dict[str, object]:
    """
    Build one explainable multicategory trend profile for a player.

    The composite score blends approved multicategory changes and feeds the
    existing season-weight adjustment path. Minutes growth also powers a small,
    separate role-change breakout boost when the player's broader trend is
    already positive.
    """
    neutral_profile = {
        "weights": base_weights,
        "composite_score": 0.0,
        "role_score": 0.0,
        "trend_shift": 0.0,
        "role_boost": 0.0,
        "signal_changes": {},
    }

    if len(available_seasons) < 2:
        return neutral_profile

    recent_stats = player_season_stats[available_seasons[0]]
    signal_changes: dict[str, float] = {}
    used_signal_weights: dict[str, float] = {}

    for stat, weight in TREND_SIGNAL_WEIGHTS.items():
        recent_value = recent_stats.get(stat, np.nan)
        baseline_value = _compute_weighted_stat_baseline(
            player_season_stats,
            available_seasons,
            base_weights,
            stat,
        )
        change = _compute_relative_change(
            recent_value=recent_value,
            baseline_value=baseline_value,
            scale_floor=TREND_SIGNAL_SCALES[stat],
        )
        if pd.isna(change):
            continue
        signal_changes[stat] = change
        used_signal_weights[stat] = weight

    if not used_signal_weights:
        return neutral_profile

    total_signal_weight = sum(used_signal_weights.values())
    composite_score = sum(
        signal_changes[stat] * used_signal_weights[stat]
        for stat in used_signal_weights
    ) / total_signal_weight
    composite_score = float(np.clip(composite_score, -0.5, 0.5))

    trend_shift = float(np.clip(composite_score / 0.22, -1.0, 1.0) * trend_boost)

    minutes_growth = max(0.0, signal_changes.get("MIN", 0.0))
    support_stats = [signal_changes.get(stat, 0.0) for stat in ("PTS", "AST", "REB", "3PTM")]
    positive_support = float(np.mean([max(0.0, value) for value in support_stats])) if support_stats else 0.0
    role_score = float(np.clip((0.65 * minutes_growth) + (0.35 * positive_support), 0.0, 0.5))

    role_boost = 0.0
    if minutes_growth >= 0.10 and composite_score > 0.03:
        # role_boost's nominal cap can combine with a maxed-out trend_shift to
        # push desired_recent_weight past RECENT_WEIGHT_MAX, which would then
        # get silently truncated by _rebalance_recent_weight's clamp below —
        # the truncation amount would depend on trend_shift, not on role_boost
        # itself, discarding an unpredictable chunk of the calibrated boost.
        # Instead, cap role_boost to whatever headroom is actually left under
        # RECENT_WEIGHT_MAX once base_weights[0] and trend_shift are applied,
        # so the sum never needs clamping through this path in the first
        # place. RECENT_WEIGHT_MAX itself is intentionally left untouched.
        available_headroom = max(0.0, RECENT_WEIGHT_MAX - base_weights[0] - trend_shift)
        effective_role_boost_cap = min(role_boost_cap, available_headroom)
        role_boost = float(
            np.clip(role_score / ROLE_BOOST_SATURATION, 0.0, 1.0) * effective_role_boost_cap
        )

    desired_recent_weight = base_weights[0] + trend_shift + role_boost
    adjusted_weights = _rebalance_recent_weight(base_weights, desired_recent_weight)

    return {
        "weights": adjusted_weights,
        "composite_score": composite_score,
        "role_score": role_score,
        "trend_shift": trend_shift,
        "role_boost": role_boost,
        "signal_changes": signal_changes,
    }


def compute_trend_weights(player_season_stats: dict[str, pd.Series],
                          available_seasons: list[str],
                          base_weights: list[float],
                          trend_boost: float = 0.14,
                          role_boost_cap: float = 0.12) -> list[float]:
    """
    Adjust season weights using one multicategory composite trend score.

    Returns normalized weights that still sum to 1.0, but the recent-season
    share can move faster for true multicategory growth and role expansion.
    """
    return compute_trend_profile(
        player_season_stats=player_season_stats,
        available_seasons=available_seasons,
        base_weights=base_weights,
        trend_boost=trend_boost,
        role_boost_cap=role_boost_cap,
    )["weights"]


def compute_decline_factor(age: float | None,
                           composite_score: float,
                           age_start: float = 31.0) -> float:
    """
    Compute a light veteran decline factor.

    Age alone does very little. The penalty becomes meaningfully stronger only
    when a veteran profile also carries a negative recent trend.
    """
    if age is None or pd.isna(age) or float(age) < age_start:
        return 1.0

    age_pressure = float(np.clip((float(age) - age_start) / 5.0, 0.0, 1.0))
    negative_alignment = float(np.clip((-float(composite_score) - 0.05) / 0.20, 0.0, 1.0))

    base_penalty = 0.02 * age_pressure
    aligned_penalty = 0.10 * age_pressure * negative_alignment
    total_penalty = min(0.12, base_penalty + aligned_penalty)

    return 1.0 - total_penalty


def calibrate_milestone_value(value: float,
                              stat: str,
                              config: dict) -> float:
    """
    Apply bounded milestone-stat compression for DD/TD.

    This keeps custom-league milestone categories meaningful while reducing the
    separation created by sparse event-rate spikes.
    """
    calibration = config.get("milestone_calibration", {}).get(stat)
    if calibration is None or pd.isna(value):
        return float(value)

    raw = max(float(value), 0.0)
    scale = float(calibration.get("scale", 1.0))
    curvature = max(float(calibration.get("curvature", 0.0)), 0.0)

    if raw == 0.0:
        return 0.0

    return scale * (raw / (1.0 + curvature * raw))


def calibrate_category_values(raw: np.ndarray,
                              cat: str,
                              config: dict) -> np.ndarray:
    """Apply category-specific calibration to a numpy array when configured."""
    if cat not in {"DD", "TD"}:
        return raw
    return np.array(
        [calibrate_milestone_value(value, cat, config) for value in raw],
        dtype=float,
    )


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
        trend_profile = compute_trend_profile(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            base_weights=norm_weights,
        )
        final_weights = trend_profile["weights"]

        # Step 2: GP availability factor
        gp_factor = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        first = available_seasons[0]
        # AGE on the BBR page is the player's age during `first` (the most
        # recent completed season). The projection targets the season after
        # that, so age needs one year added -- see CLAUDE.md 2026-08-15 and
        # GitHub issue #10 (was silently off-by-one every prior rollover).
        raw_age = player_season_stats[first].get("AGE", np.nan)
        projection_age = raw_age + 1 if pd.notna(raw_age) else raw_age
        decline_factor = compute_decline_factor(
            age=projection_age,
            composite_score=float(trend_profile["composite_score"]),
        )

        row = {
            "PLAYER_NAME": player,
            "GP_FACTOR": round(gp_factor, 3),
            "AGE": projection_age,
            "DECLINE_FACTOR": round(decline_factor, 3),
            "TREND_ROLE_SCORE": round(float(trend_profile["role_score"]), 3),
            "TREND_ROLE_BOOST": round(float(trend_profile["role_boost"]), 3),
            "TREND_SHIFT": round(float(trend_profile["trend_shift"]), 3),
            "TREND_COMPOSITE_SCORE": round(float(trend_profile["composite_score"]), 3),
        }

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
            row[cat]  = projected * gp_factor * decline_factor

        # ── FG% — volume-weighted, no GP adjustment ──────────────────────
        row["FG%"] = compute_weighted_fg_pct(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        # ── DD and TD — GP-adjusted ──────────────────────────────────────
        player_derived = derived_stats.get(player, {})
        row["DD"] = player_derived.get("DD", 0.0) * gp_factor * decline_factor
        row["TD"] = player_derived.get("TD", 0.0) * gp_factor * decline_factor

        # ── TECH — GP-adjusted ───────────────────────────────────────────
        row["TECH"] = tech_per_game.get(player, 0.05) * gp_factor * decline_factor

        # ── GP and MIN — raw, for filtering and display ──────────────────
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
        raw     = calibrate_category_values(raw, cat, config)
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
