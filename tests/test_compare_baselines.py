import contextlib
import io
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from compare_baselines import (
    bootstrap_single_run,
    classify_season,
    exact_league_targets,
    paired_bootstrap,
    run_quiet,
)


class ClassifySeasonTests(unittest.TestCase):
    def test_neutral_when_no_thresholds_given(self) -> None:
        self.assertEqual(classify_season(0.5, -50.0, None, None), "neutral")

    def test_neutral_when_deltas_within_threshold(self) -> None:
        self.assertEqual(classify_season(0.01, 0.5, 0.02, 1.0), "neutral")

    def test_improved_when_spearman_gain_clears_threshold(self) -> None:
        self.assertEqual(classify_season(0.05, 0.0, 0.02, 1.0), "improved")

    def test_improved_when_mae_drop_clears_threshold(self) -> None:
        self.assertEqual(classify_season(0.0, -2.0, 0.02, 1.0), "improved")

    def test_regressed_when_spearman_drop_clears_threshold(self) -> None:
        self.assertEqual(classify_season(-0.05, 0.0, 0.02, 1.0), "regressed")

    def test_regressed_when_mae_rise_clears_threshold(self) -> None:
        self.assertEqual(classify_season(0.0, 2.0, 0.02, 1.0), "regressed")

    def test_regression_takes_priority_over_improvement_on_other_metric(self) -> None:
        # Spearman improved a lot, but MAE regressed beyond its threshold —
        # this must not be reported as an overall improvement.
        self.assertEqual(classify_season(0.10, 5.0, 0.02, 1.0), "regressed")


class ExactLeagueTargetsTests(unittest.TestCase):
    def test_returns_exactly_three_historical_snapshot_targets(self) -> None:
        targets = exact_league_targets()
        self.assertEqual(len(targets), 3)
        for target in targets:
            self.assertEqual(target["benchmark_class"], "historical_snapshot")


