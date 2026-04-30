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
import numpy as np
from pathlib import Path

from identity import canonical_player_key, normalize_player_name


BENCHMARK_HISTORY_COLUMNS = [
    "recorded_at",
    "label",
    "benchmark_class",
    "trust_tier",
    "status",
    "matched_players",
    "spearman",
    "hit_rate",
    "mae",
]

MISS_CONTEXT_COLUMNS = [
    "GP_FACTOR",
    "PTS",
    "REB",
    "AST",
    "DD",
    "TD",
    "TECH",
    "TOTAL_VALUE",
]

MISS_OUTPUT_COLUMNS = [
    "PLAYER_NAME",
    "RANK",
    "ACTUAL_RANK",
    "delta",
    "MISS_BUCKET",
] + MISS_CONTEXT_COLUMNS


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


def load_benchmark_history(path: str | Path) -> pd.DataFrame:
    """Load benchmark history CSV if present, otherwise return an empty frame."""
    history_path = Path(path)
    if not history_path.exists():
        return pd.DataFrame(columns=BENCHMARK_HISTORY_COLUMNS)
    history = pd.read_csv(history_path)
    for col in BENCHMARK_HISTORY_COLUMNS:
        if col not in history.columns:
            history[col] = pd.NA
    return history[BENCHMARK_HISTORY_COLUMNS].copy()


def append_benchmark_history(path: str | Path, rows: list[dict]) -> None:
    """Append benchmark summary rows to the persisted history CSV."""
    if not rows:
        return
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = load_benchmark_history(history_path)
    new_rows = pd.DataFrame(rows)
    updated = new_rows if history.empty else pd.concat([history, new_rows], ignore_index=True)
    updated.to_csv(history_path, index=False)


def find_previous_baseline(history: pd.DataFrame,
                           label: str,
                           benchmark_class: str | None = None,
                           trust_tier: str | None = None) -> dict | None:
    """Return the most recent saved baseline for the same benchmark target."""
    if history.empty:
        return None

    matches = history[history["label"] == label].copy()
    if benchmark_class is not None:
        matches = matches[matches["benchmark_class"] == benchmark_class]
    if trust_tier is not None:
        matches = matches[matches["trust_tier"] == trust_tier]

    if matches.empty:
        return None

    matches = matches.sort_values("recorded_at")
    return matches.iloc[-1].to_dict()


def build_validation_summary_row(result: dict,
                                 recorded_at: str) -> dict[str, object]:
    """Serialize a validation result to one persisted benchmark summary row."""
    return {
        "recorded_at": recorded_at,
        "label": result.get("label"),
        "benchmark_class": result.get("benchmark_class"),
        "trust_tier": result.get("trust_tier"),
        "status": result.get("status"),
        "matched_players": result.get("matched_players"),
        "spearman": result.get("spearman"),
        "hit_rate": result.get("hit_rate"),
        "mae": result.get("mae"),
    }


def _delta(current: float | int | None,
           previous: float | int | None) -> float | None:
    if current is None or previous is None:
        return None
    if pd.isna(current) or pd.isna(previous):
        return None
    return float(current) - float(previous)


def compute_metric_deltas(current_result: dict,
                          previous_baseline: dict | None) -> dict[str, float] | None:
    """Compare current validation metrics to the previous saved baseline."""
    if previous_baseline is None:
        return None
    return {
        "matched_players": _delta(current_result.get("matched_players"), previous_baseline.get("matched_players")),
        "spearman": _delta(current_result.get("spearman"), previous_baseline.get("spearman")),
        "hit_rate": _delta(current_result.get("hit_rate"), previous_baseline.get("hit_rate")),
        "mae": _delta(current_result.get("mae"), previous_baseline.get("mae")),
    }


def print_metric_deltas(deltas: dict[str, float] | None) -> None:
    """Render a compact benchmark delta summary."""
    if not deltas:
        return

    def fmt(name: str, value: float | None, decimals: int = 1) -> str:
        if value is None:
            return f"{name} n/a"
        sign = "+" if value > 0 else ""
        return f"{name} {sign}{value:.{decimals}f}"

    print("\n  Baseline delta:")
    print(f"    {fmt('matched', deltas.get('matched_players'), 0)}")
    print(f"    {fmt('spearman', deltas.get('spearman'), 3)}")
    print(f"    {fmt('hit_rate', deltas.get('hit_rate'), 1)}")
    print(f"    {fmt('mae', deltas.get('mae'), 1)}")


