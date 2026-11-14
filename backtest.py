"""
backtest.py — Walk-forward backtest harness
============================================
For each target season T, run the projection using only seasons before T
and score against what actually happened in T.  No projection maths changed.

Usage:
    python backtest.py                       # all scorable folds
    python backtest.py --target 2024-25      # one fold
    python backtest.py --save-as before      # writes diagnostics/backtest/before/
    python backtest.py --compare before after
    python backtest.py --target 2026-27 --unseal-holdout
"""

import argparse
import copy
import functools
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

from config import LEAGUE_CONFIG
from data import load_bbr_csv, filter_qualified, derive_stats_from_logs, fetch_game_logs
from identity import canonical_player_key
from main import run_projection
from model import compute_g_scores

# ── Constants ─────────────────────────────────────────────────────────────────

FULL_SEASON_GAMES: dict[str, int] = {
    "2019-20": 72,
    "2020-21": 72,
}

BBR_FILENAME_PATTERN = "basketball_reference_{slug}_total_stats.csv"

FOLDS: dict[str, dict] = {
    "2021-22": {"inputs": ["2020-21", "2019-20", "2018-19"], "tuned": False},
    "2022-23": {"inputs": ["2021-22", "2020-21", "2019-20"], "tuned": False},
    "2023-24": {"inputs": ["2022-23", "2021-22", "2020-21"], "tuned": True},
    "2024-25": {"inputs": ["2023-24", "2022-23", "2021-22"], "tuned": True},
    "2025-26": {"inputs": ["2024-25", "2023-24", "2022-23"], "tuned": True},
    "2026-27": {"inputs": ["2025-26", "2024-25", "2023-24"], "tuned": True, "holdout": True},
}

INJURY_EARLIEST_SEASON = "2021-22"

MIN_GP_FOR_TARGET = 20

OUTPUT_DIR = Path("diagnostics/backtest")

