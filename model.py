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

def _gp_weighted_blend_weights(final_weights: list[float],
                               player_season_stats: dict[str, pd.Series],
                               available_seasons: list[str],
                               full_season_games: int = 82) -> list[float]:
    """
    Dampen each season's trend-adjusted blend weight by how much of that
    season the player actually played (GP / full_season_games, capped at
    1.0), then renormalize to sum to 1.0.

    A thin-sample season (10 games before a season-ending injury) is noisy
    evidence of a player's true per-game rate -- weighting it the same as a
    full healthy season overstates confidence in that one data point. This
    is a *different* correction from GP_FACTOR: GP_FACTOR discounts the
    final per-game number for games expected to be missed going forward;
    this discounts a past season's INFLUENCE on the rate estimate itself,
    based on how much real data backs it. A season with zero games played
    contributes zero weight here rather than needing special-case handling
    elsewhere (part of GitHub issue #11's total-absence blind spot).
    """
    sample_weights = []
    for season, w in zip(available_seasons, final_weights):
        gp = player_season_stats[season].get("GP", np.nan)
        confidence = min(float(gp) / full_season_games, 1.0) if pd.notna(gp) and gp > 0 else 0.0
        sample_weights.append(w * confidence)

    total = sum(sample_weights)
    if total <= 0:
        # No season has any real GP data -- fall back to the trend weights
        # unchanged rather than dividing by zero. Shouldn't occur in
        # practice (a player only reaches this function via a season row
        # that exists), but this keeps the function total.
        return final_weights

    return [w / total for w in sample_weights]