def classify_miss_bucket(row: pd.Series) -> str:
    """Assign a compact, deterministic heuristic bucket to a miss row."""
    delta = float(row.get("delta", 0.0))
    gp_factor = pd.to_numeric(pd.Series([row.get("GP_FACTOR")]), errors="coerce").iloc[0]
    dd = pd.to_numeric(pd.Series([row.get("DD")]), errors="coerce").iloc[0]
    td = pd.to_numeric(pd.Series([row.get("TD")]), errors="coerce").iloc[0]
    tech = pd.to_numeric(pd.Series([row.get("TECH")]), errors="coerce").iloc[0]

    if delta <= -15 and pd.notna(gp_factor) and gp_factor < 0.78:
        return "availability miss"
    if abs(delta) >= 15 and (
        (pd.notna(dd) and dd >= 0.35)
        or (pd.notna(td) and td >= 0.05)
        or (pd.notna(tech) and tech >= 0.03)
    ):
        return "category-weight distortion"
    if delta >= 15 and (pd.isna(gp_factor) or gp_factor >= 0.78):
        return "breakout/role growth"
    if delta <= -15 and (pd.isna(gp_factor) or gp_factor >= 0.78):
        return "aging/decline"
    return "unclear/other"


def build_top_miss_artifact(result: dict,
                            top_n: int = 10) -> pd.DataFrame:
    """Build a compact saved miss artifact from a validation result."""
    details = result.get("details")
    if details is None or len(details) == 0:
        return pd.DataFrame(columns=MISS_OUTPUT_COLUMNS)

    details = details.copy()
    if "delta" not in details.columns:
        details["delta"] = details["RANK"] - details["ACTUAL_RANK"]
    details["MISS_BUCKET"] = details.apply(classify_miss_bucket, axis=1)
    top_misses = details.sort_values("delta", key=abs, ascending=False).head(top_n).copy()

    for col in MISS_CONTEXT_COLUMNS:
        if col not in top_misses.columns:
            top_misses[col] = pd.NA

    return top_misses[MISS_OUTPUT_COLUMNS].reset_index(drop=True)


def summarize_miss_buckets(miss_df: pd.DataFrame) -> pd.Series:
    """Return bucket counts for a saved or computed miss artifact."""
    if miss_df.empty or "MISS_BUCKET" not in miss_df.columns:
        return pd.Series(dtype="int64")
    return miss_df["MISS_BUCKET"].value_counts()


def validate(df: pd.DataFrame,
             known_csv: str,
             name_col: str | list[str] = "Player Name",
             rank_col: str = "Rank",
             rank_from_metric: bool = False,
             rank_metric_ascending: bool = True,
             top_n_misses: int = 10,
             min_matched_players: int = 10,
             label: str | None = None,
             note: str | None = None,
             benchmark_class: str | None = None,
             trust_tier: str | None = None) -> dict:
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

    context_cols = [col for col in MISS_CONTEXT_COLUMNS if col in df.columns]
    predicted = df[["PLAYER_NAME", "RANK"] + context_cols].copy()
    predicted["PLAYER_KEY"] = predicted["PLAYER_NAME"].map(canonical_player_key)

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
    known["PLAYER_KEY"] = known["ACTUAL_PLAYER_NAME"].map(canonical_player_key)

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
        "benchmark_class": benchmark_class,
        "trust_tier": trust_tier,
        "top_misses": pd.DataFrame(columns=MISS_OUTPUT_COLUMNS),
    }

    print(f"\n{'='*60}")
    print(f"Validation vs {label or Path(known_csv).name}")
    if note:
        print(f"  Note: {note}")
    if benchmark_class:
        print(f"  Benchmark class : {benchmark_class}")
    if trust_tier:
        print(f"  Trust tier      : {trust_tier}")
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
    top_misses = build_top_miss_artifact({"details": merged}, top_n=top_n_misses)
    result["top_misses"] = top_misses

    print(f"\n  Biggest misses:")
    for _, row in top_misses.iterrows():
        arrow = "↑" if row["delta"] < 0 else "↓"
        print(f"    {row['PLAYER_NAME']:<28} "
              f"ours={int(row['RANK']):>3}  "
              f"actual={int(row['ACTUAL_RANK']):>3}  "
              f"{arrow}{abs(int(row['delta']))}")

    bucket_counts = summarize_miss_buckets(top_misses)
    if not bucket_counts.empty:
        print("\n  Miss buckets:")
        for bucket, count in bucket_counts.items():
            print(f"    {bucket:<24} {count}")

    return result