COUNTING_CATS = ["FGM", "FGA", "3PTM", "FTM", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF"]

AGE_BUCKETS = [
    ("22-", lambda a: a <= 22),
    ("23-24", lambda a: 23 <= a <= 24),
    ("25-27", lambda a: 25 <= a <= 27),
    ("28-30", lambda a: 28 <= a <= 30),
    ("31-33", lambda a: 31 <= a <= 33),
    ("34+", lambda a: a >= 34),
]


# ── Leak guard ────────────────────────────────────────────────────────────────

class FutureDataLeak(Exception):
    pass


def _season_start_year(season: str) -> int:
    return int(season.split("-")[0])


def _make_leak_guard(target: str, original_fn, fn_name: str):
    target_start = _season_start_year(target)

    @functools.wraps(original_fn)
    def guarded(*args, **kwargs):
        check_args = list(args) + list(kwargs.values())
        for arg in check_args:
            if isinstance(arg, str) and "-" in arg:
                try:
                    yr = _season_start_year(arg)
                    if 2000 <= yr <= 2050 and yr >= target_start:
                        raise FutureDataLeak(
                            f"{fn_name} requested season {arg!r} "
                            f"which is >= target {target!r}"
                        )
                except (ValueError, IndexError):
                    pass
            if isinstance(arg, list):
                for item in arg:
                    if isinstance(item, str) and "-" in item:
                        try:
                            yr = _season_start_year(item)
                            if 2000 <= yr <= 2050 and yr >= target_start:
                                raise FutureDataLeak(
                                    f"{fn_name} requested season {item!r} "
                                    f"which is >= target {target!r}"
                                )
                        except (ValueError, IndexError):
                            pass
        return original_fn(*args, **kwargs)

    return guarded


# ── Fold config ───────────────────────────────────────────────────────────────

def _season_slug(season: str) -> str:
    return season.replace("-", "_")


def _bbr_filename(season: str) -> str:
    return BBR_FILENAME_PATTERN.format(slug=_season_slug(season))


def fold_config(target: str) -> dict:
    """Build a LEAGUE_CONFIG copy for one backtest fold."""
    fold = FOLDS[target]
    inputs = fold["inputs"]

    cfg = copy.deepcopy(LEAGUE_CONFIG)
    cfg["game_log_seasons"] = list(inputs)
    cfg["bbr_files"] = [_bbr_filename(s) for s in inputs]

    suffix = f"_{_season_slug(target)}"
    for key in list(cfg.keys()):
        if key.endswith("_cache"):
            base = cfg[key]
            name, ext = base.rsplit(".", 1) if "." in base else (base, "pkl")
            cfg[key] = f"{name}{suffix}.{ext}"

    games_map = {s: FULL_SEASON_GAMES.get(s, 82) for s in inputs}
    cfg["full_season_games"] = games_map

    all_seasons_have_injuries = all(
        _season_start_year(s) >= _season_start_year(INJURY_EARLIEST_SEASON)
        for s in inputs
    )
    cfg["_fetch_injuries"] = all_seasons_have_injuries
    cfg["_target"] = target
    cfg["_tuned"] = fold.get("tuned", False)

    return cfg


def scorable_folds() -> list[str]:
    """Return targets whose input BBR files all exist on disk."""
    result = []
    for target, fold in FOLDS.items():
        if fold.get("holdout"):
            continue
        if all(Path(_bbr_filename(s)).exists() for s in fold["inputs"]):
            result.append(target)
    return result


# ── Actuals ───────────────────────────────────────────────────────────────────

def build_actuals(target: str, projected_players: list[str],
                  league_tau: dict[str, float], config: dict) -> pd.DataFrame:
    """Build the actual-outcome frame for season T from BBR + game logs."""
    bbr_path = _bbr_filename(target)
    if not Path(bbr_path).exists():
        raise FileNotFoundError(f"No BBR file for target season: {bbr_path}")

    raw = load_bbr_csv(bbr_path)
    raw["PLAYER_KEY"] = raw["PLAYER_NAME"].apply(canonical_player_key)

    projected_keys = {canonical_player_key(p) for p in projected_players}
    actual = raw[raw["PLAYER_KEY"].isin(projected_keys)].copy()

    season_games = FULL_SEASON_GAMES.get(target, 82)

    cache_file = f"game_log_cache_{_season_slug(target)}_actuals.pkl"
    game_logs, _ = fetch_game_logs(
        player_names=actual["PLAYER_NAME"].tolist(),
        seasons=[target],
        cache_file=cache_file,
        return_health=True,
    )
    derived = derive_stats_from_logs(game_logs)
    # Re-key by canonical key so accented BBR names match ASCII cache names
    derived_by_key = {canonical_player_key(n): v for n, v in derived.items()}

    rows = []
    for _, row in actual.iterrows():
        name = row["PLAYER_NAME"]
        gp = row.get("GP", 0)
        if pd.isna(gp):
            gp = 0

        r = {
            "PLAYER_NAME": name,
            "PLAYER_KEY": canonical_player_key(name),
            "ACTUAL_GP": gp,
            "ACTUAL_SEASON_GAMES": season_games,
        }

        for cat in COUNTING_CATS:
            r[f"ACTUAL_{cat}_RATE"] = row.get(cat, np.nan)

        fgm = row.get("FGM", np.nan)
        fga = row.get("FGA", np.nan)
        r["ACTUAL_FG%_RATE"] = (fgm / fga) if pd.notna(fga) and fga > 0 else np.nan

        player_derived = derived_by_key.get(canonical_player_key(name), {})
        r["ACTUAL_DD_RATE"] = player_derived.get("DD", 0.0)
        r["ACTUAL_TD_RATE"] = player_derived.get("TD", 0.0)

        if row.get("AGE") is not None and pd.notna(row.get("AGE")):
            r["ACTUAL_AGE"] = row["AGE"]
        else:
            r["ACTUAL_AGE"] = np.nan

        rows.append(r)

    # Add rows for projected players with no target-season BBR data (busts/injuries)
    actual_keys = {r["PLAYER_KEY"] for r in rows}
    for pname in projected_players:
        pkey = canonical_player_key(pname)
        if pkey not in actual_keys:
            rows.append({
                "PLAYER_NAME": pname,
                "PLAYER_KEY": pkey,
                "ACTUAL_GP": 0,
                "ACTUAL_SEASON_GAMES": season_games,
                **{f"ACTUAL_{c}_RATE": np.nan for c in COUNTING_CATS},
                "ACTUAL_FG%_RATE": np.nan,
                "ACTUAL_DD_RATE": np.nan,
                "ACTUAL_TD_RATE": np.nan,
                "ACTUAL_AGE": np.nan,
            })

    df = pd.DataFrame(rows)

    per_game_mask = df["ACTUAL_GP"] >= MIN_GP_FOR_TARGET

    rate_cats = [f"ACTUAL_{c}_RATE" for c in COUNTING_CATS] + ["ACTUAL_DD_RATE", "ACTUAL_TD_RATE"]
    rate_df = df[per_game_mask].copy()

    actual_projected = rate_df.copy()
    actual_projected_rows = []
    for _, arow in actual_projected.iterrows():
        proj_row = {"PLAYER_NAME": arow["PLAYER_NAME"]}
        for cat in COUNTING_CATS:
            proj_row[cat] = arow.get(f"ACTUAL_{cat}_RATE", np.nan)
            proj_row[f"{cat}_RATE"] = arow.get(f"ACTUAL_{cat}_RATE", np.nan)
        proj_row["DD"] = arow.get("ACTUAL_DD_RATE", 0.0)
        proj_row["DD_RATE"] = arow.get("ACTUAL_DD_RATE", 0.0)
        proj_row["TD"] = arow.get("ACTUAL_TD_RATE", 0.0)
        proj_row["TD_RATE"] = arow.get("ACTUAL_TD_RATE", 0.0)
        proj_row["GP"] = arow["ACTUAL_GP"]
        proj_row["MIN"] = arow.get(f"ACTUAL_MIN_RATE", 20) if f"ACTUAL_MIN_RATE" in arow.index else 20
        proj_row["TECH"] = 0.05
        proj_row["TECH_RATE"] = 0.05
        proj_row["FG%"] = arow.get("ACTUAL_FG%_RATE", np.nan)
        proj_row["GP_FACTOR"] = 1.0
        proj_row["DECLINE_FACTOR"] = 1.0
        proj_row["INJURY_DISCOUNT_FACTOR"] = 1.0
        actual_projected_rows.append(proj_row)

    if actual_projected_rows:
        actual_proj_df = pd.DataFrame(actual_projected_rows)
        actual_rankings = compute_g_scores(
            actual_proj_df, {}, league_tau, config,
        )
        df = df.merge(
            actual_rankings[["PLAYER_NAME", "TOTAL_VALUE", "RANK"]].rename(
                columns={"TOTAL_VALUE": "ACTUAL_PG_VALUE", "RANK": "ACTUAL_PG_RANK"}
            ),
            on="PLAYER_NAME", how="left",
        )
    else:
        df["ACTUAL_PG_VALUE"] = np.nan
        df["ACTUAL_PG_RANK"] = np.nan

    # ── Total-value target: season totals through compute_g_scores ──────
    # Every pooled player gets a row. Counting stats = rate * GP/season_games.
    # GP=0 → all zeros (FGA=0 so FG% is NaN, correctly excluded from scoring).
    total_rows = []
    for _, trow in df.iterrows():
        gp = trow["ACTUAL_GP"]
        gp_frac = gp / season_games if season_games > 0 else 0.0
        tr = {"PLAYER_NAME": trow["PLAYER_NAME"]}
        for cat in COUNTING_CATS:
            rate = trow.get(f"ACTUAL_{cat}_RATE", np.nan)
            tr[cat] = rate * gp_frac if pd.notna(rate) and gp > 0 else 0.0
            tr[f"{cat}_RATE"] = rate if pd.notna(rate) else 0.0
        dd_rate = trow.get("ACTUAL_DD_RATE", 0.0) if pd.notna(trow.get("ACTUAL_DD_RATE")) else 0.0
        td_rate = trow.get("ACTUAL_TD_RATE", 0.0) if pd.notna(trow.get("ACTUAL_TD_RATE")) else 0.0
        tr["DD"] = dd_rate * gp_frac if gp > 0 else 0.0
        tr["DD_RATE"] = dd_rate
        tr["TD"] = td_rate * gp_frac if gp > 0 else 0.0
        tr["TD_RATE"] = td_rate
        tr["TECH"] = 0.05 * gp_frac if gp > 0 else 0.0
        tr["TECH_RATE"] = 0.05
        fgm_total = tr["FGM"]
        fga_total = tr["FGA"]
        tr["FG%"] = (fgm_total / fga_total) if fga_total > 0 else np.nan
        tr["GP"] = gp
        tr["GP_FACTOR"] = 1.0
        tr["MIN"] = trow.get("ACTUAL_MIN_RATE", 20) * gp_frac if gp > 0 else 0.0
        tr["DECLINE_FACTOR"] = 1.0
        tr["INJURY_DISCOUNT_FACTOR"] = 1.0
        total_rows.append(tr)

    if total_rows:
        total_proj_df = pd.DataFrame(total_rows)
        total_rankings = compute_g_scores(total_proj_df, {}, league_tau, config)
        df = df.merge(
            total_rankings[["PLAYER_NAME", "TOTAL_VALUE", "RANK"]].rename(
                columns={"TOTAL_VALUE": "ACTUAL_TOTAL_VALUE", "RANK": "ACTUAL_TOTAL_RANK"}
            ),
            on="PLAYER_NAME", how="left",
        )
    else:
        df["ACTUAL_TOTAL_VALUE"] = np.nan
        df["ACTUAL_TOTAL_RANK"] = np.nan

    assert df["ACTUAL_TOTAL_RANK"].notna().all(), "NaN in ACTUAL_TOTAL_RANK"

    return df


# ── Baselines ─────────────────────────────────────────────────────────────────

def persistence_baseline(target: str,
                         derived_by_key: dict[str, dict] | None = None,
                         projected_keys: set[str] | None = None) -> pd.DataFrame:
    """Season T-1's per-game line and GP as the projection."""
    fold = FOLDS[target]
    prev_season = fold["inputs"][0]
    prev_path = _bbr_filename(prev_season)
    if not Path(prev_path).exists():
        return pd.DataFrame()

    raw = load_bbr_csv(prev_path)
    prev_season_games = FULL_SEASON_GAMES.get(prev_season, 82)

    rows = []
    seen_keys: set[str] = set()
    for _, r in raw.iterrows():
        pkey = canonical_player_key(r["PLAYER_NAME"])
        seen_keys.add(pkey)
        fgm = r.get("FGM", np.nan)
        fga = r.get("FGA", np.nan)
        row = {
            "PLAYER_NAME": r["PLAYER_NAME"],
            "PLAYER_KEY": pkey,
            "GP": r.get("GP", np.nan),
            "FG%_RATE": (fgm / fga) if pd.notna(fga) and fga > 0 else np.nan,
            "_season_games": prev_season_games,
        }
        for cat in COUNTING_CATS:
            row[f"{cat}_RATE"] = r.get(cat, np.nan)
        pd_stats = derived_by_key.get(pkey, {}) if derived_by_key else {}
        row["DD_RATE"] = pd_stats.get("DD", 0.0)
        row["TD_RATE"] = pd_stats.get("TD", 0.0)
        rows.append(row)

    # Add zero-GP rows for projected players with no T-1 BBR data
    if projected_keys:
        for pkey in projected_keys:
            if pkey not in seen_keys:
                rows.append({
                    "PLAYER_NAME": pkey,
                    "PLAYER_KEY": pkey,
                    "GP": 0,
                    "FG%_RATE": np.nan,
                    "_season_games": prev_season_games,
                    **{f"{c}_RATE": 0.0 for c in COUNTING_CATS},
                    "DD_RATE": 0.0,
                    "TD_RATE": 0.0,
                })

    return pd.DataFrame(rows)


def marcel_lite_baseline(target: str,
                         derived_by_key: dict[str, dict] | None = None,
                         projected_keys: set[str] | None = None) -> pd.DataFrame:
    """Three-season weighted average with regression toward the mean.

    Regression: reliability = M / (M + 1000) where M = weighted total minutes.
    GP: 0.5 * weighted_GP + 0.5 * pool_mean_GP.
    Pool means are computed over the fold's projected players only.
    """
    fold = FOLDS[target]
    inputs = fold["inputs"]

    dfs = []
    season_names = []
    for s in inputs:
        path = _bbr_filename(s)
        if Path(path).exists():
            df = load_bbr_csv(path)
            df["_season"] = s
            dfs.append(df)
            season_names.append(s)
    if not dfs:
        return pd.DataFrame()

    marcel_weights = [5, 4, 3][:len(dfs)]

    all_players = set()
    season_data: dict[str, list[tuple]] = {}
    for df, w, s in zip(dfs, marcel_weights, season_names):
        for _, r in df.iterrows():
            all_players.add(r["PLAYER_NAME"])
            season_data.setdefault(r["PLAYER_NAME"], []).append((r, w, s))

    # First pass: compute weighted stats for all players so we can filter to pool
    preliminary: dict[str, dict] = {}
    for player in sorted(all_players):
        entries = season_data.get(player, [])
        if not entries:
            continue
        info: dict[str, object] = {}
        for cat in COUNTING_CATS + ["GP", "MIN"]:
            vals, wts = [], []
            for r, w, _s in entries:
                v = r.get(cat, np.nan)
                if pd.notna(v):
                    vals.append(v)
                    wts.append(w)
            if vals:
                info[cat] = sum(v * w for v, w in zip(vals, wts)) / sum(wts)
            else:
                info[cat] = 0.0
        preliminary[player] = info

    # Pool means: from projected players only (if provided), else top-130 by MIN
    if projected_keys:
        pool_players = [p for p in preliminary if canonical_player_key(p) in projected_keys]
    else:
        sorted_by_min = sorted(preliminary.items(), key=lambda x: x[1].get("MIN", 0), reverse=True)
        pool_players = [p for p, _ in sorted_by_min[:130]]

    pool_means: dict[str, float] = {}
    for cat in COUNTING_CATS + ["GP"]:
        vals = [preliminary[p].get(cat, 0.0) for p in pool_players if p in preliminary]
        pool_means[cat] = float(np.mean(vals)) if vals else 0.0

    rows = []
    for player in sorted(all_players):
        entries = season_data.get(player, [])
        if not entries:
            continue

        row: dict[str, object] = {"PLAYER_NAME": player, "PLAYER_KEY": canonical_player_key(player)}

        # Reliability: M / (M + 1000) where M = sum(w_i * total_min_i) / sum(w_i)
        min_vals, min_wts = [], []
        gp_vals_for_min = []
        for r, w, s in entries:
            gp = r.get("GP", 0)
            mpg = r.get("MIN", 0)
            if pd.notna(gp) and pd.notna(mpg):
                s_games = FULL_SEASON_GAMES.get(s, 82)
                total_min = float(mpg) * float(gp)
                min_vals.append(total_min)
                min_wts.append(w)
        if min_vals:
            weighted_min = sum(v * w for v, w in zip(min_vals, min_wts)) / sum(min_wts)
        else:
            weighted_min = 0.0
        reliability = weighted_min / (weighted_min + 1000.0)

        for cat in COUNTING_CATS:
            vals, wts = [], []
            for r, w, _s in entries:
                v = r.get(cat, np.nan)
                if pd.notna(v):
                    vals.append(v)
                    wts.append(w)
            if vals:
                weighted = sum(v * w for v, w in zip(vals, wts)) / sum(wts)
                projected = reliability * weighted + (1 - reliability) * pool_means.get(cat, 0)
            else:
                projected = pool_means.get(cat, 0)
            row[f"{cat}_RATE"] = projected

        # GP regression: 0.5 * weighted_GP + 0.5 * pool_mean_GP
        gp_vals, gp_wts = [], []
        for r, w, _s in entries:
            v = r.get("GP", np.nan)
            if pd.notna(v):
                gp_vals.append(v)
                gp_wts.append(w)
        if gp_vals:
            weighted_gp = sum(v * w for v, w in zip(gp_vals, gp_wts)) / sum(gp_wts)
            row["GP"] = 0.5 * weighted_gp + 0.5 * pool_means.get("GP", 60)
        else:
            row["GP"] = pool_means.get("GP", 60)

        # Age adjustment (unchanged)
        age_vals = [r.get("AGE", np.nan) for r, _, _s in entries]
        age_vals = [a for a in age_vals if pd.notna(a)]
        if age_vals:
            age = max(age_vals) + 1
            if age < 29:
                age_adj = 1.0 + 0.006 * (29 - age)
            else:
                age_adj = 1.0 - 0.003 * (age - 29)
        else:
            age_adj = 1.0

        for cat in COUNTING_CATS:
            if f"{cat}_RATE" in row and pd.notna(row[f"{cat}_RATE"]):
                row[f"{cat}_RATE"] *= age_adj

        # FG% from projected rates
        fgm_r = row.get("FGM_RATE", 0)
        fga_r = row.get("FGA_RATE", 0)
        row["FG%_RATE"] = (fgm_r / fga_r) if fga_r and fga_r > 0 else np.nan

        # DD/TD from T-1 game logs
        pkey = canonical_player_key(player)
        pd_stats = derived_by_key.get(pkey, {}) if derived_by_key else {}
        row["DD_RATE"] = pd_stats.get("DD", 0.0)
        row["TD_RATE"] = pd_stats.get("TD", 0.0)

        rows.append(row)

    return pd.DataFrame(rows)


# ── Bootstrap ────────────────────────────────────────────────────────────────

def paired_bootstrap_rho(ranks_a: np.ndarray, ranks_b: np.ndarray,
                         actual_ranks: np.ndarray,
                         n_boot: int = 2000, seed: int = 42) -> dict:
    """Paired bootstrap: P(model A beats B on Spearman rho), with 95% CI on delta."""
    rng = np.random.default_rng(seed)
    n = len(actual_ranks)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        rho_a = spearmanr(ranks_a[idx], actual_ranks[idx]).statistic
        rho_b = spearmanr(ranks_b[idx], actual_ranks[idx]).statistic
        deltas[i] = rho_a - rho_b
    ci_lo, ci_hi = np.percentile(deltas, [2.5, 97.5])
    return {
        "mean_delta": round(float(np.mean(deltas)), 4),
        "ci_lo": round(float(ci_lo), 4),
        "ci_hi": round(float(ci_hi), 4),
        "p_a_wins": round(float((deltas > 0).mean()), 3),
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_fold_metrics(projected_rankings: pd.DataFrame,
                         actuals: pd.DataFrame,
                         league_tau: dict[str, float],
                         config: dict,
                         method: str = "model") -> dict:
    """Compute all metrics for one fold / one method."""
    proj = projected_rankings.copy()
    proj["PLAYER_KEY"] = proj["PLAYER_NAME"].apply(canonical_player_key)

    merged = actuals.merge(proj, on="PLAYER_KEY", how="inner", suffixes=("_actual", "_proj"))

    per_game = merged[merged["ACTUAL_GP"] >= MIN_GP_FOR_TARGET].copy()

    metrics: dict[str, object] = {"method": method, "n_players": len(merged), "n_per_game": len(per_game)}

    # Per-category MAE and Pearson r
    cat_metrics = {}
    for cat in COUNTING_CATS:
        rate_col = f"{cat}_RATE"
        actual_col = f"ACTUAL_{cat}_RATE"
        if rate_col in per_game.columns and actual_col in per_game.columns:
            valid = per_game[[rate_col, actual_col]].dropna()
            if len(valid) >= 5:
                mae = (valid[rate_col] - valid[actual_col]).abs().mean()
                r, _ = pearsonr(valid[rate_col], valid[actual_col])
                cat_metrics[cat] = {"mae": round(mae, 4), "pearson_r": round(r, 4)}
    metrics["category_metrics"] = cat_metrics

    # Age bias
    if "AGE" in per_game.columns and "ACTUAL_AGE" in per_game.columns:
        age_col = per_game["AGE"].fillna(per_game["ACTUAL_AGE"])
    elif "AGE" in per_game.columns:
        age_col = per_game["AGE"]
    elif "ACTUAL_AGE" in per_game.columns:
        age_col = per_game["ACTUAL_AGE"]
    else:
        age_col = pd.Series(dtype=float)

    if "TOTAL_VALUE" in per_game.columns and "ACTUAL_PG_VALUE" in per_game.columns:
        age_bias = {}
        for bucket_name, bucket_fn in AGE_BUCKETS:
            mask = age_col.apply(lambda a: bucket_fn(a) if pd.notna(a) else False)
            subset = per_game[mask]
            if len(subset) >= 3:
                diff = (subset["TOTAL_VALUE"] - subset["ACTUAL_PG_VALUE"]).mean()
                age_bias[bucket_name] = round(diff, 3)
        metrics["age_bias"] = age_bias

    # GP MAE
    if "GP_FACTOR" in merged.columns:
        season_games = actuals["ACTUAL_SEASON_GAMES"].iloc[0] if len(actuals) > 0 else 82
        merged["PROJECTED_GP"] = merged["GP_FACTOR"] * season_games
        valid_gp = merged[["PROJECTED_GP", "ACTUAL_GP"]].dropna()
        if len(valid_gp) >= 5:
            metrics["gp_mae"] = round((valid_gp["PROJECTED_GP"] - valid_gp["ACTUAL_GP"]).abs().mean(), 2)
            if valid_gp["PROJECTED_GP"].std() > 0:
                slope = np.polyfit(valid_gp["PROJECTED_GP"], valid_gp["ACTUAL_GP"], 1)[0]
                metrics["gp_slope"] = round(slope, 3)

    # Spearman: per-game value
    if "ACTUAL_PG_RANK" in per_game.columns and "RANK" in per_game.columns:
        valid_rank = per_game[["RANK", "ACTUAL_PG_RANK"]].dropna()
        if len(valid_rank) >= 5:
            rho, _ = spearmanr(valid_rank["RANK"], valid_rank["ACTUAL_PG_RANK"])
            metrics["spearman_per_game"] = round(rho, 4)

    # Spearman: total value
    if "ACTUAL_TOTAL_RANK" in merged.columns and "RANK" in merged.columns:
        valid_total = merged[["RANK", "ACTUAL_TOTAL_RANK"]].dropna()
        if len(valid_total) >= 5:
            rho, _ = spearmanr(valid_total["RANK"], valid_total["ACTUAL_TOTAL_RANK"])
            metrics["spearman_total"] = round(rho, 4)

    # Top-50 capture
    if "ACTUAL_TOTAL_RANK" in merged.columns and "RANK" in merged.columns:
        actual_top50 = set(merged[merged["ACTUAL_TOTAL_RANK"] <= 50]["PLAYER_KEY"])
        proj_top50 = set(merged.nsmallest(50, "RANK")["PLAYER_KEY"])
        if actual_top50:
            metrics["top50_capture"] = round(len(actual_top50 & proj_top50) / len(actual_top50), 3)

    return metrics


def _baseline_to_proj_rows(baseline_df: pd.DataFrame,
                           season_games: int = 82) -> list[dict]:
    """Convert a baseline DataFrame into projection rows for compute_g_scores."""
    proj_rows = []
    for _, r in baseline_df.iterrows():
        row = {"PLAYER_NAME": r["PLAYER_NAME"]}
        gp = r.get("GP", 60)
        if pd.isna(gp):
            gp = 60
        sg = r.get("_season_games", season_games)
        gp_factor = min(gp / sg, 1.0) if sg > 0 else 1.0
        for cat in COUNTING_CATS:
            rate = r.get(f"{cat}_RATE", np.nan)
            row[cat] = rate * gp_factor if pd.notna(rate) else np.nan
            row[f"{cat}_RATE"] = rate
        row["DD"] = r.get("DD_RATE", 0.0) * gp_factor
        row["DD_RATE"] = r.get("DD_RATE", 0.0)
        row["TD"] = r.get("TD_RATE", 0.0) * gp_factor
        row["TD_RATE"] = r.get("TD_RATE", 0.0)
        row["TECH"] = 0.05 * gp_factor
        row["TECH_RATE"] = 0.05
        fgm_r = r.get("FGM_RATE", np.nan)
        fga_r = r.get("FGA_RATE", np.nan)
        row["FG%"] = r.get("FG%_RATE", np.nan)
        if pd.isna(row["FG%"]) and pd.notna(fgm_r) and pd.notna(fga_r) and fga_r > 0:
            row["FG%"] = fgm_r / fga_r
        row["GP"] = gp
        row["GP_FACTOR"] = gp_factor
        row["MIN"] = r.get("MIN_RATE", 20) if "MIN_RATE" in r.index else 20
        row["DECLINE_FACTOR"] = 1.0
        row["INJURY_DISCOUNT_FACTOR"] = 1.0
        proj_rows.append(row)
    return proj_rows


def score_baseline(baseline_df: pd.DataFrame, actuals: pd.DataFrame,
                   league_tau: dict[str, float], config: dict,
                   method: str, target: str | None = None) -> dict:
    """Score a baseline by converting it into rankings, then computing metrics."""
    if baseline_df.empty:
        return {"method": method, "n_players": 0}

    projected_keys = set(actuals["PLAYER_KEY"])
    baseline_df["PLAYER_KEY"] = baseline_df["PLAYER_NAME"].apply(canonical_player_key)
    baseline_df = baseline_df[baseline_df["PLAYER_KEY"].isin(projected_keys)].copy()

    if baseline_df.empty:
        return {"method": method, "n_players": 0}

    season_games = 82
    if target:
        fold = FOLDS[target]
        prev_season = fold["inputs"][0]
        season_games = FULL_SEASON_GAMES.get(prev_season, 82)

    proj_rows = _baseline_to_proj_rows(baseline_df, season_games)
    proj_df = pd.DataFrame(proj_rows)
    rankings = compute_g_scores(proj_df, {}, league_tau, config)

    return compute_fold_metrics(rankings, actuals, league_tau, config, method=method)


def _compute_bootstrap(rankings, persist, marcel, common_actuals, common_keys,
                       league_tau, cfg, target: str | None = None):
    """Paired bootstrap comparing model vs each baseline on both total and per-game."""
    bootstrap = {}
    proj_m = rankings.copy()
    proj_m["PLAYER_KEY"] = proj_m["PLAYER_NAME"].apply(canonical_player_key)

    # Total-value alignment
    merged_total = common_actuals.merge(proj_m[["PLAYER_KEY", "RANK"]], on="PLAYER_KEY", how="inner")
    valid_total = merged_total[["PLAYER_KEY", "RANK", "ACTUAL_TOTAL_RANK"]].dropna()

    # Per-game alignment (GP >= MIN_GP_FOR_TARGET)
    pg_actuals = common_actuals[common_actuals["ACTUAL_GP"] >= MIN_GP_FOR_TARGET]
    merged_pg = pg_actuals.merge(proj_m[["PLAYER_KEY", "RANK"]], on="PLAYER_KEY", how="inner")
    valid_pg = merged_pg[["PLAYER_KEY", "RANK", "ACTUAL_PG_RANK"]].dropna()

    if len(valid_total) < 20:
        return bootstrap

    season_games = 82
    if target:
        fold = FOLDS[target]
        prev_season = fold["inputs"][0]
        season_games = FULL_SEASON_GAMES.get(prev_season, 82)

    for bl_name, bl_df in [("persistence", persist), ("marcel_lite", marcel)]:
        if bl_df.empty:
            continue
        bl_copy = bl_df.copy()
        bl_copy["PLAYER_KEY"] = bl_copy["PLAYER_NAME"].apply(canonical_player_key)
        bl_filtered = bl_copy[bl_copy["PLAYER_KEY"].isin(common_keys)]

        bl_proj_rows = _baseline_to_proj_rows(bl_filtered, season_games)
        if not bl_proj_rows:
            continue

        bl_proj_df = pd.DataFrame(bl_proj_rows)
        bl_rankings = compute_g_scores(bl_proj_df, {}, league_tau, cfg)
        bl_rankings["PLAYER_KEY"] = bl_rankings["PLAYER_NAME"].apply(canonical_player_key)

        result: dict = {}

        # Total-value bootstrap
        aligned_t = valid_total.merge(
            bl_rankings[["PLAYER_KEY", "RANK"]].rename(columns={"RANK": "BL_RANK"}),
            on="PLAYER_KEY", how="inner",
        ).dropna(subset=["RANK", "BL_RANK", "ACTUAL_TOTAL_RANK"])
        if len(aligned_t) >= 20:
            result["total"] = paired_bootstrap_rho(
                aligned_t["RANK"].values,
                aligned_t["BL_RANK"].values,
                aligned_t["ACTUAL_TOTAL_RANK"].values,
            )

        # Per-game bootstrap
        aligned_pg = valid_pg.merge(
            bl_rankings[["PLAYER_KEY", "RANK"]].rename(columns={"RANK": "BL_RANK"}),
            on="PLAYER_KEY", how="inner",
        ).dropna(subset=["RANK", "BL_RANK", "ACTUAL_PG_RANK"])
        if len(aligned_pg) >= 20:
            result["per_game"] = paired_bootstrap_rho(
                aligned_pg["RANK"].values,
                aligned_pg["BL_RANK"].values,
                aligned_pg["ACTUAL_PG_RANK"].values,
            )

        if result:
            bootstrap[bl_name] = result

    return bootstrap


# ── Run one fold ──────────────────────────────────────────────────────────────

def run_fold(target: str) -> dict:
    """Run the projection for one fold and score it."""
    import pickle

    cfg = fold_config(target)
    print(f"\n{'='*60}")
    print(f"Fold: target={target}  tuned={'yes' if cfg['_tuned'] else 'no'}  "
          f"injuries={'on' if cfg['_fetch_injuries'] else 'off'}")
    print(f"  Inputs: {', '.join(cfg['game_log_seasons'])}")
    print(f"{'='*60}")

    result = run_projection(cfg, use_rosters=False,
                            fetch_injuries=cfg["_fetch_injuries"])
    rankings = result["rankings"]
    league_tau = result["league_tau"]

    # Load DD/TD from the projection's game-log cache (already on disk)
    cache_path = Path(cfg["game_log_cache"])
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cache_data = pickle.load(f)
        proj_game_logs = cache_data.get("payload", cache_data) if isinstance(cache_data, dict) else cache_data
        proj_derived = derive_stats_from_logs(proj_game_logs)
        derived_by_key = {canonical_player_key(n): v for n, v in proj_derived.items()}
    else:
        derived_by_key = {}

    # Report pooled players with no game logs in any input season
    no_logs = []
    for _, row in rankings.iterrows():
        pkey = canonical_player_key(row["PLAYER_NAME"])
        if pkey not in derived_by_key:
            no_logs.append(row["PLAYER_NAME"])
    if no_logs:
        print(f"  Pooled players with no game logs ({len(no_logs)}): "
              + ", ".join(no_logs[:10])
              + ("..." if len(no_logs) > 10 else ""))

    print(f"  Projected {len(rankings)} players, scoring against {target} actuals...")

    actuals = build_actuals(
        target, rankings["PLAYER_NAME"].tolist(), league_tau, cfg,
    )

    model_keys = set(rankings["PLAYER_NAME"].apply(canonical_player_key))

    persist = persistence_baseline(target, derived_by_key=derived_by_key,
                                   projected_keys=model_keys)
    marcel = marcel_lite_baseline(target, derived_by_key=derived_by_key,
                                  projected_keys=model_keys)

    # Common set: model ∩ persist ∩ marcel (persistence now includes zero-GP
    # rows for projected players with no T-1 data, so drops are rarer)
    persist_keys = set(persist["PLAYER_NAME"].apply(canonical_player_key)) if not persist.empty else model_keys
    marcel_keys = set(marcel["PLAYER_NAME"].apply(canonical_player_key)) if not marcel.empty else model_keys
    common_keys = model_keys & persist_keys & marcel_keys

    # Report drops
    dropped = model_keys - common_keys
    if dropped:
        rank_lookup = dict(zip(
            rankings["PLAYER_NAME"].apply(canonical_player_key),
            rankings["RANK"],
        ))
        drop_info = sorted(
            [(k, rank_lookup.get(k, 999)) for k in dropped],
            key=lambda x: x[1],
        )
        print(f"  Dropped from common set ({len(dropped)}): "
              + ", ".join(f"{k}(#{int(r)})" for k, r in drop_info))

    common_actuals = actuals[actuals["PLAYER_KEY"].isin(common_keys)].copy()
    print(f"  Common player set: {len(common_keys)} "
          f"(model={len(model_keys)}, persist={len(persist_keys)}, marcel={len(marcel_keys)})")

    # Count under-20-GP players and their mean model rank
    under20 = actuals[
        (actuals["PLAYER_KEY"].isin(common_keys)) & (actuals["ACTUAL_GP"] < MIN_GP_FOR_TARGET)
    ]
    rank_lookup = dict(zip(
        rankings["PLAYER_NAME"].apply(canonical_player_key), rankings["RANK"],
    ))
    under20_ranks = [rank_lookup.get(k, np.nan) for k in under20["PLAYER_KEY"]]
    n_under20 = len(under20)
    mean_under20_rank = float(np.nanmean(under20_ranks)) if under20_ranks else 0.0

    model_metrics = compute_fold_metrics(rankings, common_actuals, league_tau, cfg, method="model")
    persist_metrics = score_baseline(persist, common_actuals, league_tau, cfg,
                                     "persistence", target=target)
    marcel_metrics = score_baseline(marcel, common_actuals, league_tau, cfg,
                                    "marcel_lite", target=target)

    bootstrap = _compute_bootstrap(
        rankings, persist, marcel, common_actuals, common_keys,
        league_tau, cfg, target=target,
    )

    return {
        "target": target,
        "tuned": cfg["_tuned"],
        "injuries": cfg["_fetch_injuries"],
        "n_projected": len(rankings),
        "n_actual": len(actuals),
        "n_actual_qualified": int((actuals["ACTUAL_GP"] >= MIN_GP_FOR_TARGET).sum()),
        "n_under20_gp": n_under20,
        "mean_under20_rank": round(mean_under20_rank, 1),
        "model": model_metrics,
        "persistence": persist_metrics,
        "marcel_lite": marcel_metrics,
        "bootstrap": bootstrap,
        "fold_details": _build_fold_details(rankings, actuals),
    }


def _build_fold_details(rankings: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """One row per player: projected and actual line, values, ranks."""
    proj = rankings.copy()
    proj["PLAYER_KEY"] = proj["PLAYER_NAME"].apply(canonical_player_key)
    merged = actuals.merge(
        proj[["PLAYER_KEY", "PLAYER_NAME", "RANK", "TOTAL_VALUE"] +
             [c for c in proj.columns if c.endswith("_RATE")]],
        on="PLAYER_KEY", how="outer", suffixes=("_actual", "_proj"),
    )
    return merged


# ── Output ────────────────────────────────────────────────────────────────────

def print_fold_summary(fold_result: dict) -> None:
    t = fold_result["target"]
    tag = "untouched" if not fold_result["tuned"] else "tuned-era"
    inj = "injuries=on" if fold_result["injuries"] else "injuries=off"

    n_u20 = fold_result.get("n_under20_gp", 0)
    mean_u20 = fold_result.get("mean_under20_rank", 0)

    print(f"\n  {t} [{tag}, {inj}]  "
          f"projected={fold_result['n_projected']}  "
          f"actual_qualified={fold_result['n_actual_qualified']}  "
          f"under20gp={n_u20}(mean_rank={mean_u20:.0f})")

    for method in ("model", "persistence", "marcel_lite"):
        m = fold_result[method]
        if m.get("n_players", 0) == 0:
            print(f"    {method:<14s}  (no data)")
            continue
        parts = [f"n={m['n_players']}"]
        if "spearman_per_game" in m:
            parts.append(f"rho_pg={m['spearman_per_game']:.3f}")
        if "spearman_total" in m:
            parts.append(f"rho_total={m['spearman_total']:.3f}")
        if "top50_capture" in m:
            parts.append(f"top50={m['top50_capture']:.0%}")
        if "gp_mae" in m:
            parts.append(f"gp_mae={m['gp_mae']:.1f}")
        print(f"    {method:<14s}  {'  '.join(parts)}")

    bootstrap = fold_result.get("bootstrap", {})
    for bl_name, bs in bootstrap.items():
        for metric_key, label in [("total", "total"), ("per_game", "pg")]:
            if metric_key in bs:
                bm = bs[metric_key]
                print(f"    bootstrap_{label} model vs {bl_name}: "
                      f"delta={bm['mean_delta']:+.4f}  "
                      f"95%CI=[{bm['ci_lo']:+.4f}, {bm['ci_hi']:+.4f}]  "
                      f"P(model wins)={bm['p_a_wins']:.1%}")


def save_fold_results(fold_results: list[dict], name: str) -> None:
    out_dir = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for fr in fold_results:
        for method in ("model", "persistence", "marcel_lite"):
            m = fr[method]
            row = {"target": fr["target"], "tuned": fr["tuned"], "method": method}
            for k, v in m.items():
                if k not in ("method", "category_metrics", "age_bias"):
                    row[k] = v
            summary_rows.append(row)

        details = fr.get("fold_details")
        if details is not None and len(details) > 0:
            details.to_csv(out_dir / f"fold_{_season_slug(fr['target'])}.csv", index=False)

    pd.DataFrame(summary_rows).to_csv(out_dir / "summary.csv", index=False)
    print(f"\n  Saved to {out_dir}/")


def compare_runs(before_name: str, after_name: str) -> None:
    before_path = OUTPUT_DIR / before_name / "summary.csv"
    after_path = OUTPUT_DIR / after_name / "summary.csv"
    if not before_path.exists() or not after_path.exists():
        print(f"Missing summary: {before_path} or {after_path}")
        return

    before = pd.read_csv(before_path)
    after = pd.read_csv(after_path)

    merged = before.merge(after, on=["target", "method"], suffixes=("_before", "_after"))

    print(f"\n{'='*60}")
    print(f"Compare: {before_name} → {after_name}")
    print(f"{'='*60}")

    for _, row in merged.iterrows():
        parts = [f"{row['target']} {row['method']:<14s}"]
        for metric in ("spearman_total", "spearman_per_game", "gp_mae", "top50_capture"):
            b_col = f"{metric}_before"
            a_col = f"{metric}_after"
            if b_col in row.index and a_col in row.index:
                b, a = row[b_col], row[a_col]
                if pd.notna(b) and pd.notna(a):
                    delta = a - b
                    sign = "+" if delta >= 0 else ""
                    parts.append(f"{metric}={sign}{delta:.3f}")
        print("  " + "  ".join(parts))


# ── Holdout guard ─────────────────────────────────────────────────────────────

HOLDOUT_LOG = OUTPUT_DIR / "holdout_access.log"


def log_holdout_access(target: str) -> None:
    HOLDOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(HOLDOUT_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} unsealed {target}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest harness")
    parser.add_argument("--target", type=str, help="Run one fold only")
    parser.add_argument("--save-as", type=str, help="Name for this run's output")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="Compare two saved runs")
    parser.add_argument("--unseal-holdout", action="store_true",
                        help="Allow scoring the 2026-27 holdout fold")
    args = parser.parse_args()

    if args.compare:
        compare_runs(args.compare[0], args.compare[1])
        return

    if args.target:
        targets = [args.target]
        if args.target not in FOLDS:
            print(f"Unknown target: {args.target}")
            print(f"Available: {', '.join(FOLDS.keys())}")
            sys.exit(1)
        if FOLDS[args.target].get("holdout") and not args.unseal_holdout:
            print(f"Target {args.target} is a holdout. Pass --unseal-holdout to score it.")
            sys.exit(1)
        if FOLDS[args.target].get("holdout") and args.unseal_holdout:
            log_holdout_access(args.target)
    else:
        targets = scorable_folds()
        if not targets:
            print("No scorable folds — input BBR files are missing.")
            print("Need BBR season-total CSVs for older seasons. See the design spec.")
            sys.exit(0)

    print(f"Walk-forward backtest: {len(targets)} fold(s)")
    print(f"Targets: {', '.join(targets)}")

    fold_results = []
    for target in targets:
        try:
            result = run_fold(target)
            fold_results.append(result)
            print_fold_summary(result)
        except FileNotFoundError as e:
            print(f"\n  [skip] {target}: {e}")
        except Exception as e:
            print(f"\n  [error] {target}: {e.__class__.__name__}: {e}")

    if fold_results:
        # Aggregate: untouched vs tuned-era
        untouched = [r for r in fold_results if not r["tuned"]]
        tuned = [r for r in fold_results if r["tuned"]]

        if untouched:
            print(f"\n  Untouched aggregate ({len(untouched)} folds):")
            _print_aggregate(untouched)
        if tuned:
            print(f"\n  Tuned-era aggregate ({len(tuned)} folds):")
            _print_aggregate(tuned)

        name = args.save_as or datetime.now().strftime("%Y%m%d_%H%M%S")
        save_fold_results(fold_results, name)


def _print_aggregate(results: list[dict]) -> None:
    for method in ("model", "persistence", "marcel_lite"):
        rhos = [r[method].get("spearman_total") for r in results
                if r[method].get("spearman_total") is not None]
        caps = [r[method].get("top50_capture") for r in results
                if r[method].get("top50_capture") is not None]
        if rhos:
            print(f"    {method:<14s}  mean_rho_total={np.mean(rhos):.3f}  "
                  f"mean_top50={np.mean(caps):.0%}" if caps else "")


if __name__ == "__main__":
    main()
