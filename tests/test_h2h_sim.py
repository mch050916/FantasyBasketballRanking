"""Tests for h2h_sim — synthetic fixture for marginal player value."""

import numpy as np
import pandas as pd
import pytest

from h2h_sim import simulate_player_values, SIM_CATS, API_COL, CAT_META


def _make_logs(player_keys, weeks, overrides=None):
    """
    Build synthetic game logs: every player scores 10 in every counting stat
    every game, 1 game per week, except overrides[player] = {api_col: value}.
    """
    overrides = overrides or {}
    logs = {}
    for pk in player_keys:
        rows = []
        for w in weeks:
            row = {
                "GAME_DATE": f"2025-01-{int(w.split('_')[1]):02d}",
                "WEEK_KEY": w,
                "MIN": 30,
            }
            for cat in SIM_CATS:
                col = API_COL.get(cat, cat)
                if cat == "FG%":
                    continue
                default = 10 if CAT_META[cat]["direction"] == "high" else 2
                row[col] = default
            row["FGM"] = 5
            row["FGA"] = 10
            if pk in overrides:
                row.update(overrides[pk])
            rows.append(row)
        logs[pk] = pd.DataFrame(rows)
    return logs


class TestSimulatePlayerValues:
    def test_dominant_steals_player_ranks_above_clone(self):
        """
        Player 'star' gets 20 STL per game (vs everyone else's 10).
        Star must rank above an otherwise-identical player.
        """
        n = 30  # need enough for two non-overlapping 13-player rosters
        keys = [f"p{i}" for i in range(n)]
        weeks = [f"2025_{i}" for i in range(1, 5)]  # 4 weeks

        overrides = {"p0": {"STL": 20}}  # star steals player
        logs = _make_logs(keys, weeks, overrides)

        vals = simulate_player_values(logs, keys, n_rosters=500, seed=42, roster_size=13)

        # p0 (steals star) must rank above p1 (identical to everyone else)
        assert vals[0] > vals[1], (
            f"Steals star value {vals[0]:.3f} should exceed clone {vals[1]:.3f}"
        )

    def test_identical_players_have_similar_values(self):
        """All-identical players should have values clustered near zero."""
        keys = [f"p{i}" for i in range(30)]
        weeks = [f"2025_{i}" for i in range(1, 5)]
        logs = _make_logs(keys, weeks)

        vals = simulate_player_values(logs, keys, n_rosters=500, seed=42, roster_size=13)
        assert np.std(vals) < 1.0, f"Identical players should cluster: std={np.std(vals):.3f}"
