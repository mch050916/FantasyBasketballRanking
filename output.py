"""
output.py — Formatting and saving rankings
===========================================
Handles printing the rankings table to the console and saving to CSV.
"""

import pandas as pd
from pathlib import Path


def format_rankings(df: pd.DataFrame, config: dict, top_n: int = 30) -> str:
    """
    Format the top N players as a readable table for console output.

    Stat columns are rounded to 2 decimal places.
    TOTAL_VALUE is rounded to 3.
    """
    cats      = list(config["categories"].keys())
    stat_cols = [c for c in cats if c in df.columns]
    display   = df.head(top_n)[["RANK", "PLAYER_NAME", "TOTAL_VALUE"] + stat_cols].copy()

    for col in stat_cols:
        display[col] = display[col].round(2)
    display["TOTAL_VALUE"] = display["TOTAL_VALUE"].round(3)

    try:
        from tabulate import tabulate
        return tabulate(
            display.values.tolist(),
            headers=display.columns.tolist(),
            tablefmt="github",
        )
    except ImportError:
        return display.to_string(index=False)


def save_rankings(df: pd.DataFrame, path: str) -> None:
    """Save the full rankings DataFrame to a CSV file."""
    df.to_csv(path, index=False)
    print(f"Full rankings ({len(df)} players) saved to: {path}")


def _rookie_tiers(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Group rookies by their real draft-slot bucket and order tiers by the
    bucket's own mean TOTAL_VALUE, best to worst. Rookies sharing a bucket
    share identical baseline stats by construction (rookie_baseline.py) --
    tiering by bucket is a real grouping, not a manufactured one, unlike the
    arbitrary tie-break a numeric RANK 1-N would assert across players with
    byte-identical projections.

    Returns (df with a TIER_LABEL column added, tier labels best-to-worst).
    """
    from rookie_baseline import pick_bucket_label

    working = df.copy()
    working["TIER_LABEL"] = working["OVERALL_PICK"].apply(pick_bucket_label)
    tier_order = (
        working.groupby("TIER_LABEL")["TOTAL_VALUE"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    return working, tier_order


def format_rookie_tiers(df: pd.DataFrame) -> str:
    """
    Format rookies as draft-slot tiers instead of ranks 1-N. Within a tier,
    players are listed alphabetically -- not a ranking, just a stable order.
    """
    working, tier_order = _rookie_tiers(df)
    lines = []
    for i, tier_label in enumerate(tier_order, start=1):
        tier_df = working[working["TIER_LABEL"] == tier_label].sort_values("PLAYER_NAME")
        players = ", ".join(tier_df["PLAYER_NAME"].tolist())
        lines.append(f"Tier {i} ({tier_label}, n={len(tier_df)}): {players}")
    return "\n".join(lines)


def save_rookie_tiers(df: pd.DataFrame, path: str) -> None:
    """
    Save rookie rows to CSV with a TIER column in place of the arbitrary
    RANK tie-break -- ranks within a tier aren't meaningful, so the CSV
    shouldn't assert a precision that isn't there either.
    """
    working, tier_order = _rookie_tiers(df)
    tier_number = {label: i for i, label in enumerate(tier_order, start=1)}
    working["TIER"] = working["TIER_LABEL"].map(lambda label: f"Tier {tier_number[label]} ({label})")
    working = working.drop(columns=["TIER_LABEL", "RANK"])
    working = working.sort_values(["TIER", "PLAYER_NAME"]).reset_index(drop=True)
    working = working[["TIER"] + [c for c in working.columns if c != "TIER"]]
    working.to_csv(path, index=False)
    print(f"Rookie tiers ({len(working)} players, {len(tier_order)} tiers) saved to: {path}")