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

import pandas as pd
from pathlib import Path


def validate(df: pd.DataFrame,
             known_csv: str,
             name_col: str = "Player Name",
             rank_col: str = "Rank",
             top_n_misses: int = 10) -> dict:
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

    known = pd.read_csv(known_csv)[[name_col, rank_col]].rename(
        columns={name_col: "PLAYER_NAME", rank_col: "ACTUAL_RANK"}
    )
    merged = pd.merge(df[["PLAYER_NAME", "RANK"]], known, on="PLAYER_NAME")

    if merged.empty:
        print("No matching players found for validation.")
        return {}

    corr, _  = spearmanr(merged["RANK"], merged["ACTUAL_RANK"])
    delta    = merged["RANK"] - merged["ACTUAL_RANK"]
    hit_rate = (delta.abs() <= 5).mean() * 100
    mae      = delta.abs().mean()

    print(f"\n{'='*60}")
    print(f"Validation vs {Path(known_csv).name}")
    print(f"  Note: 14-cat model vs 9-cat actual — directional comparison only")
    print(f"{'='*60}")
    print(f"  Players matched : {len(merged)}")
    print(f"  Spearman r      : {corr:.3f}  (1.0 = perfect, 0 = random)")
    print(f"  Hit rate (±5)   : {hit_rate:.1f}%")
    print(f"  MAE             : {mae:.1f} ranks")

    merged["delta"] = delta
    top_misses = merged.sort_values("delta", key=abs, ascending=False).head(top_n_misses)

    print(f"\n  Biggest misses:")
    for _, row in top_misses.iterrows():
        arrow = "↑" if row["delta"] < 0 else "↓"
        print(f"    {row['PLAYER_NAME']:<28} "
              f"ours={int(row['RANK']):>3}  "
              f"actual={int(row['ACTUAL_RANK']):>3}  "
              f"{arrow}{abs(int(row['delta']))}")

    return {
        "spearman": corr,
        "hit_rate": hit_rate,
        "mae":      mae,
        "details":  merged,
    }