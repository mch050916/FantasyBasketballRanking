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

PREDICTED_CONTEXT_COLUMNS = [
    "GP_FACTOR",
    "PTS",
    "REB",
    "AST",
    "3PTM",
    "BLK",
    "TO",
    "FG%",
    "DD",
    "TD",
    "TECH",
    "TOTAL_VALUE",
    "DD_G",
    "TD_G",
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

MILESTONE_CONTRIBUTION_COLUMNS = [
    "PLAYER_NAME",
    "RANK",
    "ACTUAL_RANK",
    "delta",
    "MISS_BUCKET",
    "DD",
    "TD",
    "DD_G",
    "TD_G",
    "MILESTONE_G_SUM",
    "MILESTONE_ABS_SHARE",
    "MILESTONE_DOMINANT",
    "TOTAL_VALUE",
]

CATEGORY_DISTORTION_COLUMNS = [
    "PLAYER_NAME",
    "RANK",
    "ACTUAL_RANK",
    "delta",
    "DISTORTION_FAMILY",
    "MISS_BUCKET",
    "PTS",
    "REB",
    "AST",
    "3PTM",
    "BLK",
    "TO",
    "FG%",
    "DD",
    "TD",
    "DD_G",
    "TD_G",
    "MILESTONE_ABS_SHARE",
    "TOTAL_VALUE",
]

CATEGORY_DISTORTION_SUMMARY_COLUMNS = [
    "DISTORTION_FAMILY",
    "PRIMARY_HITS",
    "PRIMARY_BENCHMARKS",
    "PRIMARY_PLAYER_COUNT",
    "SECONDARY_HITS",
    "EVIDENCE_LEVEL",
    "FOLLOW_UP_DECISION",
    "AVG_ABS_DELTA",
    "REPRESENTATIVE_PLAYERS",
]


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


def _coerce_float(value: object) -> float | None:
    """Return a float when possible, otherwise None."""
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def classify_category_distortion_family(row: pd.Series) -> str:
    """Assign a broad, interpretable family to category-weight distortion misses."""
    milestone_share = _coerce_float(row.get("MILESTONE_ABS_SHARE")) or 0.0
    pts = _coerce_float(row.get("PTS")) or 0.0
    reb = _coerce_float(row.get("REB")) or 0.0
    ast = _coerce_float(row.get("AST")) or 0.0
    threes = _coerce_float(row.get("3PTM")) or 0.0
    blocks = _coerce_float(row.get("BLK")) or 0.0
    turnovers = _coerce_float(row.get("TO")) or 99.0
    fg_pct = _coerce_float(row.get("FG%")) or 0.0
    dd = _coerce_float(row.get("DD")) or 0.0
    td = _coerce_float(row.get("TD")) or 0.0

    if milestone_share >= 0.55 or td >= 0.08 or (dd >= 0.50 and ast >= 5.0):
        return "milestone carry"
    if reb >= 8.0 and (blocks >= 0.80 or (fg_pct >= 0.50 and ast < 5.5)):
        return "big-man stat carry"
    if ast >= 6.5 and (pts >= 16.0 or threes >= 1.80):
        return "guard creation carry"
    if fg_pct >= 0.53 and turnovers <= 2.0:
        return "efficiency carry"
    return "balanced category carry"


def _milestone_dominant_label(dd_g: float | None, td_g: float | None) -> str:
    """Return which milestone category dominates the miss contribution."""
    dd_abs = abs(float(dd_g)) if dd_g is not None and not pd.isna(dd_g) else 0.0
    td_abs = abs(float(td_g)) if td_g is not None and not pd.isna(td_g) else 0.0
    if dd_abs == 0.0 and td_abs == 0.0:
        return "none"
    if dd_abs >= td_abs * 1.25:
        return "DD"
    if td_abs >= dd_abs * 1.25:
        return "TD"
    return "mixed"


def build_milestone_contribution_artifact(result: dict,
                                          top_n: int = 10) -> pd.DataFrame:
    """Build a compact DD/TD contribution artifact from validation details."""
    details = result.get("details")
    if details is None or len(details) == 0:
        return pd.DataFrame(columns=MILESTONE_CONTRIBUTION_COLUMNS)

    artifact = details.copy()
    if "delta" not in artifact.columns:
        artifact["delta"] = artifact["RANK"] - artifact["ACTUAL_RANK"]
    if "MISS_BUCKET" not in artifact.columns:
        artifact["MISS_BUCKET"] = artifact.apply(classify_miss_bucket, axis=1)

    for col in ["DD", "TD", "DD_G", "TD_G", "TOTAL_VALUE"]:
        if col not in artifact.columns:
            artifact[col] = pd.NA
        artifact[col] = pd.to_numeric(artifact[col], errors="coerce")

    artifact["MILESTONE_G_SUM"] = artifact["DD_G"].fillna(0.0) + artifact["TD_G"].fillna(0.0)
    total_abs = artifact["TOTAL_VALUE"].abs().replace(0, np.nan)
    artifact["MILESTONE_ABS_SHARE"] = artifact["MILESTONE_G_SUM"].abs() / total_abs
    artifact["MILESTONE_DOMINANT"] = artifact.apply(
        lambda row: _milestone_dominant_label(row.get("DD_G"), row.get("TD_G")),
        axis=1,
    )

    artifact = artifact.sort_values("delta", key=abs, ascending=False).head(top_n).copy()
    return artifact[MILESTONE_CONTRIBUTION_COLUMNS].reset_index(drop=True)


def build_category_distortion_artifact(result: dict,
                                       top_n: int = 10) -> pd.DataFrame:
    """Build a compact saved artifact for family-level category distortion diagnosis."""
    details = result.get("details")
    if details is None or len(details) == 0:
        return pd.DataFrame(columns=CATEGORY_DISTORTION_COLUMNS)

    artifact = details.copy()
    if "delta" not in artifact.columns:
        artifact["delta"] = artifact["RANK"] - artifact["ACTUAL_RANK"]
    if "MISS_BUCKET" not in artifact.columns:
        artifact["MISS_BUCKET"] = artifact.apply(classify_miss_bucket, axis=1)

    for col in ["DD", "TD", "DD_G", "TD_G", "TOTAL_VALUE"]:
        if col not in artifact.columns:
            artifact[col] = pd.NA
        artifact[col] = pd.to_numeric(artifact[col], errors="coerce")

    total_abs = artifact["TOTAL_VALUE"].abs().replace(0, np.nan)
    artifact["MILESTONE_ABS_SHARE"] = (
        artifact["DD_G"].fillna(0.0) + artifact["TD_G"].fillna(0.0)
    ).abs() / total_abs

    distortion_only = artifact[artifact["MISS_BUCKET"] == "category-weight distortion"].copy()
    if distortion_only.empty:
        return pd.DataFrame(columns=CATEGORY_DISTORTION_COLUMNS)

    for col in ["PTS", "REB", "AST", "3PTM", "BLK", "TO", "FG%"]:
        if col not in distortion_only.columns:
            distortion_only[col] = pd.NA

    distortion_only["DISTORTION_FAMILY"] = distortion_only.apply(
        classify_category_distortion_family,
        axis=1,
    )
    distortion_only = distortion_only.sort_values("delta", key=abs, ascending=False).head(top_n).copy()
    return distortion_only[CATEGORY_DISTORTION_COLUMNS].reset_index(drop=True)


def summarize_category_distortion_families(artifact: pd.DataFrame) -> pd.Series:
    """Return family counts for a saved or computed category-distortion artifact."""
    if artifact.empty or "DISTORTION_FAMILY" not in artifact.columns:
        return pd.Series(dtype="int64")
    return artifact["DISTORTION_FAMILY"].value_counts()


def build_category_distortion_summary(results: list[dict[str, object]]) -> pd.DataFrame:
    """Aggregate category-distortion artifacts into one cross-benchmark summary."""
    records: list[dict[str, object]] = []
    for result in results:
        artifact = result.get("category_distortions")
        if artifact is None or len(artifact) == 0:
            continue

        artifact_df = artifact.copy()
        artifact_df["ABS_DELTA"] = artifact_df["delta"].abs()
        is_primary = (
            result.get("benchmark_class") == "historical_snapshot"
            and result.get("trust_tier") == "snapshot_derived"
        )
        label = str(result.get("label", "benchmark"))

        for family, family_df in artifact_df.groupby("DISTORTION_FAMILY"):
            records.append(
                {
                    "DISTORTION_FAMILY": family,
                    "BENCHMARK_LABEL": label,
                    "IS_PRIMARY": is_primary,
                    "HIT_COUNT": int(len(family_df)),
                    "PLAYER_NAMES": family_df["PLAYER_NAME"].astype(str).tolist(),
                    "AVG_ABS_DELTA": float(family_df["ABS_DELTA"].mean()),
                    "REPRESENTATIVE_PLAYERS": ", ".join(
                        family_df.sort_values("ABS_DELTA", ascending=False)["PLAYER_NAME"]
                        .astype(str)
                        .drop_duplicates()
                        .head(3)
                        .tolist()
                    ),
                }
            )

    if not records:
        return pd.DataFrame(columns=CATEGORY_DISTORTION_SUMMARY_COLUMNS)

    records_df = pd.DataFrame(records)
    summary_rows: list[dict[str, object]] = []
    for family, family_df in records_df.groupby("DISTORTION_FAMILY"):
        primary_df = family_df[family_df["IS_PRIMARY"]]
        secondary_df = family_df[~family_df["IS_PRIMARY"]]
        primary_benchmarks = int(primary_df["BENCHMARK_LABEL"].nunique())
        primary_hits = int(primary_df["HIT_COUNT"].sum())
        primary_player_count = int(
            primary_df["PLAYER_NAMES"].explode().dropna().astype(str).nunique()
        ) if not primary_df.empty else 0
        secondary_hits = int(secondary_df["HIT_COUNT"].sum())
        if primary_benchmarks >= 2:
            evidence_level = "repeat_exact_league"
        elif primary_hits > 0:
            evidence_level = "single_exact_league"
        else:
            evidence_level = "secondary_only"

        if evidence_level == "repeat_exact_league" and (
            primary_player_count >= 2 or primary_hits >= 4
        ):
            follow_up_decision = "active_target"
        elif evidence_level == "repeat_exact_league":
            follow_up_decision = "monitor_narrow"
        elif evidence_level == "single_exact_league":
            follow_up_decision = "watch_supporting"
        else:
            follow_up_decision = "support_only"

        representative_source = primary_df if not primary_df.empty else family_df
        representative_players = ", ".join(
            representative_source
            .sort_values("AVG_ABS_DELTA", ascending=False)["REPRESENTATIVE_PLAYERS"]
            .astype(str)
            .str.split(", ")
            .explode()
            .dropna()
            .drop_duplicates()
            .head(3)
            .tolist()
        )

        summary_rows.append(
            {
                "DISTORTION_FAMILY": family,
                "PRIMARY_HITS": primary_hits,
                "PRIMARY_BENCHMARKS": primary_benchmarks,
                "PRIMARY_PLAYER_COUNT": primary_player_count,
                "SECONDARY_HITS": secondary_hits,
                "EVIDENCE_LEVEL": evidence_level,
                "FOLLOW_UP_DECISION": follow_up_decision,
                "AVG_ABS_DELTA": float(family_df["AVG_ABS_DELTA"].mean()),
                "REPRESENTATIVE_PLAYERS": representative_players,
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values(
        ["PRIMARY_BENCHMARKS", "PRIMARY_HITS", "SECONDARY_HITS", "AVG_ABS_DELTA"],
        ascending=[False, False, False, False],
    )
    return summary[CATEGORY_DISTORTION_SUMMARY_COLUMNS].reset_index(drop=True)


def summarize_milestone_contributions(artifact: pd.DataFrame) -> dict[str, object]:
    """Return a compact DD/TD contribution summary for one benchmark artifact."""
    if artifact.empty:
        return {
            "avg_dd_g": 0.0,
            "avg_td_g": 0.0,
            "avg_share": 0.0,
            "dominant_counts": {},
        }

    dominant_counts = artifact["MILESTONE_DOMINANT"].value_counts().to_dict() \
        if "MILESTONE_DOMINANT" in artifact.columns else {}
    return {
        "avg_dd_g": float(artifact["DD_G"].fillna(0.0).mean()),
        "avg_td_g": float(artifact["TD_G"].fillna(0.0).mean()),
        "avg_share": float(artifact["MILESTONE_ABS_SHARE"].fillna(0.0).mean() * 100.0),
        "dominant_counts": dominant_counts,
    }


def write_analysis_artifact(df: pd.DataFrame, path: str | Path) -> None:
    """Persist an analysis artifact deterministically to CSV."""
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(artifact_path, index=False)


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
             trust_tier: str | None = None,
             benchmark_metadata: dict[str, object] | None = None) -> dict:
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

    context_cols = [col for col in PREDICTED_CONTEXT_COLUMNS if col in df.columns]
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
        "benchmark_metadata": benchmark_metadata,
        "top_misses": pd.DataFrame(columns=MISS_OUTPUT_COLUMNS),
        "milestone_contributions": pd.DataFrame(columns=MILESTONE_CONTRIBUTION_COLUMNS),
        "category_distortions": pd.DataFrame(columns=CATEGORY_DISTORTION_COLUMNS),
    }

    print(f"\n{'='*60}")
    print(f"Validation vs {label or Path(known_csv).name}")
    if note:
        print(f"  Note: {note}")
    if benchmark_class:
        print(f"  Benchmark class : {benchmark_class}")
    if trust_tier:
        print(f"  Trust tier      : {trust_tier}")
    if benchmark_metadata:
        print(f"  Readiness       : {'ready' if benchmark_metadata.get('ready') else 'not_ready'}")
        confidence_summary = benchmark_metadata.get("confidence_summary")
        file_confidence = benchmark_metadata.get("file_confidence")
        if confidence_summary is not None:
            if file_confidence is None or pd.isna(file_confidence):
                print(f"  Confidence      : {confidence_summary}")
            else:
                print(f"  Confidence      : {confidence_summary} ({float(file_confidence):.2f})")
        if benchmark_metadata.get("source_batch"):
            print(f"  Source batch    : {benchmark_metadata['source_batch']}")
        review_counts = benchmark_metadata.get("review_counts") or {}
        if review_counts:
            print(
                "  Review counts   : "
                f"{review_counts.get('total', 0)} total / "
                f"{review_counts.get('approved', 0)} approved / "
                f"{review_counts.get('pending', 0)} pending / "
                f"{review_counts.get('rejected', 0)} rejected"
            )
        if benchmark_metadata.get("generated_at"):
            print(f"  Generated at    : {benchmark_metadata['generated_at']}")
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
    milestone_artifact = build_milestone_contribution_artifact({"details": merged}, top_n=top_n_misses)
    category_distortion_artifact = build_category_distortion_artifact({"details": merged}, top_n=top_n_misses)
    result["top_misses"] = top_misses
    result["milestone_contributions"] = milestone_artifact
    result["category_distortions"] = category_distortion_artifact

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

    milestone_summary = summarize_milestone_contributions(milestone_artifact)
    dominant_counts = milestone_summary["dominant_counts"]
    if milestone_artifact is not None and len(milestone_artifact) > 0:
        dominant_parts = ", ".join(
            f"{label} {count}" for label, count in dominant_counts.items()
        ) or "none"
        print("\n  DD/TD contribution:")
        print(f"    avg DD_G                 {milestone_summary['avg_dd_g']:.3f}")
        print(f"    avg TD_G                 {milestone_summary['avg_td_g']:.3f}")
        print(f"    avg milestone share      {milestone_summary['avg_share']:.1f}%")
        print(f"    dominant                 {dominant_parts}")

    family_counts = summarize_category_distortion_families(category_distortion_artifact)
    if not family_counts.empty:
        print("\n  Category distortion families:")
        for family, count in family_counts.items():
            print(f"    {family:<24} {count}")

    return result