def project_stats(season_dfs: list[pd.DataFrame],
                  weights: list[float],
                  derived_stats: dict[str, dict[str, float]],
                  tech_per_game: dict[str, float],
                  seasons: list[str] | None = None,
                  raw_player_sets: list[set[str]] | None = None,
                  raw_gp_by_season: list[dict[str, int]] | None = None) -> pd.DataFrame:
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

    `raw_player_sets`/`raw_gp_by_season` (optional, aligned by index with
    `seasons`/`season_dfs`) carry each season's *pre-qualification-filter*
    player names/GP, so a player entirely missing from the newest season can
    be told apart from one who played a few games but didn't clear
    `filter_qualified`'s bar — those are different situations and get
    different `DATA_AVAILABILITY_NOTE` text. Without them, everything falls
    back to season-absence language for the flag's own inputs (unit tests
    that construct pre-qualified `season_dfs` directly, mainly).
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
    for player in sorted(all_players):

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

        # A player missing from the most recent requested season's *qualified*
        # data (filter_qualified dropped them, or they have no row at all)
        # silently drops out of `available_seasons` above and the blend falls
        # back to whichever season they do have, with no signal that this
        # happened. GP_FACTOR/DECLINE_FACTOR can't fix this -- they only see
        # seasons that exist for the player, never the absence of one. This
        # can't distinguish cause (injury, trade, retirement, ...), so it
        # names the source season and leaves judgment to whoever's drafting,
        # who does know why -- see GitHub issue #11 and CLAUDE.md 2026-08-15.
        # Two distinct situations, worded differently so neither is claimed
        # inaccurately: truly no row for that season at all, vs. some games
        # played but below filter_qualified's bar (a real, if thin, season).
        data_availability_note = ""
        if seasons and seasons[0] not in available_seasons:
            newest_season  = seasons[0]
            fallback_source = available_seasons[0]
            raw_names = raw_player_sets[0] if raw_player_sets else None
            raw_gp    = raw_gp_by_season[0] if raw_gp_by_season else None
            if raw_names is not None and player in raw_names:
                gp_note = f" ({int(raw_gp[player])} GP)" if raw_gp and player in raw_gp else ""
                data_availability_note = (
                    f"Below qualification threshold in {newest_season}{gp_note} "
                    f"-- projected from {fallback_source}"
                )
            else:
                data_availability_note = (
                    f"No {newest_season} data -- projected from {fallback_source}"
                )

        # Step 1: trend-aware weight adjustment
        trend_profile = compute_trend_profile(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            base_weights=norm_weights,
        )
        final_weights = trend_profile["weights"]

        # Step 2: GP availability factor -- uses the trend weights, not the
        # sample-size-shrunk ones below. GP_FACTOR answers "how many games
        # will this player play going forward," which should track the same
        # recency/trend weighting as everything else; shrinking a thin
        # season's influence on the *rate estimate* (next) is an unrelated
        # concern and shouldn't also quietly change what GP_FACTOR measures.
        gp_factor = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        # Step 2b: shrink each season's blend weight toward zero for how
        # thin its own sample is, so a 10-game season doesn't count as much
        # toward the rate estimate as a 70-game one -- see
        # _gp_weighted_blend_weights. Used only for the counting-stat blend
        # below, not for gp_factor/decline_factor above.
        rate_weights = _gp_weighted_blend_weights(
            final_weights, player_season_stats, available_seasons,
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

        # A player with no game-log entry in ANY fetched season (never
        # matched by the NBA-API fetch at all, not just missing the newest
        # one) has no `derived_stats` entry -- DD/TD then hard-default to
        # 0.0 below, indistinguishable from a genuine zero-double-double
        # rate. This is a distinct claim from `data_availability_note`
        # above (which season the *other* stats came from) -- a player can
        # be true for both at once (e.g. Chris Paul: thin-but-real 2025-26
        # BBR season AND zero game logs anywhere), so both are recorded
        # rather than one overwriting the other. See CLAUDE.md 2026-08-15.
        player_derived = derived_stats.get(player, {})
        defaulted_fields = [f for f in ("DD", "TD") if f not in player_derived]
        defaulted_fields_note = (
            f"{'/'.join(defaulted_fields)} not available -- defaulted to zero"
            if defaulted_fields else ""
        )
        data_availability_note = "; ".join(
            n for n in (data_availability_note, defaulted_fields_note) if n
        )

        row = {
            "PLAYER_NAME": player,
            "GP_FACTOR": round(gp_factor, 3),
            "AGE": projection_age,
            "DECLINE_FACTOR": round(decline_factor, 3),
            "DATA_AVAILABILITY_NOTE": data_availability_note,
            "TREND_ROLE_SCORE": round(float(trend_profile["role_score"]), 3),
            "TREND_ROLE_BOOST": round(float(trend_profile["role_boost"]), 3),
            "TREND_SHIFT": round(float(trend_profile["trend_shift"]), 3),
            "TREND_COMPOSITE_SCORE": round(float(trend_profile["composite_score"]), 3),
        }

        # ── Counting categories — GP-adjusted ───────────────────────────
        for cat in counting_cats:
            vals, wts = [], []
            for season, w in zip(available_seasons, rate_weights):
                v = player_season_stats[season].get(cat, np.nan)
                if pd.notna(v):
                    vals.append(v)
                    wts.append(w)

            if not vals:
                row[cat] = np.nan
                row[f"{cat}_RATE"] = np.nan
                continue

            wt        = sum(wts)
            projected = sum(v * w for v, w in zip(vals, wts)) / wt
            # `{cat}` stays the GP/decline-adjusted value everything else in
            # the pipeline (G-scores, the draft board's headline numbers)
            # already depends on -- not touched here. `{cat}_RATE` is the
            # same season-blended number BEFORE that multiply: the pure
            # skill-rate projection, with no availability or aging tax
            # baked in. Exists so a consumer can show "why" a player's
            # headline number is lower than their rate alone would suggest,
            # instead of GP_FACTOR/DECLINE_FACTOR's effect being invisible.
            row[f"{cat}_RATE"] = projected
            row[cat] = projected * gp_factor * decline_factor

        # ── FG% — volume-weighted, no GP adjustment ──────────────────────
        row["FG%"] = compute_weighted_fg_pct(
            player_season_stats=player_season_stats,
            available_seasons=available_seasons,
            weights=final_weights,
        )

        # ── DD and TD — GP-adjusted ──────────────────────────────────────
        row["DD_RATE"] = player_derived.get("DD", 0.0)
        row["TD_RATE"] = player_derived.get("TD", 0.0)
        row["DD"] = row["DD_RATE"] * gp_factor * decline_factor
        row["TD"] = row["TD_RATE"] * gp_factor * decline_factor

        # ── TECH — GP-adjusted ───────────────────────────────────────────
        row["TECH_RATE"] = tech_per_game.get(player, 0.05)
        row["TECH"] = row["TECH_RATE"] * gp_factor * decline_factor

        # ── GP and MIN — raw, for filtering and display ──────────────────
        row["GP"]  = player_season_stats[first].get("GP", np.nan)
        row["MIN"] = player_season_stats[first].get("MIN", np.nan)

        rows.append(row)

    return pd.DataFrame(rows)


# ── Tau (weekly variance) ─────────────────────────────────────────────────────

def add_week_key(logs: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of a player's game log with an ISO year_week key attached.

    Shared by compute_tau (weekly variance) and trade.py (weekly sample bank)
    so both agree on exactly what "a week" means.
    """
    logs = logs.copy()
    logs["GAME_DATE"] = pd.to_datetime(logs["GAME_DATE"])
    iso = logs["GAME_DATE"].dt.isocalendar()
    logs["WEEK_KEY"] = iso["year"].astype(str) + "_" + iso["week"].astype(str)
    return logs


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

            logs = add_week_key(logs)

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
      1. Compute league mean and sigma on raw (milestone-calibrated) values
         -- same scale compute_tau uses, see the no-skew-transform note below
      2. Player tau lookup (player-specific → league median fallback)
      3. G = (player_raw - mean) / sqrt(sigma^2 + kappa * tau^2)
      4. Flip sign for 'low is better' categories
      5. FG%: multiply by (player_FGA / league_avg_FGA) — volume weighting
      6. Clip to ±3.5 — prevents one outlier compressing everyone else
      7. Multiply by category weight
    """
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

        raw = df[cat].fillna(0.0).values.astype(float)
        raw = calibrate_category_values(raw, cat, config)

        # No skew transform here: compute_tau (model.py) computes tau from
        # raw, untransformed per-game weekly averages, so mean/sigma must
        # stay on that same raw scale too, or sqrt(sigma^2 + kappa*tau^2)
        # silently adds two incompatible units. A prior Box-Cox-transformed
        # version of this line did exactly that -- see the 2026-10 fix for
        # the mechanism (tau, computed on raw per-game values, swamped the
        # much-smaller transformed-scale sigma for high-variance counting
        # categories like PTS, while leaving naturally-small sparse
        # categories like DD/TD comparatively untouched -- the likely real
        # cause of issue #12's 34%-DD/TD-vs-0.6%-PTS variance split). No
        # published G-score-family method (the formula this function
        # implements) transforms a stat before standardizing either --
        # skew is left to the variance term, not a separate nonlinear step.
        league_mean  = raw.mean()
        league_sigma = raw.std()

        if league_sigma < 1e-8:
            df[f"{cat}_G"] = 0.0
            continue

        g_scores = []
        for i, row in df.iterrows():
            player = row["PLAYER_NAME"]
            tau    = player_tau.get(player, {}).get(cat, league_tau.get(cat, 1.0))

            denom = np.sqrt(league_sigma ** 2 + kappa * tau ** 2)
            g     = (raw[df.index.get_loc(i)] - league_mean) / denom

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
