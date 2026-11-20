"""
scripts/rookie_measurement.py -- walk-forward check of rookie placement
=========================================================================
For each backtest fold T (2021-22 .. 2025-26) it replays what main.py does
for the 2026-27 board, using only data available before T:

  1. veteran projection from the fold's three input seasons (run_projection)
  2. rookie model fitted on the three draft classes before T's class, their
     rookie seasons read from the Basketball Reference files on disk
  3. T's first-round picks placed with main.place_rookies, ranked on one
     BOARD_RANK with the veterans, then main.add_market_blend (market first
     for rookies) when that season's Yahoo ADP file exists
  4. everyone scored against T's actual results (backtest.build_actuals)

Rookie rank error = predicted rank - actual rank (positive = placed too low).
Headline numbers exclude 2024-25: its ADP file is from an April 2025 page.
Also reports the rookie GP rule (gp_shrink 0 / 0.5 / 1) and error by pick
bucket. Per-rookie rows go to diagnostics/rookie_measurement.csv.

Run: python scripts/rookie_measurement.py   (--report: re-print from the CSV)
"""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backtest import _bbr_filename, build_actuals, fold_config, scorable_folds  # noqa: E402
from data import fetch_combine_stats, fetch_draft_history, load_bbr_csv  # noqa: E402
from identity import canonical_player_key  # noqa: E402
from main import add_market_blend, place_rookies, run_projection  # noqa: E402
from rookie_baseline import (  # noqa: E402
    CATEGORIES, build_rookie_rows, extract_combine_features, fit_final_model,
    run_leave_one_class_out_cv,
)

DRAFT_YEARS = [str(y) for y in range(2018, 2026)]
CONTAMINATED = {"2024-25"}
GP_SHRINKS = (0.0, 0.5, 1.0)
OUT_FILE = REPO_ROOT / "diagnostics" / "rookie_measurement.csv"


def _season(draft_year: int) -> str:
    return f"{draft_year}-{(draft_year + 1) % 100:02d}"


def training_rows(year: int, draft_history: dict, combine: dict) -> list[dict]:
    """A draft class's real rookie seasons, from that season's BBR file."""
    bbr = load_bbr_csv(_bbr_filename(_season(year)))
    by_key = {canonical_player_key(n): r for n, r in bbr.set_index("PLAYER_NAME").iterrows()}
    rows = []
    for name, info in draft_history.items():
        row = by_key.get(canonical_player_key(name))
        if info["draft_year"] != str(year) or row is None or not row["GP"]:
            continue
        actual = {c: float(row[c]) for c in CATEGORIES}
        if any(np.isnan(v) for v in actual.values()):
            continue
        raw = combine.get(canonical_player_key(name))
        rows.append({"player_name": name, "overall_pick": info["overall_pick"], "actual": actual,
                     "combine_features": extract_combine_features(raw) if raw is not None else None})
    return rows


