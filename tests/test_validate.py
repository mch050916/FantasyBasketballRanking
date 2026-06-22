import tempfile
import unittest
from pathlib import Path

import pandas as pd

from benchmark_ingest import build_benchmark_snapshot, build_review_table
from identity import canonical_player_key
from validate import (
    append_benchmark_history,
    build_category_distortion_artifact,
    build_category_distortion_summary,
    build_player_name,
    build_milestone_contribution_artifact,
    build_rank_series,
    build_top_miss_artifact,
    build_validation_summary_row,
    compute_metric_deltas,
    find_previous_baseline,
    load_benchmark_history,
    normalize_player_name,
    summarize_category_distortion_families,
    summarize_miss_buckets,
    summarize_milestone_contributions,
    validate,
    write_analysis_artifact,
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

    def test_validate_accepts_generated_historical_snapshot_shape(self) -> None:
        rankings = pd.DataFrame(
            [
                {"PLAYER_NAME": "Nikola Jokić", "RANK": 1},
                {"PLAYER_NAME": "Victor Wembanyama", "RANK": 2},
            ]
        )
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": "approved",
                },
                {
                    "rank": 2,
                    "player_name": "Victor Wembanyama",
                    "raw_ocr_name": "Victor Wembanyama",
                    "review_status": "approved",
                },
            ],
            season="2024-25",
            source_batch="batch_a",
        )
        known = build_benchmark_snapshot(review_table)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "actual_14cat_24_25_snapshot.csv"
            known.to_csv(csv_path, index=False)
            result = validate(
                rankings,
                str(csv_path),
                benchmark_class="historical_snapshot",
                trust_tier="snapshot_derived",
            )

        self.assertEqual(result["matched_players"], 2)
        self.assertEqual(result["status"], "weak_matches")

    def test_validate_preserves_benchmark_readiness_metadata(self) -> None:
        rankings = pd.DataFrame([{"PLAYER_NAME": "Nikola Jokić", "RANK": 1}])
        known = pd.DataFrame([{"Player Name": "Nikola Jokic", "Rank": 1}])
        benchmark_metadata = {
            "ready": True,
            "confidence_summary": "high",
            "file_confidence": 1.0,
            "source_batch": "legacy_2024_25_snapshot",
            "review_counts": {"total": 1, "approved": 1, "pending": 0, "rejected": 0},
            "generated_at": "2026-05-07T07:25:29+00:00",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(
                rankings,
                str(csv_path),
                benchmark_class="historical_snapshot",
                trust_tier="snapshot_derived",
                benchmark_metadata=benchmark_metadata,
            )

        self.assertEqual(result["benchmark_metadata"], benchmark_metadata)
        self.assertEqual(result["status"], "weak_matches")

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

    def test_build_milestone_contribution_artifact_separates_dd_and_td(self) -> None:
        result = {
            "details": pd.DataFrame(
                [
                    {
                        "PLAYER_NAME": "Player A",
                        "RANK": 18,
                        "ACTUAL_RANK": 78,
                        "delta": -60,
                        "GP_FACTOR": 0.92,
                        "DD": 0.45,
                        "TD": 0.02,
                        "DD_G": 1.20,
                        "TD_G": 0.10,
                        "TOTAL_VALUE": 3.0,
                    },
                    {
                        "PLAYER_NAME": "Player B",
                        "RANK": 30,
                        "ACTUAL_RANK": 70,
                        "delta": -40,
                        "GP_FACTOR": 0.88,
                        "DD": 0.20,
                        "TD": 0.08,
                        "DD_G": 0.30,
                        "TD_G": 0.90,
                        "TOTAL_VALUE": 2.0,
                    },
                ]
            )
        }

        artifact = build_milestone_contribution_artifact(result, top_n=2)
        summary = summarize_milestone_contributions(artifact)

        self.assertIn("DD_G", artifact.columns)
        self.assertIn("TD_G", artifact.columns)
        self.assertIn("MILESTONE_ABS_SHARE", artifact.columns)
        self.assertEqual(artifact.iloc[0]["MILESTONE_DOMINANT"], "DD")
        self.assertEqual(artifact.iloc[1]["MILESTONE_DOMINANT"], "TD")
        self.assertGreater(summary["avg_dd_g"], 0.0)
        self.assertGreater(summary["avg_td_g"], 0.0)
        self.assertIn("DD", summary["dominant_counts"])
        self.assertIn("TD", summary["dominant_counts"])

    def test_build_category_distortion_artifact_keeps_family_output_compact(self) -> None:
        result = {
            "details": pd.DataFrame(
                [
                    {
                        "PLAYER_NAME": "Nikola Vucevic",
                        "RANK": 18,
                        "ACTUAL_RANK": 112,
                        "delta": -94,
                        "MISS_BUCKET": "category-weight distortion",
                        "PTS": 16.3,
                        "REB": 9.1,
                        "AST": 3.1,
                        "3PTM": 1.4,
                        "BLK": 0.8,
                        "TO": 1.4,
                        "FG%": 0.51,
                        "DD": 0.56,
                        "TD": 0.01,
                        "DD_G": 1.55,
                        "TD_G": 0.02,
                        "TOTAL_VALUE": 2.67,
                        "FGM": 6.7,
                    },
                    {
                        "PLAYER_NAME": "Tyrese Haliburton",
                        "RANK": 4,
                        "ACTUAL_RANK": 103,
                        "delta": -99,
                        "MISS_BUCKET": "category-weight distortion",
                        "PTS": 16.7,
                        "REB": 3.2,
                        "AST": 8.6,
                        "3PTM": 2.6,
                        "BLK": 0.6,
                        "TO": 1.7,
                        "FG%": 0.47,
                        "DD": 0.40,
                        "TD": 0.01,
                        "DD_G": 0.35,
                        "TD_G": 0.01,
                        "TOTAL_VALUE": 4.20,
                        "FGM": 5.9,
                    },
                    {
                        "PLAYER_NAME": "Jayson Tatum",
                        "RANK": 5,
                        "ACTUAL_RANK": 121,
                        "delta": -116,
                        "MISS_BUCKET": "category-weight distortion",
                        "PTS": 23.8,
                        "REB": 7.5,
                        "AST": 5.0,
                        "3PTM": 3.0,
                        "BLK": 0.5,
                        "TO": 2.5,
                        "FG%": 0.46,
                        "DD": 0.38,
                        "TD": 0.02,
                        "DD_G": 0.38,
                        "TD_G": 0.02,
                        "TOTAL_VALUE": 3.95,
                        "FGM": 8.1,
                    },
                ]
            )
        }

        artifact = build_category_distortion_artifact(result, top_n=3)
        family_counts = summarize_category_distortion_families(artifact)

        self.assertIn("DISTORTION_FAMILY", artifact.columns)
        self.assertIn("MILESTONE_ABS_SHARE", artifact.columns)
        self.assertNotIn("FGM", artifact.columns)
        self.assertEqual(artifact.iloc[0]["DISTORTION_FAMILY"], "balanced category carry")
        self.assertIn("milestone carry", family_counts.index)
        self.assertIn("guard creation carry", family_counts.index)

    def test_build_category_distortion_summary_requires_repeat_exact_league_signal(self) -> None:
        summary = build_category_distortion_summary(
            [
                {
                    "label": "actual_14cat_24_25_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Nikola Vucevic",
                                "delta": -94,
                                "DISTORTION_FAMILY": "milestone carry",
                            },
                            {
                                "PLAYER_NAME": "Tyrese Haliburton",
                                "delta": -99,
                                "DISTORTION_FAMILY": "guard creation carry",
                            },
                        ]
                    ),
                },
                {
                    "label": "actual_14cat_23_24_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Josh Hart",
                                "delta": -58,
                                "DISTORTION_FAMILY": "milestone carry",
                            }
                        ]
                    ),
                },
                {
                    "label": "yahoo_25_26_adp_proxy",
                    "benchmark_class": "direct_export_market",
                    "trust_tier": "direct_export",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Jayson Tatum",
                                "delta": -116,
                                "DISTORTION_FAMILY": "guard creation carry",
                            }
                        ]
                    ),
                },
            ]
        )

        milestone_row = summary[summary["DISTORTION_FAMILY"] == "milestone carry"].iloc[0]
        guard_row = summary[summary["DISTORTION_FAMILY"] == "guard creation carry"].iloc[0]

        self.assertEqual(milestone_row["PRIMARY_BENCHMARKS"], 2)
        self.assertEqual(milestone_row["EVIDENCE_LEVEL"], "repeat_exact_league")
        self.assertEqual(milestone_row["FOLLOW_UP_DECISION"], "active_target")
        self.assertEqual(guard_row["PRIMARY_BENCHMARKS"], 1)
        self.assertEqual(guard_row["SECONDARY_HITS"], 1)
        self.assertEqual(guard_row["EVIDENCE_LEVEL"], "single_exact_league")
        self.assertEqual(guard_row["FOLLOW_UP_DECISION"], "watch_supporting")

    def test_build_category_distortion_summary_marks_narrow_repeat_family_for_monitoring(self) -> None:
        summary = build_category_distortion_summary(
            [
                {
                    "label": "actual_14cat_24_25_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Toumani Camara",
                                "delta": -16,
                                "DISTORTION_FAMILY": "balanced category carry",
                            }
                        ]
                    ),
                },
                {
                    "label": "actual_14cat_23_24_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Toumani Camara",
                                "delta": -16,
                                "DISTORTION_FAMILY": "balanced category carry",
                            }
                        ]
                    ),
                },
            ]
        )

        balanced_row = summary[summary["DISTORTION_FAMILY"] == "balanced category carry"].iloc[0]
        self.assertEqual(balanced_row["PRIMARY_BENCHMARKS"], 2)
        self.assertEqual(balanced_row["PRIMARY_PLAYER_COUNT"], 1)
        self.assertEqual(balanced_row["FOLLOW_UP_DECISION"], "monitor_narrow")

    def test_write_analysis_artifact_persists_deterministically(self) -> None:
        artifact = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Player A",
                    "DD_G": 1.2,
                    "TD_G": 0.1,
                    "MILESTONE_DOMINANT": "DD",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "milestone.csv"
            write_analysis_artifact(artifact, path)
            loaded = pd.read_csv(path)

        self.assertTrue(path.name.endswith("milestone.csv"))
        self.assertEqual(loaded.iloc[0]["PLAYER_NAME"], "Player A")
        self.assertEqual(loaded.iloc[0]["MILESTONE_DOMINANT"], "DD")


if __name__ == "__main__":
    unittest.main()
