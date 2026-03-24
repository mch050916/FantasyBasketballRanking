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