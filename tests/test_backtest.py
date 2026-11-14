"""Tests for backtest.py — fold config, leak guard, actuals, Marcel-lite."""

import pandas as pd
import numpy as np
import pytest

from backtest import (
    fold_config,
    FutureDataLeak,
    _make_leak_guard,
    _season_slug,
    scorable_folds,
    marcel_lite_baseline,
    build_actuals,
    FOLDS,
    MIN_GP_FOR_TARGET,
    COUNTING_CATS,
)


# ── fold_config ───────────────────────────────────────────────────────────────

class TestFoldConfig:
    def test_seasons_and_bbr_files(self):
        cfg = fold_config("2024-25")
        assert cfg["game_log_seasons"] == ["2023-24", "2022-23", "2021-22"]
        assert cfg["bbr_files"][0] == "basketball_reference_2023_24_total_stats.csv"
        assert len(cfg["bbr_files"]) == 3

    def test_cache_suffix(self):
        cfg = fold_config("2023-24")
        assert cfg["game_log_cache"] == "game_log_cache_2023_24.pkl"
        assert cfg["tech_cache"] == "tech_cache_2023_24.pkl"

    def test_full_season_games_short_seasons(self):
        cfg = fold_config("2021-22")
        games = cfg["full_season_games"]
        assert games["2019-20"] == 72
        assert games["2020-21"] == 72
        assert games.get("2018-19", 82) == 82

    def test_injury_flag_off_for_old_folds(self):
        cfg = fold_config("2021-22")
        assert cfg["_fetch_injuries"] is False

    def test_injury_flag_on_for_recent_folds(self):
        cfg = fold_config("2025-26")
        assert cfg["_fetch_injuries"] is True

    def test_tuned_flag(self):
        assert fold_config("2021-22")["_tuned"] is False
        assert fold_config("2022-23")["_tuned"] is False
        assert fold_config("2023-24")["_tuned"] is True

    def test_all_folds_configurable(self):
        for target in FOLDS:
            cfg = fold_config(target)
            assert len(cfg["bbr_files"]) == 3
            assert len(cfg["game_log_seasons"]) == 3


# ── Leak guard ────────────────────────────────────────────────────────────────

class TestLeakGuard:
    def test_blocks_target_season(self):
        def fake_load(path):
            return path

        guarded = _make_leak_guard("2024-25", fake_load, "fake_load")
        with pytest.raises(FutureDataLeak, match="2024-25"):
            guarded("basketball_reference_2024-25_totals.csv", "2024-25")

    def test_blocks_future_season(self):
        def fake_load(path):
            return path

        guarded = _make_leak_guard("2024-25", fake_load, "fake_load")
        with pytest.raises(FutureDataLeak):
            guarded("2025-26")

    def test_allows_past_season(self):
        def fake_load(season):
            return season

        guarded = _make_leak_guard("2024-25", fake_load, "fake_load")
        assert guarded("2023-24") == "2023-24"

    def test_blocks_list_arg(self):
        def fake_fetch(seasons):
            return seasons

        guarded = _make_leak_guard("2024-25", fake_fetch, "fake_fetch")
        with pytest.raises(FutureDataLeak):
            guarded(["2023-24", "2024-25"])

    def test_allows_past_list(self):
        def fake_fetch(seasons):
            return seasons

        guarded = _make_leak_guard("2024-25", fake_fetch, "fake_fetch")
        assert guarded(["2022-23", "2023-24"]) == ["2022-23", "2023-24"]


# ── Season slug ───────────────────────────────────────────────────────────────

def test_season_slug():
    assert _season_slug("2024-25") == "2024_25"
    assert _season_slug("2021-22") == "2021_22"


# ── Scorable folds ────────────────────────────────────────────────────────────

def test_scorable_folds_excludes_holdout():
    sf = scorable_folds()
    assert "2026-27" not in sf


# ── Total-value target correctness ───────────────────────────────────────────

class TestTotalValueTarget:
    """GP=0 players rank last; below-avg player's total doesn't improve when GP falls."""

    @pytest.fixture()
    def _actuals_frame(self, tmp_path, monkeypatch):
        """Build a minimal actuals frame with known rates."""
        from unittest.mock import patch
        from model import compute_g_scores
        from config import LEAGUE_CONFIG
        import copy

        # Fake league_tau (one per category)
        cats = list(LEAGUE_CONFIG["categories"].keys())
        league_tau = {c: 1.0 for c in cats}
        cfg = copy.deepcopy(LEAGUE_CONFIG)

        # Build a small BBR-like CSV
        rows = []
        # Player A: good player, 70 GP
        rows.append({"PLAYER_NAME": "Good Player", "GP": 70, "AGE": 27,
                      **{c: 10.0 for c in COUNTING_CATS}, "FG%": 0.500})
        # Player B: below-average, 70 GP
        rows.append({"PLAYER_NAME": "Below Avg", "GP": 70, "AGE": 27,
                      **{c: 2.0 for c in COUNTING_CATS}, "FG%": 0.350})
        # Player C: below-average, 30 GP (fewer games)
        rows.append({"PLAYER_NAME": "Below Avg Less GP", "GP": 30, "AGE": 27,
                      **{c: 2.0 for c in COUNTING_CATS}, "FG%": 0.350})
        # Player D: bust, 0 GP
        rows.append({"PLAYER_NAME": "Bust Player", "GP": 0, "AGE": 27,
                      **{c: np.nan for c in COUNTING_CATS}, "FG%": np.nan})

        bbr_df = pd.DataFrame(rows)
        csv_path = tmp_path / "test_bbr.csv"
        bbr_df.to_csv(csv_path, index=False)

        projected_players = [r["PLAYER_NAME"] for r in rows]

        with patch("backtest.load_bbr_csv", return_value=bbr_df), \
             patch("backtest._bbr_filename", return_value=str(csv_path)), \
             patch("backtest.fetch_game_logs", return_value=({}, {})), \
             patch("backtest.derive_stats_from_logs", return_value={}):
            actuals = build_actuals("2025-26", projected_players, league_tau, cfg)

        return actuals

    def test_gp0_ranks_last(self, _actuals_frame):
        bust = _actuals_frame[_actuals_frame["PLAYER_NAME"] == "Bust Player"]
        assert len(bust) == 1
        max_rank = _actuals_frame["ACTUAL_TOTAL_RANK"].max()
        assert bust.iloc[0]["ACTUAL_TOTAL_RANK"] >= max_rank

    def test_no_nan_total_rank(self, _actuals_frame):
        assert _actuals_frame["ACTUAL_TOTAL_RANK"].notna().all()

    def test_below_avg_total_doesnt_improve_with_fewer_gp(self, _actuals_frame):
        ba70 = _actuals_frame[_actuals_frame["PLAYER_NAME"] == "Below Avg"]
        ba30 = _actuals_frame[_actuals_frame["PLAYER_NAME"] == "Below Avg Less GP"]
        # Fewer games should not help a below-average player (higher rank = worse)
        assert ba30.iloc[0]["ACTUAL_TOTAL_RANK"] >= ba70.iloc[0]["ACTUAL_TOTAL_RANK"]