def run_fold(target: str, draft_history: dict, combine: dict) -> pd.DataFrame:
    year = int(target[:4])
    rows_by_class = {str(y): training_rows(y, draft_history, combine) for y in range(year - 3, year)}
    stage1, stage2 = fit_final_model(rows_by_class, run_leave_one_class_out_cv(rows_by_class))
    fitted = {"categories": CATEGORIES, "stage1": stage1, "stage2": stage2}

    cfg = fold_config(target)
    result = run_projection(cfg, use_rosters=False, fetch_injuries=cfg["_fetch_injuries"])
    rankings, projected = result["rankings"], result["projected"]
    klass = {n: i for n, i in draft_history.items() if i["draft_year"] == str(year)}
    rookie_rows = build_rookie_rows(klass, combine, fitted, set(projected["PLAYER_NAME"]))
    rookie_rows = rookie_rows[rookie_rows["OVERALL_PICK"] <= 30]

    boards = {}
    for shrink in GP_SHRINKS:
        c = copy.deepcopy(cfg)
        c["regression"] = {**(c.get("regression") or {}), "gp_shrink": shrink}
        placed = place_rookies(rookie_rows, projected, result["player_tau"], result["league_tau"], c)
        board = pd.concat([rankings.assign(ROOKIE=False), placed.assign(ROOKIE=True)], ignore_index=True)
        board["BOARD_RANK"] = board["TOTAL_VALUE"].rank(ascending=False, method="min")
        boards[shrink] = board
    out = boards[cfg["regression"]["gp_shrink"]]
    out = add_market_blend(out, f"yahoo_{target[2:4]}_{target[5:]}_adp_hashtag.csv",
                           rank_col="BOARD_RANK", market_first=out["ROOKIE"])
    for shrink, board in boards.items():
        out[f"BOARD_RANK_GP{shrink}"] = out["PLAYER_NAME"].map(board.set_index("PLAYER_NAME")["BOARD_RANK"])

    actuals = build_actuals(target, out["PLAYER_NAME"].tolist(), result["league_tau"], cfg)
    out["PLAYER_KEY"] = out["PLAYER_NAME"].map(canonical_player_key)
    out = out.merge(actuals[["PLAYER_KEY", "ACTUAL_GP", "ACTUAL_PG_RANK", "ACTUAL_TOTAL_RANK"]],
                    on="PLAYER_KEY", how="left")
    if "BLEND_RANK" not in out:
        out["MARKET_ADP"] = np.nan
        out["MARKET_RANK"] = np.nan
        out["BLEND_RANK"] = out["BOARD_RANK"]
    out["FOLD"] = target
    out["PRED_GP"] = out["PLAYER_NAME"].map(rookie_rows.set_index("PLAYER_NAME")["GP"])
    return out[["FOLD", "PLAYER_NAME", "ROOKIE", "AGE", "OVERALL_PICK", "PRED_GP", "ACTUAL_GP", "MARKET_ADP",
                    "BOARD_RANK", "MARKET_RANK", "BLEND_RANK",
                    *[f"BOARD_RANK_GP{s}" for s in GP_SHRINKS],
                    "ACTUAL_PG_RANK", "ACTUAL_TOTAL_RANK"]]


def _err(df: pd.DataFrame, pred: str, actual: str) -> str:
    d = df.dropna(subset=[pred, actual])
    if len(d) < 3:
        return f"{'n<3':>24}"
    e = d[pred] - d[actual]
    rho = spearmanr(d[pred], d[actual])[0]
    return f"{e.abs().mean():6.1f} {e.mean():+6.1f} {rho:6.3f} {len(d):4d}"


