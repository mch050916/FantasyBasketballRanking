"""
validate.py — Validation against known rankings
=================================================
Compares our projected rankings to a ground-truth CSV.

Metrics:
  - Spearman correlation: 1.0 = perfect rank order, 0 = random
  - Hit rate (±5): % of players ranked within 5 spots of actual
  - MAE: mean absolute rank error

Usage:
    from validate import validate
    validate(rankings_df, "actual_9cat_24_25.csv")

Note: our model scores 14 categories; the validation CSV is Yahoo's 9-cat
rankings. This means the comparison is directional only — it confirms
whether our model broadly agrees on player value, not exact rank matching.
"""

import re
import unicodedata
import pandas as pd
import numpy as np
from pathlib import Path


def normalize_player_name(name: str) -> str:
    """Normalize player names so minor formatting/accent differences still match."""
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def build_player_name(df: pd.DataFrame, name_col: str | list[str]) -> pd.Series:
    """Build a comparable player-name column from one or more source columns."""
    if isinstance(name_col, str):
        return df[name_col].fillna("").astype(str).str.strip()

    parts = [df[col].fillna("").astype(str).str.strip() for col in name_col]
    combined = parts[0]
    for part in parts[1:]:
        combined = combined.str.cat(part, sep=" ")
    return combined.str.replace(r"\s+", " ", regex=True).str.strip()


def build_rank_series(df: pd.DataFrame,
                      rank_col: str,
                      rank_from_metric: bool = False,
                      ascending: bool = True) -> pd.Series:
    """Return a comparable rank series from either explicit ranks or a sortable metric."""
    series = pd.to_numeric(df[rank_col], errors="coerce")
    if not rank_from_metric:
        return series
    return series.rank(method="first", ascending=ascending)


def validate(df: pd.DataFrame,
             known_csv: str,
             name_col: str | list[str] = "Player Name",
             rank_col: str = "Rank",
             rank_from_metric: bool = False,
             rank_metric_ascending: bool = True,
             top_n_misses: int = 10,
             min_matched_players: int = 10,
             label: str | None = None,
             note: str | None = None) -> dict:
    """
    Compare our rankings to a ground-truth CSV.

    Parameters
    ----------
    df          : our rankings DataFrame (must have PLAYER_NAME and RANK columns)
    known_csv   : path to a CSV with player names and their actual ranks
    name_col    : column name for player names in the known CSV
    rank_col    : column name for actual ranks in the known CSV
    top_n_misses: how many biggest misses to print

    Returns
    -------
    dict with keys: spearman, hit_rate, mae, details (DataFrame)
    """
    from scipy.stats import spearmanr

    predicted = df[["PLAYER_NAME", "RANK"]].copy()
    predicted["PLAYER_KEY"] = predicted["PLAYER_NAME"].map(normalize_player_name)

    known_df = pd.read_csv(known_csv)
    required_cols = [rank_col] + ([name_col] if isinstance(name_col, str) else list(name_col))
    known = known_df[required_cols].copy()
    known["ACTUAL_PLAYER_NAME"] = build_player_name(known, name_col)
    known["ACTUAL_RANK"] = build_rank_series(
        known,
        rank_col,
        rank_from_metric=rank_from_metric,
        ascending=rank_metric_ascending,
    )
    known = known[["ACTUAL_PLAYER_NAME", "ACTUAL_RANK"]].dropna(subset=["ACTUAL_RANK"])
    known["PLAYER_KEY"] = known["ACTUAL_PLAYER_NAME"].map(normalize_player_name)

    merged = pd.merge(
        predicted,
        known,
        on="PLAYER_KEY",
        how="inner",
    )

    result = {
        "status": "no_matches",
        "spearman": None,
        "hit_rate": None,
        "mae": None,
        "matched_players": len(merged),
        "details": merged,
        "label": label or Path(known_csv).name,
    }

    print(f"\n{'='*60}")
    print(f"Validation vs {label or Path(known_csv).name}")
    if note:
        print(f"  Note: {note}")
    print(f"{'='*60}")

    if merged.empty:
        print("  Status          : no_matches")
        print("  Players matched : 0")
        print("  Validation did not produce any comparable players.")
        return result

    corr = np.nan
    if len(merged) >= 2:
        corr, _ = spearmanr(merged["RANK"], merged["ACTUAL_RANK"])
    delta    = merged["RANK"] - merged["ACTUAL_RANK"]
    hit_rate = (delta.abs() <= 5).mean() * 100
    mae      = delta.abs().mean()

    status = "ok" if len(merged) >= min_matched_players else "weak_matches"
    result.update(
        {
            "status": status,
            "spearman": corr,
            "hit_rate": hit_rate,
            "mae": mae,
            "matched_players": len(merged),
            "details": merged,
        }
    )

    print(f"  Status          : {status}")
    print(f"  Players matched : {len(merged)}")
    if np.isnan(corr):
        print("  Spearman r      : n/a  (need at least 2 matched players)")
    else:
        print(f"  Spearman r      : {corr:.3f}  (1.0 = perfect, 0 = random)")
    print(f"  Hit rate (±5)   : {hit_rate:.1f}%")
    print(f"  MAE             : {mae:.1f} ranks")
    if status == "weak_matches":
        print(f"  Warning         : matched player count is below the trust threshold ({min_matched_players})")

    merged["delta"] = delta
    top_misses = merged.sort_values("delta", key=abs, ascending=False).head(top_n_misses)

    print(f"\n  Biggest misses:")
    for _, row in top_misses.iterrows():
        arrow = "↑" if row["delta"] < 0 else "↓"
        print(f"    {row['PLAYER_NAME']:<28} "
              f"ours={int(row['RANK']):>3}  "
              f"actual={int(row['ACTUAL_RANK']):>3}  "
              f"{arrow}{abs(int(row['delta']))}")

    return result