class RunQuietTests(unittest.TestCase):
    def test_suppresses_console_output_and_returns_result(self) -> None:
        rankings = pd.DataFrame([{"PLAYER_NAME": "Player A", "RANK": 1}])
        known = pd.DataFrame([{"Player Name": "Player A", "Rank": 2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            target = {"path": str(csv_path), "name_col": "Player Name", "rank_col": "Rank"}

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                result = run_quiet(rankings, target)

        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(result["matched_players"], 1)


class BootstrapSingleRunTests(unittest.TestCase):
    def _perfect_match_details(self, n: int = 30) -> pd.DataFrame:
        # RANK == ACTUAL_RANK at every row -> every bootstrap resample is a
        # perfect match too (elementwise identical), so spearman is always
        # exactly 1.0 and MAE is always exactly 0.0. Deterministic regardless
        # of which indices get resampled.
        ranks = list(range(1, n + 1))
        return pd.DataFrame({"RANK": ranks, "ACTUAL_RANK": ranks})

    def test_reports_n_matched_and_n_iterations(self) -> None:
        result = bootstrap_single_run(self._perfect_match_details(), n_iterations=200, seed=1)
        self.assertEqual(result["n_matched"], 30)
        self.assertEqual(result["n_iterations"], 200)

    def test_perfect_match_gives_spearman_one_and_mae_zero_every_time(self) -> None:
        result = bootstrap_single_run(self._perfect_match_details(), n_iterations=200, seed=1)
        self.assertAlmostEqual(result["spearman"]["mean"], 1.0, places=9)
        self.assertAlmostEqual(result["spearman"]["ci_low"], 1.0, places=9)
        self.assertAlmostEqual(result["spearman"]["ci_high"], 1.0, places=9)
        self.assertEqual(result["mae"]["mean"], 0.0)
        self.assertEqual(result["mae"]["ci_low"], 0.0)
        self.assertEqual(result["mae"]["ci_high"], 0.0)

    def test_same_seed_is_reproducible(self) -> None:
        details = pd.DataFrame({"RANK": [1, 5, 2, 8, 3, 9, 4, 7, 6, 10],
                                 "ACTUAL_RANK": [2, 4, 1, 9, 3, 7, 5, 8, 6, 10]})
        first = bootstrap_single_run(details, n_iterations=300, seed=7)
        second = bootstrap_single_run(details, n_iterations=300, seed=7)
        self.assertEqual(first["spearman"], second["spearman"])
        self.assertEqual(first["mae"], second["mae"])

    def test_different_seed_can_change_result(self) -> None:
        details = pd.DataFrame({"RANK": [1, 5, 2, 8, 3, 9, 4, 7, 6, 10],
                                 "ACTUAL_RANK": [2, 4, 1, 9, 3, 7, 5, 8, 6, 10]})
        first = bootstrap_single_run(details, n_iterations=300, seed=7)
        second = bootstrap_single_run(details, n_iterations=300, seed=8)
        self.assertNotEqual(first["spearman"]["mean"], second["spearman"]["mean"])


class PairedBootstrapTests(unittest.TestCase):
    def test_identical_before_and_after_centers_delta_on_zero(self) -> None:
        details = pd.DataFrame({
            "PLAYER_KEY": [f"player{i}" for i in range(30)],
            "RANK": list(range(1, 31)),
            "ACTUAL_RANK": [(i * 7) % 30 + 1 for i in range(30)],
        })

        result = paired_bootstrap(details, details.copy(), n_iterations=200, seed=1)

        # Same data resampled with the same indices on both sides -> every
        # iteration's before/after metrics are identical, so every delta is
        # exactly zero. No seed-dependent flakiness possible here.
        self.assertEqual(result["spearman_delta"]["median"], 0.0)
        self.assertEqual(result["spearman_delta"]["ci_low"], 0.0)
        self.assertEqual(result["spearman_delta"]["ci_high"], 0.0)
        self.assertEqual(result["mae_delta"]["median"], 0.0)
        self.assertEqual(result["spearman_delta"]["pct_improved"], 0.0)
        self.assertEqual(result["mae_delta"]["pct_improved"], 0.0)

    def test_only_players_matched_in_both_runs_are_paired(self) -> None:
        before = pd.DataFrame({
            "PLAYER_KEY": ["a", "b", "c"],
            "RANK": [1, 2, 3],
            "ACTUAL_RANK": [1, 2, 3],
        })
        after = pd.DataFrame({
            "PLAYER_KEY": ["b", "c", "d"],
            "RANK": [1, 2, 3],
            "ACTUAL_RANK": [1, 2, 3],
        })

        # n=2 paired players means some resamples pick the same player twice,
        # which makes the resampled ACTUAL_RANK array constant -> scipy warns
        # that spearman correlation is undefined for that draw. Expected for
        # this tiny fixture; the nan-safe aggregation handles it correctly.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = paired_bootstrap(before, after, n_iterations=50, seed=1)

        self.assertEqual(result["n_paired"], 2)

    def test_pairing_is_by_identity_not_position(self) -> None:
        # Regression guard: pairing must join on PLAYER_KEY, not row position.
        # A positional implementation would happen to pass every other test
        # here (both sides come from the same deterministically-ordered
        # pipeline in real use), but breaks silently the moment either run's
        # row order differs — e.g. because a model change shifted who
        # qualifies. Shuffling one side's row order is the one thing that
        # actually discriminates identity-based pairing from positional.
        n = 40
        keys = [f"p{i}" for i in range(n)]
        rank_before = list(range(1, n + 1))
        actual = [(i * 5) % n + 1 for i in range(n)]

        before = pd.DataFrame({"PLAYER_KEY": keys, "RANK": rank_before, "ACTUAL_RANK": actual})
        after = pd.DataFrame({"PLAYER_KEY": keys, "RANK": [r + 1 for r in rank_before], "ACTUAL_RANK": actual})

        rng = np.random.default_rng(11)
        shuffled_order = list(range(n))
        rng.shuffle(shuffled_order)
        after_shuffled = after.iloc[shuffled_order].reset_index(drop=True)

        result_original = paired_bootstrap(before, after, n_iterations=300, seed=5)
        result_shuffled = paired_bootstrap(before, after_shuffled, n_iterations=300, seed=5)

        self.assertEqual(result_original["spearman_delta"], result_shuffled["spearman_delta"])
        self.assertEqual(result_original["mae_delta"], result_shuffled["mae_delta"])

    def test_excluded_players_are_reported_by_side(self) -> None:
        before = pd.DataFrame({
            "PLAYER_KEY": ["a", "b", "c", "x", "y"],
            "RANK": [1, 2, 3, 4, 5],
            "ACTUAL_RANK": [1, 2, 3, 4, 5],
        })
        after = pd.DataFrame({
            "PLAYER_KEY": ["a", "b", "c", "z"],
            "RANK": [1, 2, 3, 4],
            "ACTUAL_RANK": [1, 2, 3, 4],
        })

        # n=3 paired players carries the same small-sample constant-resample
        # risk as test_only_players_matched_in_both_runs_are_paired above.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = paired_bootstrap(before, after, n_iterations=50, seed=1)

        self.assertEqual(result["n_paired"], 3)
        # "x" and "y" are before-only.
        self.assertEqual(result["excluded_before_only"], 2)
        # "z" is after-only.
        self.assertEqual(result["excluded_after_only"], 1)

    def test_systematically_better_after_shows_high_pct_improved(self) -> None:
        n = 40
        actual = list(range(1, n + 1))
        # "before" ranks are shuffled/noisy vs actual; "after" ranks equal
        # actual exactly -> after is a strictly better predictor every time.
        rng = np.random.default_rng(42)
        noisy_before = list(actual)
        rng.shuffle(noisy_before)

        before = pd.DataFrame({
            "PLAYER_KEY": [f"p{i}" for i in range(n)],
            "RANK": noisy_before,
            "ACTUAL_RANK": actual,
        })
        after = pd.DataFrame({
            "PLAYER_KEY": [f"p{i}" for i in range(n)],
            "RANK": actual,
            "ACTUAL_RANK": actual,
        })

        result = paired_bootstrap(before, after, n_iterations=500, seed=3)

        self.assertGreater(result["mae_delta"]["pct_improved"], 90.0)
        self.assertLess(result["mae_delta"]["median"], 0.0)


if __name__ == "__main__":
    unittest.main()
