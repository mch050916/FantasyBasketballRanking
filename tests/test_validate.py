import tempfile
import unittest
from pathlib import Path

import pandas as pd

from identity import canonical_player_key
from validate import (
    append_benchmark_history,
    build_player_name,
    build_rank_series,
    build_top_miss_artifact,
    build_validation_summary_row,
    compute_metric_deltas,
    find_previous_baseline,
    load_benchmark_history,
    normalize_player_name,
    summarize_miss_buckets,
    validate,
)


class ValidateTests(unittest.TestCase):
    def test_normalize_player_name_strips_accents_and_punctuation(self) -> None:
        self.assertEqual(normalize_player_name("Luka Dončić"), "lukadoncic")
        self.assertEqual(normalize_player_name("Nikola Jokić"), "nikolajokic")

    def test_validate_matches_normalized_player_names(self) -> None:
        rankings = pd.DataFrame(
            [
                {"PLAYER_NAME": "Luka Dončić", "RANK": 4},
                {"PLAYER_NAME": "Nikola Jokić", "RANK": 1},
            ]
        )
        known = pd.DataFrame(
            [
                {"Player Name": "Luka Doncic", "Rank": 5},
                {"Player Name": "Nikola Jokic", "Rank": 2},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(rankings, str(csv_path))

        self.assertEqual(result["matched_players"], 2)
        self.assertEqual(result["status"], "weak_matches")

    def test_build_player_name_supports_split_columns(self) -> None:
        known = pd.DataFrame(
            [
                {"First Name": "Luka", "Last Name": "Dončić"},
                {"First Name": "Shai", "Last Name": "Gilgeous-Alexander"},
            ]
        )

        built = build_player_name(known, ["First Name", "Last Name"])

        self.assertEqual(built.iloc[0], "Luka Dončić")
        self.assertEqual(built.iloc[1], "Shai Gilgeous-Alexander")

    def test_build_rank_series_supports_metric_based_ordering(self) -> None:
        known = pd.DataFrame(
            [
                {"Avg. Pick": 3.2},
                {"Avg. Pick": 1.7},
                {"Avg. Pick": 8.4},
            ]
        )

        ranks = build_rank_series(known, "Avg. Pick", rank_from_metric=True, ascending=True)

        self.assertEqual(ranks.tolist(), [2.0, 1.0, 3.0])

    def test_validate_returns_no_matches_health_state(self) -> None:
        rankings = pd.DataFrame([{"PLAYER_NAME": "Nikola Jokić", "RANK": 1}])
        known = pd.DataFrame([{"Player Name": "Someone Else", "Rank": 9}])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(rankings, str(csv_path))

        self.assertEqual(result["status"], "no_matches")
        self.assertEqual(result["matched_players"], 0)

    def test_validate_uses_override_backed_deterministic_matching(self) -> None:
        rankings = pd.DataFrame([{"PLAYER_NAME": "Jimmy Butler", "RANK": 12}])
        known = pd.DataFrame([{"Player Name": "Jimmy Butler III", "Rank": 11}])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(
                rankings,
                str(csv_path),
                benchmark_class="historical_snapshot",
                trust_tier="snapshot_derived",
            )

        self.assertEqual(result["matched_players"], 1)
        self.assertEqual(result["benchmark_class"], "historical_snapshot")
        self.assertEqual(result["trust_tier"], "snapshot_derived")
        self.assertEqual(canonical_player_key("Jimmy Butler III"), canonical_player_key("Jimmy Butler"))

    def test_validate_preserves_direct_export_metadata(self) -> None:
        rankings = pd.DataFrame([{"PLAYER_NAME": "Luka Dončić", "RANK": 4}])
        known = pd.DataFrame([{"First Name": "Luka", "Last Name": "Doncic", "Avg. Pick": 3.2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(
                rankings,
                str(csv_path),
                name_col=["First Name", "Last Name"],
                rank_col="Avg. Pick",
                rank_from_metric=True,
                benchmark_class="direct_export_market",
                trust_tier="direct_export",
            )

        self.assertEqual(result["benchmark_class"], "direct_export_market")
        self.assertEqual(result["trust_tier"], "direct_export")

    def test_benchmark_history_is_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "benchmark_history.csv"
            append_benchmark_history(
                history_path,
                [
                    {
                        "recorded_at": "2026-04-28T10:00:00",
                        "label": "snapshot.csv",
                        "benchmark_class": "historical_snapshot",
                        "trust_tier": "snapshot_derived",
                        "status": "ok",
                        "matched_players": 94,
                        "spearman": 0.658,
                        "hit_rate": 27.7,
                        "mae": 24.3,
                    }
                ],
            )
            history = load_benchmark_history(history_path)

        self.assertEqual(len(history), 1)
        self.assertEqual(history.iloc[0]["label"], "snapshot.csv")

    def test_compute_metric_deltas_uses_same_target_previous_baseline(self) -> None:
        result = {
            "label": "snapshot.csv",
            "benchmark_class": "historical_snapshot",
            "trust_tier": "snapshot_derived",
            "matched_players": 95,
            "spearman": 0.700,
            "hit_rate": 30.0,
            "mae": 20.0,
        }
        history = pd.DataFrame(
            [
                {
                    "recorded_at": "2026-04-28T10:00:00",
                    "label": "snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "status": "ok",
                    "matched_players": 90,
                    "spearman": 0.650,
                    "hit_rate": 25.0,
                    "mae": 22.5,
                }
            ]
        )

        baseline = find_previous_baseline(history, "snapshot.csv", "historical_snapshot", "snapshot_derived")
        deltas = compute_metric_deltas(result, baseline)

        self.assertEqual(deltas["matched_players"], 5.0)
        self.assertAlmostEqual(deltas["spearman"], 0.05)
        self.assertAlmostEqual(deltas["hit_rate"], 5.0)
        self.assertAlmostEqual(deltas["mae"], -2.5)

    def test_previous_baseline_is_isolated_per_benchmark_target(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "recorded_at": "2026-04-28T10:00:00",
                    "label": "snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "status": "ok",
                    "matched_players": 90,
                    "spearman": 0.650,
                    "hit_rate": 25.0,
                    "mae": 22.5,
                },
                {
                    "recorded_at": "2026-04-28T11:00:00",
                    "label": "yahoo_adp",
                    "benchmark_class": "direct_export_market",
                    "trust_tier": "direct_export",
                    "status": "ok",
                    "matched_players": 120,
                    "spearman": 0.670,
                    "hit_rate": 12.0,
                    "mae": 31.0,
                },
            ]
        )

        baseline = find_previous_baseline(history, "snapshot.csv", "historical_snapshot", "snapshot_derived")

        self.assertEqual(baseline["label"], "snapshot.csv")
        self.assertEqual(baseline["benchmark_class"], "historical_snapshot")

    def test_build_validation_summary_row_preserves_benchmark_metadata(self) -> None:
        row = build_validation_summary_row(
            {
                "label": "snapshot.csv",
                "benchmark_class": "historical_snapshot",
                "trust_tier": "snapshot_derived",
                "status": "ok",
                "matched_players": 94,
                "spearman": 0.658,
                "hit_rate": 27.7,
                "mae": 24.3,
            },
            "2026-04-28T12:00:00",
        )

        self.assertEqual(row["label"], "snapshot.csv")
        self.assertEqual(row["benchmark_class"], "historical_snapshot")
        self.assertEqual(row["trust_tier"], "snapshot_derived")

    def test_build_top_miss_artifact_keeps_context_compact_and_bucketed(self) -> None:
        result = {
            "details": pd.DataFrame(
                [
                    {
                        "PLAYER_NAME": "Player A",
                        "RANK": 20,
                        "ACTUAL_RANK": 80,
                        "delta": -60,
                        "GP_FACTOR": 0.60,
                        "PTS": 18.0,
                        "REB": 7.0,
                        "AST": 4.0,
                        "DD": 0.10,
                        "TD": 0.01,
                        "TECH": 0.01,
                        "TOTAL_VALUE": 2.5,
                        "FGM": 8.0,
                    },
                    {
                        "PLAYER_NAME": "Player B",
                        "RANK": 90,
                        "ACTUAL_RANK": 30,
                        "delta": 60,
                        "GP_FACTOR": 0.92,
                        "PTS": 16.0,
                        "REB": 5.0,
                        "AST": 5.0,
                        "DD": 0.05,
                        "TD": 0.00,
                        "TECH": 0.01,
                        "TOTAL_VALUE": 1.2,
                        "FGM": 6.0,
                    },
                    {
                        "PLAYER_NAME": "Player C",
                        "RANK": 25,
                        "ACTUAL_RANK": 70,
                        "delta": -45,
                        "GP_FACTOR": 0.88,
                        "PTS": 14.0,
                        "REB": 9.0,
                        "AST": 6.0,
                        "DD": 0.50,
                        "TD": 0.06,
                        "TECH": 0.04,
                        "TOTAL_VALUE": 2.0,
                        "FGM": 5.0,
                    },
                ]
            )
        }

        top_misses = build_top_miss_artifact(result, top_n=3)
        bucket_counts = summarize_miss_buckets(top_misses)

        self.assertIn("MISS_BUCKET", top_misses.columns)
        self.assertIn("GP_FACTOR", top_misses.columns)
        self.assertIn("TOTAL_VALUE", top_misses.columns)
        self.assertNotIn("FGM", top_misses.columns)
        self.assertEqual(top_misses.iloc[0]["MISS_BUCKET"], "availability miss")
        self.assertIn("breakout/role growth", bucket_counts.index)
        self.assertIn("category-weight distortion", bucket_counts.index)


if __name__ == "__main__":
    unittest.main()