def matched_gap(rows: pd.DataFrame, rookies: pd.Series, actual: str, reps: int = 1000) -> str:
    """Mean of (actual rank - the rank a veteran placed at the same BOARD_RANK
    finishes) over the selected rookies, with a 95% bootstrap interval
    (players resampled within fold). The veteran line is a straight fit of
    actual on BOARD_RANK over veterans placed 40th or lower. Negative =
    rookies finish better than veterans placed alongside them. Raw signed
    rank error can't show this: anyone placed near the bottom can only miss
    upward (docs/research/2026-11-21-rookie-undervaluation.md)."""
    d = rows.assign(_SEL=rookies).dropna(subset=[actual])

    def gap(x: pd.DataFrame) -> float:
        v = x[~x["ROOKIE"] & (x["BOARD_RANK"] >= 40)]
        slope, icept = np.polyfit(v["BOARD_RANK"], v[actual], 1)
        r = x[x["_SEL"]]
        return float((r[actual] - (icept + slope * r["BOARD_RANK"])).mean())

    rng = np.random.default_rng(42)
    boot = [gap(d.groupby("FOLD").sample(frac=1, replace=True, random_state=rng)) for _ in range(reps)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return f"{gap(d):+6.1f}  [{lo:+.1f}, {hi:+.1f}]  n={int(d['_SEL'].sum())}"


def report(all_rows: pd.DataFrame) -> None:
    vets = all_rows[~all_rows["ROOKIE"]]
    print("\n== Veterans by age at projection, model vs ACTUAL_TOTAL_RANK (all folds) ==")
    print(f"{'':28s}{'MARE':>6} {'signed':>6} {'rho':>6} {'n':>4}")
    for lo, hi in ((0, 22), (23, 24), (25, 27), (28, 30), (31, 33), (34, 99)):
        b = vets[vets["AGE"].between(lo, hi)]
        print(f"{f'  age {lo}-{hi}':28s}{_err(b, 'BOARD_RANK', 'ACTUAL_TOTAL_RANK')}")
    for label, rows in (("Headline (excl 2024-25)", all_rows[~all_rows["FOLD"].isin(CONTAMINATED)]),
                        ("All folds", all_rows)):
        print(f"\n== Matched gap, {label}: rookie actual rank minus a same-placed veteran's ==")
        for actual in ("ACTUAL_TOTAL_RANK", "ACTUAL_PG_RANK"):
            for lo, hi in ((1, 5), (6, 30), (1, 30)):
                sel = rows["ROOKIE"] & rows["OVERALL_PICK"].between(lo, hi)
                print(f"  {actual:18s} picks {lo:2d}-{hi:2d}  {matched_gap(rows, sel, actual)}")
    df = all_rows[all_rows["ROOKIE"]]
    head = df[~df["FOLD"].isin(CONTAMINATED)]
    hdr = f"{'':28s}{'MARE':>6} {'signed':>6} {'rho':>6} {'n':>4}"
    for label, d in (("Headline (excl 2024-25)", head), ("All folds", df)):
        print(f"\n== {label} ==")
        for actual in ("ACTUAL_TOTAL_RANK", "ACTUAL_PG_RANK"):
            print(f"-- vs {actual}\n{hdr}")
            print(f"{'model (BOARD_RANK)':28s}{_err(d, 'BOARD_RANK', actual)}")
            print(f"{'final (BLEND_RANK)':28s}{_err(d, 'BLEND_RANK', actual)}")
            priced = d[d["MARKET_ADP"].notna()]
            print(f"{'  priced only: model':28s}{_err(priced, 'BOARD_RANK', actual)}")
            print(f"{'  priced only: market':28s}{_err(priced, 'MARKET_RANK', actual)}")
        print(f"-- GP rule (rookie gp_shrink) vs ACTUAL_TOTAL_RANK\n{hdr}")
        for s in GP_SHRINKS:
            print(f"{'  gp_shrink ' + str(s):28s}{_err(d, f'BOARD_RANK_GP{s}', 'ACTUAL_TOTAL_RANK')}")
        print(f"-- model by pick bucket vs ACTUAL_TOTAL_RANK\n{hdr}")
        for lo, hi in ((1, 5), (6, 14), (15, 30)):
            b = d[d["OVERALL_PICK"].between(lo, hi)]
            print(f"{f'  picks {lo}-{hi}':28s}{_err(b, 'BOARD_RANK', 'ACTUAL_TOTAL_RANK')}")
        gp = d.dropna(subset=["PRED_GP"])
        print(f"GP: predicted mean {gp['PRED_GP'].mean():.1f}, actual mean {gp['ACTUAL_GP'].mean():.1f}, "
              f"MAE {(gp['PRED_GP'] - gp['ACTUAL_GP']).abs().mean():.1f}")


def main() -> None:
    if "--report" in sys.argv:  # re-print from the saved CSV without rerunning the folds
        report(pd.read_csv(OUT_FILE))
        return
    draft_history = fetch_draft_history(DRAFT_YEARS, str(REPO_ROOT / "draft_history_walkforward_cache.pkl"))
    combine = fetch_combine_stats(str(REPO_ROOT / "combine_stats_cache.pkl"))
    df = pd.concat([run_fold(t, draft_history, combine) for t in scorable_folds()], ignore_index=True)
    df.to_csv(OUT_FILE, index=False)
    print(f"\nWrote {OUT_FILE} ({len(df)} rows, {int(df['ROOKIE'].sum())} rookies)")
    report(df)


if __name__ == "__main__":
    main()
