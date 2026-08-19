"""
trade.py — Trade analyzer engine
=================================
Simulates a fantasy week by resampling each player's real observed weeks from
the cached game logs, rescaled to this season's projection, and counts how
often a roster wins each category against the league field.

Pure functions only: no file I/O, no printing. See scripts/analyze_trade.py.
"""

import zlib

import numpy as np
import pandas as pd

from model import add_week_key


SIM_CATEGORIES = ["FGM", "FTM", "3PTM", "PTS", "REB", "AST",
                  "ST", "BLK", "TO", "PF", "DD", "TD", "TECH"]

# FGA rides along because FG% is aggregated as sum(FGM)/sum(FGA), never as a
# mean of per-player ratios. GAMES is needed to convert weekly totals back to
# a per-game rate for the projection rescale.
BANK_COLUMNS = SIM_CATEGORIES + ["FGA", "GAMES"]

# Same mapping compute_tau uses, so both read the game logs identically.
API_COL_MAP = {"ST": "STL", "TO": "TOV", "3PTM": "FG3M", "DD": "DD2", "TD": "TD3"}

TECH_PER_PF = 0.012


_WARNED_COLUMNS: set[str] = set()


def _warn_missing_column(column: str) -> None:
    """
    Warn once per absent game-log column, then treat it as zeros.

    Dropping the whole player-season instead would empty every bank on one
    missing column and silently route the entire league to the synthetic
    fallback -- a far worse failure than one category reading zero.
    """
    if column not in _WARNED_COLUMNS:
        _WARNED_COLUMNS.add(column)
        print(f"  [warn] game logs have no '{column}' column; treating it as zero")


def _weekly_totals(logs: pd.DataFrame) -> np.ndarray | None:
    """Collapse one player-season game log into per-ISO-week totals."""
    logs = add_week_key(logs)
    grouped = logs.groupby("WEEK_KEY", sort=True)
    out = np.zeros((grouped.ngroups, len(BANK_COLUMNS)))

    for i, col in enumerate(BANK_COLUMNS):
        if col == "GAMES":
            out[:, i] = grouped.size().values
        elif col == "TECH":
            if "PF" not in logs.columns:
                _warn_missing_column("PF")
                continue
            out[:, i] = grouped["PF"].sum().values * TECH_PER_PF
        else:
            api_col = API_COL_MAP.get(col, col)
            if api_col not in logs.columns:
                _warn_missing_column(api_col)
                continue
            out[:, i] = grouped[api_col].sum().values

    return out


def build_week_bank(game_logs: dict[str, dict[str, pd.DataFrame]]) -> dict[str, np.ndarray]:
    """
    Build each player's bank of real observed weeks across all cached seasons.

    Returns { player_name -> array of shape (n_weeks, len(BANK_COLUMNS)) }.
    Unlike compute_tau, seasons are NOT recency-weighted here: every observed
    week is one equally likely draw. Recency enters through the projection
    rescale in scale_bank_to_projection, which is already recency-weighted.
    """
    frames: dict[str, list[np.ndarray]] = {}

    for season_logs in game_logs.values():
        for player_name, logs in season_logs.items():
            if logs is None or logs.empty:
                continue
            weekly = _weekly_totals(logs)
            if weekly is None or weekly.shape[0] == 0:
                continue
            frames.setdefault(player_name, []).append(weekly)

    return {name: np.vstack(chunks) for name, chunks in frames.items()}
