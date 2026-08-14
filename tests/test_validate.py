import tempfile
import unittest
from pathlib import Path

import pandas as pd

from benchmark_ingest import build_benchmark_snapshot, build_review_table
from identity import canonical_player_key
from validate import (
    PREDICTED_CONTEXT_COLUMNS,
    append_benchmark_history,
    build_breakout_availability_artifact,
    build_breakout_availability_summary,
    build_category_distortion_artifact,
    build_category_distortion_summary,
    build_player_name,
    build_milestone_contribution_artifact,
    build_rank_series,
    build_top_miss_artifact,
    build_validation_summary_row,
    classify_breakout_availability,
    classify_category_distortion_family,
    classify_miss_bucket,
    compute_metric_deltas,
    find_previous_baseline,
    load_benchmark_history,
    normalize_player_name,
    summarize_breakout_availability_labels,
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

    def test_validate_details_carries_trend_profile_columns(self) -> None:
        # Guards the plumbing added for the role-growth calibration follow-up:
        # TREND_ROLE_SCORE/TREND_ROLE_BOOST/TREND_SHIFT/TREND_COMPOSITE_SCORE
        # must be listed in PREDICTED_CONTEXT_COLUMNS (the gate that decides
        # what survives validate()'s merge into `details`), and must actually
        # come through when present on the projected DataFrame.
        for col in (
            "TREND_ROLE_SCORE",
            "TREND_ROLE_BOOST",
            "TREND_SHIFT",
            "TREND_COMPOSITE_SCORE",
        ):
            self.assertIn(col, PREDICTED_CONTEXT_COLUMNS)

        rankings = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Nikola Jokić",
                    "RANK": 1,
                    "TREND_ROLE_SCORE": 0.271,
                    "TREND_ROLE_BOOST": 0.12,
                    "TREND_SHIFT": 0.05,
                    "TREND_COMPOSITE_SCORE": 0.18,
                }
            ]
        )
        known = pd.DataFrame([{"Player Name": "Nikola Jokic", "Rank": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            result = validate(rankings, str(csv_path))

        details = result["details"]
        self.assertIn("TREND_ROLE_SCORE", details.columns)
        self.assertIn("TREND_ROLE_BOOST", details.columns)
        self.assertIn("TREND_SHIFT", details.columns)
        self.assertIn("TREND_COMPOSITE_SCORE", details.columns)
        self.assertEqual(details["TREND_ROLE_BOOST"].iloc[0], 0.12)

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

    def test_validate_rank_ceiling_excludes_players_outside_pool_and_fixes_mae(self) -> None:
        # Guards the yahoo_25_26_live_snapshot fix: when the known CSV ranks across
        # a much larger player universe than our own pool, raw rank deltas for
        # players who fell far outside that universe inflate MAE for reasons that
        # have nothing to do with model quality. rank_ceiling should drop them.
        rankings = pd.DataFrame(
            [
                {"PLAYER_NAME": "Player A", "RANK": 1},
                {"PLAYER_NAME": "Player B", "RANK": 2},
                {"PLAYER_NAME": "Player C", "RANK": 3},
            ]
        )
        known = pd.DataFrame(
            [
                {"Player Name": "Player A", "Rank": 2},
                {"Player Name": "Player B", "Rank": 3},
                # Player C collapsed to a deep-universe rank (e.g. season-ending
                # injury) — outside our own 3-player pool entirely.
                {"Player Name": "Player C", "Rank": 700},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "known.csv"
            known.to_csv(csv_path, index=False)
            unbounded = validate(rankings, str(csv_path), min_matched_players=1)
            bounded = validate(rankings, str(csv_path), min_matched_players=1, rank_ceiling=3)

        self.assertEqual(unbounded["matched_players"], 3)
        self.assertEqual(unbounded["excluded_by_rank_ceiling"], 0)

        self.assertEqual(bounded["matched_players"], 2)
        self.assertEqual(bounded["excluded_by_rank_ceiling"], 1)
        self.assertLess(bounded["mae"], unbounded["mae"])
        self.assertNotIn("Player C", bounded["details"]["PLAYER_NAME"].tolist())

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

    def test_classify_miss_bucket_flags_healthy_one_dimensional_overrate(self) -> None:
        # Shaped after the real Devin Booker miss from the 2025-26 true
        # holdout: predicted #39, actual #119, healthy all season, no
        # elevated DD/TD/TECH, weak REB/BLK. Caught by the one-dimensional
        # scorer check before it would ever reach the trend-overprojection/
        # unclassified fallthrough below.
        booker_like_row = pd.Series(
            {
                "delta": -80,
                "GP_FACTOR": 0.88,
                "PTS": 23.08,
                "REB": 3.74,
                "AST": 6.17,
                "BLK": 0.30,
                "DD": 0.18,
                "TD": 0.0,
                "TECH": 0.029,
            }
        )

        self.assertEqual(
            classify_miss_bucket(booker_like_row),
            "category-weight distortion",
        )
        self.assertEqual(
            classify_category_distortion_family(booker_like_row),
            "concentrated scorer carry",
        )

    def test_classify_category_distortion_family_splits_concentrated_scorers_from_the_rest(self) -> None:
        # Real evidence from the balanced-category-carry investigation (see
        # GitHub issue #4's investigation comment and issue #8): 6 confirmed
        # high-usage overrated players and 6 confirmed low-usage/defensive
        # underrated players (+ Jaden McDaniels, whose static predicted
        # profile matches the underrated group even though one season's
        # actual outcome separately labeled him overrated) -- this is the
        # full known population this branch was derived from, not a sample.
        # NOTE: passing on this evidence is a regression guard (the code
        # implements the intended split), not validation that the pts>=17.0/
        # blocks<0.50 thresholds generalize -- see the plan doc's epistemic
        # status section. Real validation is out-of-sample data this branch
        # wasn't derived from.
        concentrated_scorers = {
            "Austin Reaves": {"PTS": 17.541259, "REB": 4.087120, "AST": 5.228809, "BLK": 0.277416},
            "De'Aaron Fox": {"PTS": 20.304762, "REB": 3.858804, "AST": 4.938959, "BLK": 0.335330},
            "DeMar DeRozan": {"PTS": 21.062275, "REB": 3.718307, "AST": 4.423756, "BLK": 0.442405},
            "Devin Booker": {"PTS": 23.080660, "REB": 3.743624, "AST": 6.170923, "BLK": 0.257713},
            "Mikal Bridges": {"PTS": 18.441817, "REB": 3.738925, "AST": 3.695754, "BLK": 0.457620},
            "Stephen Curry": {"PTS": 21.461422, "REB": 3.784324, "AST": 4.873427, "BLK": 0.351093},
        }
        not_concentrated = {
            "Dillon Brooks": {"PTS": 12.296763, "REB": 3.239429, "AST": 1.525713, "BLK": 0.171308},
            "Jaren Jackson Jr.": {"PTS": 19.292777, "REB": 4.838961, "AST": 1.840728, "BLK": 1.347030},
            "Jimmy Butler": {"PTS": 12.828389, "REB": 3.631303, "AST": 3.550322, "BLK": 0.209685},
            "Luguentz Dort": {"PTS": 9.328564, "REB": 3.547921, "AST": 1.398375, "BLK": 0.507343},
            "Toumani Camara": {"PTS": 10.059699, "REB": 5.281261, "AST": 1.960723, "BLK": 0.576549},
            "Jaden McDaniels": {"PTS": 11.461861, "REB": 4.969254, "AST": 1.797296, "BLK": 0.803736},
        }
        filler = {"TO": 2.0, "FG%": 0.47, "DD": 0.1, "TD": 0.0}

        for name, stats in concentrated_scorers.items():
            row = pd.Series({**stats, **filler})
            self.assertEqual(
                classify_category_distortion_family(row),
                "concentrated scorer carry",
                f"{name} should classify as concentrated scorer carry",
            )

        for name, stats in not_concentrated.items():
            row = pd.Series({**stats, **filler})
            self.assertEqual(
                classify_category_distortion_family(row),
                "unclassified (category-weight distortion)",
                f"{name} should not classify as concentrated scorer carry",
            )

    def test_classify_miss_bucket_flags_trend_overprojection(self) -> None:
        # GitHub issue #5: these 4 players are currently mislabeled
        # "aging/decline" despite having no real age-decline signal —
        # Avdija (23-24), Okongwu (24), Thompson (22) aren't remotely
        # decline-age, and Westbrook's own TREND_SHIFT is strongly
        # positive (the model over-projected his role growth, the
        # opposite of a decline story an age gate would have asserted).
        # What they share instead is a real, measured positive
        # TREND_SHIFT that didn't pay off in the actual outcome. Real
        # projected values from a full pipeline rerun against all 3
        # exact-league benchmarks (2025-26/2024-25/2023-24).
        avdija_like_row = pd.Series(
            {
                "delta": -49,
                "GP_FACTOR": 0.889,
                "PTS": 14.468253,
                "REB": 6.429995,
                "AST": 3.445216,
                "BLK": 0.430418,
                "DD": 0.201433,
                "TD": 0.023698,
                "TECH": 0.025994,
                "TREND_SHIFT": 0.085,
            }
        )
        westbrook_like_row = pd.Series(
            {
                "delta": -73,
                "GP_FACTOR": 0.902,
                "PTS": 11.426174,
                "REB": 4.374730,
                "AST": 5.174017,
                "BLK": 0.415443,
                "DD": 0.135968,
                "TD": 0.038848,
                "TECH": 0.023730,
                "TREND_SHIFT": 0.140,
            }
        )
        okongwu_like_row = pd.Series(
            {
                "delta": -18,
                "GP_FACTOR": 0.848,
                "PTS": 10.693791,
                "REB": 7.148129,
                "AST": 1.740867,
                "BLK": 0.813506,
                "DD": 0.319372,
                "TD": 0.0,
                "TECH": 0.027602,
                "TREND_SHIFT": 0.140,
            }
        )
        thompson_like_row = pd.Series(
            {
                "delta": -20,
                "GP_FACTOR": 0.829,
                "PTS": 11.088722,
                "REB": 6.577346,
                "AST": 3.031935,
                "BLK": 0.984705,
                "DD": 0.212217,
                "TD": 0.030317,
                "TECH": 0.023492,
                "TREND_SHIFT": 0.140,
            }
        )

        for row in (avdija_like_row, westbrook_like_row, okongwu_like_row, thompson_like_row):
            self.assertEqual(classify_miss_bucket(row), "trend overprojection")

    def test_classify_miss_bucket_flags_unclassified_below_trend_shift_threshold(self) -> None:
        # Pins the >= 0.085 threshold itself from below, not just from
        # missing data: these two real players from the same 12-player
        # investigated population DO carry a TREND_SHIFT value, but it's
        # well under the 0.085 floor, so they must fall through to
        # "unclassified (healthy overrate)" rather than firing the new
        # branch. Without a below-threshold row like this, mutating the
        # code to drop the ">= 0.085" comparison entirely (i.e. firing on
        # any non-null TREND_SHIFT) would still pass every other test.
        bridges_like_row = pd.Series(
            {
                "delta": -50,
                "GP_FACTOR": 0.803,
                "PTS": 16.513200,
                "REB": 5.976451,
                "AST": 2.955507,
                "BLK": 0.498068,
                "DD": 0.165313,
                "TD": 0.011808,
                "TECH": 0.015176,
                "TREND_SHIFT": 0.007,
            }
        )
        harris_like_row = pd.Series(
            {
                "delta": -59,
                "GP_FACTOR": 0.874,
                "PTS": 13.213405,
                "REB": 5.333794,
                "AST": 2.259010,
                "BLK": 0.628127,
                "DD": 0.063318,
                "TD": 0.0,
                "TECH": 0.018562,
                "TREND_SHIFT": -0.069,
            }
        )

        for row in (bridges_like_row, harris_like_row):
            self.assertEqual(classify_miss_bucket(row), "unclassified (healthy overrate)")

    def test_classify_miss_bucket_keeps_unclassified_for_non_concentrated_profiles(self) -> None:
        # A healthy overrate that ISN'T one-dimensional (decent REB/BLK)
        # should still fall through to "unclassified (healthy overrate)" —
        # the concentrated-scorer branch must not over-fire on every
        # healthy overrate. No TREND_SHIFT here either, so it also doesn't
        # qualify for "trend overprojection" (see GitHub issue #5's
        # investigation: "aging/decline" was itself a fallthrough with no
        # age signal, replaced by a real positive branch keyed on
        # TREND_SHIFT plus an honest unclassified remainder).
        balanced_decline_row = pd.Series(
            {
                "delta": -20,
                "GP_FACTOR": 0.90,
                "PTS": 12.0,
                "REB": 6.0,
                "AST": 3.0,
                "BLK": 0.8,
                "DD": 0.10,
                "TD": 0.0,
                "TECH": 0.01,
            }
        )

        self.assertEqual(classify_miss_bucket(balanced_decline_row), "unclassified (healthy overrate)")

    def test_classify_miss_bucket_does_not_flag_low_scoring_healthy_overrates(self) -> None:
        # Real false positives found in a subsequent review of the
        # Booker-branch fix: healthy, big-overrate players with weak
        # REB/BLK but LOW PTS are not one-dimensional scorers — they're
        # not caught by the category-weight-distortion branch. None of
        # these three rows carry a TREND_SHIFT value, so per issue #5's
        # fix they fail closed to the honest "unclassified (healthy
        # overrate)" remainder rather than being swept into
        # "category-weight distortion" OR asserting an unverified
        # "aging/decline" story.
        chris_paul_like_row = pd.Series(
            {
                "delta": -436,
                "GP_FACTOR": 0.904,
                "PTS": 7.918092280677733,
                "REB": 3.2757694994625677,
                "AST": 6.359757702093891,
                "BLK": 0.189656,
                "DD": 0.12504577856213622,
                "TD": 0.0,
                "TECH": 0.019530587539173652,
            }
        )
        bub_carrington_like_row = pd.Series(
            {
                "delta": -370,
                "GP_FACTOR": 1.0,
                "PTS": 9.841463414634147,
                "REB": 4.158536585365853,
                "AST": 4.439024390243903,
                "BLK": 0.256098,
                "DD": 0.056818181818181816,
                "TD": 0.0,
                "TECH": 0.027600000000000003,
            }
        )
        westbrook_like_row = pd.Series(
            {
                "delta": -73,
                "GP_FACTOR": 0.902,
                "PTS": 11.426174353658539,
                "REB": 4.3747304573170736,
                "AST": 5.174016963414634,
                "BLK": 0.415443,
                "DD": 0.13596810506566606,
                "TD": 0.03884803001876173,
                "TECH": 0.023729833536585365,
            }
        )

        self.assertEqual(classify_miss_bucket(chris_paul_like_row), "unclassified (healthy overrate)")
        self.assertEqual(classify_miss_bucket(bub_carrington_like_row), "unclassified (healthy overrate)")
        self.assertEqual(classify_miss_bucket(westbrook_like_row), "unclassified (healthy overrate)")

    def test_classify_miss_bucket_still_flags_real_booker_holdout_row(self) -> None:
        # Confirms the PTS-concentration threshold doesn't exclude the
        # real true positive it was added to protect: Devin Booker's
        # 2025-26 true-holdout row (PTS=23.08).
        booker_row = pd.Series(
            {
                "delta": -81,
                "GP_FACTOR": 0.88,
                "PTS": 23.080659532935194,
                "REB": 3.7436237735333364,
                "AST": 6.170923008103348,
                "BLK": 0.257713,
                "DD": 0.1806141422726606,
                "TD": 0.0,
                "TECH": 0.029056300138114274,
            }
        )
        self.assertEqual(classify_miss_bucket(booker_row), "category-weight distortion")

    def test_classify_miss_bucket_still_flags_real_austin_reaves_boundary_row(self) -> None:
        # An earlier 18.0 PTS threshold wrongly excluded this real row
        # (Austin Reaves, 2025-26 snapshot, PTS=17.54) — he was already a
        # confirmed "balanced category carry" true positive cited by name
        # in GitHub issue #4 before this fix. The threshold was lowered
        # to 15.0 specifically to keep this boundary case correct while
        # still excluding every confirmed false positive (max PTS ~12.6).
        reaves_row = pd.Series(
            {
                "delta": -31,
                "GP_FACTOR": 0.918,
                "PTS": 17.541258759484922,
                "REB": 4.087120061682169,
                "AST": 5.228808633079077,
                "BLK": 0.27741609887549407,
                "DD": 0.10073760561034889,
                "TD": 0.011193067290038765,
                "TECH": 0.022303,
            }
        )
        self.assertEqual(classify_miss_bucket(reaves_row), "category-weight distortion")

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

    def test_build_milestone_contribution_artifact_floors_tiny_total_value_denominator(self) -> None:
        # A small-but-nonzero TOTAL_VALUE (near-replacement-level net
        # contribution) blows up MILESTONE_ABS_SHARE when divided into a
        # normal-sized DD_G/TD_G sum. Real example: Jaren Jackson Jr.'s
        # 2023-24 row has TOTAL_VALUE=-0.034 and DD_G/TD_G summing to
        # ~0.52, producing a share of ~15.2 (a ratio that should never
        # exceed ~1.0). The floor should treat the ratio as unreliable
        # (NaN) rather than exploding, while leaving a normal-sized
        # TOTAL_VALUE row (Player A, unchanged from the sibling test)
        # untouched.
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
                        "PLAYER_NAME": "Jaren Jackson Jr.-like",
                        "RANK": 40,
                        "ACTUAL_RANK": 68,
                        "delta": 28,
                        "GP_FACTOR": 0.90,
                        "DD": 0.06,
                        "TD": 0.0,
                        "DD_G": -0.17,
                        "TD_G": -0.35,
                        "TOTAL_VALUE": -0.034,
                    },
                ]
            )
        }

        artifact = build_milestone_contribution_artifact(result, top_n=2)
        tiny_row = artifact[artifact["PLAYER_NAME"] == "Jaren Jackson Jr.-like"].iloc[0]
        normal_row = artifact[artifact["PLAYER_NAME"] == "Player A"].iloc[0]

        self.assertTrue(pd.isna(tiny_row["MILESTONE_ABS_SHARE"]))
        self.assertAlmostEqual(normal_row["MILESTONE_ABS_SHARE"], 1.30 / 3.0, places=6)

    def test_build_milestone_contribution_artifact_floors_negative_total_value_past_the_magnitude_floor(self) -> None:
        # The magnitude floor alone isn't enough: a real below-replacement
        # player can have |TOTAL_VALUE| well past MILESTONE_SHARE_TOTAL_VALUE_
        # FLOOR while TOTAL_VALUE itself is negative, with negative DD_G/TD_G
        # too. Real example: Jordan Poole, TOTAL_VALUE=-2.07, DD_G=-0.87,
        # TD_G=-0.35 -- |milestone_g_sum|/|total_value| = 1.22/2.07 = 0.59,
        # a ratio that reads as a real positive "milestone carry" signal for
        # a player who is below replacement partly BECAUSE of weak DD/TD, not
        # carried by them. "Share of value" is meaningless when there's no
        # positive value to share -- must be NaN, not a magnitude-only check.
        result = {
            "details": pd.DataFrame(
                [
                    {
                        "PLAYER_NAME": "Jordan Poole-like",
                        "RANK": 90,
                        "ACTUAL_RANK": 120,
                        "delta": -30,
                        "GP_FACTOR": 0.95,
                        "DD": 0.01,
                        "TD": 0.0,
                        "DD_G": -0.87,
                        "TD_G": -0.35,
                        "TOTAL_VALUE": -2.07,
                    },
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
                ]
            )
        }

        artifact = build_milestone_contribution_artifact(result, top_n=2)
        poole_row = artifact[artifact["PLAYER_NAME"] == "Jordan Poole-like"].iloc[0]
        normal_row = artifact[artifact["PLAYER_NAME"] == "Player A"].iloc[0]

        self.assertTrue(pd.isna(poole_row["MILESTONE_ABS_SHARE"]))
        self.assertAlmostEqual(normal_row["MILESTONE_ABS_SHARE"], 1.30 / 3.0, places=6)

    def test_classify_category_distortion_family_does_not_misfile_tiny_total_value_as_milestone_carry(self) -> None:
        # Once MILESTONE_ABS_SHARE is floored to NaN for a tiny TOTAL_VALUE
        # row, classify_category_distortion_family must not fall back to
        # "milestone carry" for a player whose DD/TD/AST profile doesn't
        # otherwise clear that family's thresholds.
        tiny_value_row = pd.Series(
            {
                "MILESTONE_ABS_SHARE": float("nan"),
                "PTS": 12.0,
                "REB": 4.84,
                "AST": 1.84,
                "3PTM": 1.0,
                "BLK": 1.35,
                "TO": 1.9,
                "FG%": 0.47,
                "DD": 0.064,
                "TD": 0.0,
            }
        )
        self.assertEqual(
            classify_category_distortion_family(tiny_value_row),
            "unclassified (category-weight distortion)",
        )

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
        self.assertEqual(artifact.iloc[0]["DISTORTION_FAMILY"], "unclassified (category-weight distortion)")
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
                                "DISTORTION_FAMILY": "concentrated scorer carry",
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
                                "DISTORTION_FAMILY": "concentrated scorer carry",
                            }
                        ]
                    ),
                },
            ]
        )

        concentrated_row = summary[summary["DISTORTION_FAMILY"] == "concentrated scorer carry"].iloc[0]
        self.assertEqual(concentrated_row["PRIMARY_BENCHMARKS"], 2)
        self.assertEqual(concentrated_row["PRIMARY_PLAYER_COUNT"], 1)
        self.assertEqual(concentrated_row["FOLLOW_UP_DECISION"], "monitor_narrow")

    def test_build_category_distortion_summary_excludes_unclassified_from_priority(self) -> None:
        # An "unclassified"-prefixed family (a structural default, not a
        # named phenomenon -- see GitHub issue #8) must never read
        # active_target/monitor_narrow, no matter how strong the raw hit
        # counts look. Fixture deliberately has 2 primary benchmarks and
        # 2 distinct players -- exactly what earns "active_target" for a
        # real family (see the repeat-signal test above) -- to prove the
        # exclusion isn't just "weak evidence never got there naturally".
        summary = build_category_distortion_summary(
            [
                {
                    "label": "actual_14cat_24_25_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "category_distortions": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Player A",
                                "delta": -40,
                                "DISTORTION_FAMILY": "unclassified (category-weight distortion)",
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
                                "PLAYER_NAME": "Player B",
                                "delta": -40,
                                "DISTORTION_FAMILY": "unclassified (category-weight distortion)",
                            }
                        ]
                    ),
                },
            ]
        )

        unclassified_row = summary[
            summary["DISTORTION_FAMILY"] == "unclassified (category-weight distortion)"
        ].iloc[0]
        self.assertEqual(unclassified_row["PRIMARY_BENCHMARKS"], 2)
        self.assertEqual(unclassified_row["PRIMARY_PLAYER_COUNT"], 2)
        self.assertEqual(unclassified_row["EVIDENCE_LEVEL"], "repeat_exact_league")
        self.assertNotIn(unclassified_row["FOLLOW_UP_DECISION"], {"active_target", "monitor_narrow"})
        self.assertEqual(unclassified_row["FOLLOW_UP_DECISION"], "not_prioritized")

    def test_classify_breakout_availability_emits_only_locked_labels(self) -> None:
        unclear_row = pd.Series({"delta": 10, "GP_FACTOR": 0.90, "GP": 78, "MIN": 20})
        overtrust_row = pd.Series({"delta": -40, "GP_FACTOR": 0.55, "GP": 40, "MIN": 25})
        undertrust_row = pd.Series({"delta": 45, "GP_FACTOR": 0.55, "GP": 40, "MIN": 25})
        role_growth_row = pd.Series(
            {
                "delta": 45,
                "GP_FACTOR": 0.90,
                "GP": 78,
                "MIN": 32,
                "AST": 3.0,
                "REB": 4.0,
                "ST": 0.4,
                "BLK": 0.3,
                "3PTM": 1.0,
            }
        )
        breakout_row = pd.Series(
            {
                "delta": 45,
                "GP_FACTOR": 0.90,
                "GP": 78,
                "MIN": 20,
                "AST": 2.0,
                "REB": 3.0,
                "ST": 0.3,
                "BLK": 0.2,
                "3PTM": 0.5,
            }
        )

        self.assertEqual(classify_breakout_availability(unclear_row), "unclear")
        self.assertEqual(classify_breakout_availability(overtrust_row), "availability overtrust")
        self.assertEqual(classify_breakout_availability(undertrust_row), "availability undertrust")
        self.assertEqual(classify_breakout_availability(role_growth_row), "role-growth underreaction")
        self.assertEqual(classify_breakout_availability(breakout_row), "breakout underreaction")

        locked_labels = {
            "breakout underreaction",
            "role-growth underreaction",
            "availability overtrust",
            "availability undertrust",
            "unclear",
        }
        for row in (unclear_row, overtrust_row, undertrust_row, role_growth_row, breakout_row):
            self.assertIn(classify_breakout_availability(row), locked_labels)

    def test_build_breakout_availability_artifact_keeps_context_compact(self) -> None:
        result = {
            "details": pd.DataFrame(
                [
                    {
                        "PLAYER_NAME": "Role Growth Case",
                        "RANK": 90,
                        "ACTUAL_RANK": 45,
                        "delta": 45,
                        "GP_FACTOR": 0.90,
                        "GP": 78,
                        "MIN": 32,
                        "PTS": 15.0,
                        "REB": 4.0,
                        "AST": 3.0,
                        "3PTM": 1.0,
                        "ST": 0.4,
                        "BLK": 0.3,
                        "DD": 0.10,
                        "TD": 0.00,
                        "DD_G": 0.05,
                        "TD_G": 0.00,
                        "TOTAL_VALUE": 1.5,
                    },
                    {
                        "PLAYER_NAME": "Availability Overtrust Case",
                        "RANK": 20,
                        "ACTUAL_RANK": 70,
                        "delta": -50,
                        "GP_FACTOR": 0.55,
                        "GP": 38,
                        "MIN": 28,
                        "PTS": 17.0,
                        "REB": 4.0,
                        "AST": 3.0,
                        "3PTM": 0.8,
                        "ST": 0.3,
                        "BLK": 0.2,
                        "DD": 0.10,
                        "TD": 0.00,
                        "DD_G": 0.05,
                        "TD_G": 0.00,
                        "TOTAL_VALUE": 2.0,
                    },
                ]
            )
        }

        artifact = build_breakout_availability_artifact(result, top_n=2)
        label_counts = summarize_breakout_availability_labels(artifact)

        self.assertIn("ROLE_SIGNAL_SCORE", artifact.columns)
        self.assertIn("AVAILABILITY_SIGNAL", artifact.columns)
        self.assertIn("DIAGNOSTIC_REASON", artifact.columns)
        self.assertIn("BREAKOUT_AVAILABILITY_LABEL", artifact.columns)

        role_growth_label = artifact.set_index("PLAYER_NAME").loc[
            "Role Growth Case", "BREAKOUT_AVAILABILITY_LABEL"
        ]
        availability_label = artifact.set_index("PLAYER_NAME").loc[
            "Availability Overtrust Case", "BREAKOUT_AVAILABILITY_LABEL"
        ]
        self.assertEqual(role_growth_label, "role-growth underreaction")
        self.assertEqual(availability_label, "availability overtrust")
        self.assertIn("role-growth underreaction", label_counts.index)
        self.assertIn("availability overtrust", label_counts.index)

        empty_artifact = build_breakout_availability_artifact({}, top_n=5)
        self.assertTrue(empty_artifact.empty)
        self.assertEqual(list(empty_artifact.columns), list(artifact.columns))

    def test_build_breakout_availability_summary_keeps_exact_league_primary(self) -> None:
        summary = build_breakout_availability_summary(
            [
                {
                    "label": "actual_14cat_24_25_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "breakout_availability": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Player X",
                                "delta": 45,
                                "BREAKOUT_AVAILABILITY_LABEL": "breakout underreaction",
                                "DIAGNOSTIC_REASON": "upside miss",
                            }
                        ]
                    ),
                },
                {
                    "label": "actual_14cat_23_24_snapshot.csv",
                    "benchmark_class": "historical_snapshot",
                    "trust_tier": "snapshot_derived",
                    "breakout_availability": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Player X",
                                "delta": 40,
                                "BREAKOUT_AVAILABILITY_LABEL": "breakout underreaction",
                                "DIAGNOSTIC_REASON": "upside miss",
                            }
                        ]
                    ),
                },
                {
                    "label": "yahoo_25_26_adp_proxy",
                    "benchmark_class": "direct_export_market",
                    "trust_tier": "direct_export",
                    "breakout_availability": pd.DataFrame(
                        [
                            {
                                "PLAYER_NAME": "Player Y",
                                "delta": -30,
                                "BREAKOUT_AVAILABILITY_LABEL": "availability overtrust",
                                "DIAGNOSTIC_REASON": "availability=low",
                            }
                        ]
                    ),
                },
            ]
        )

        breakout_row = summary[summary["BREAKOUT_AVAILABILITY_LABEL"] == "breakout underreaction"].iloc[0]
        availability_row = summary[summary["BREAKOUT_AVAILABILITY_LABEL"] == "availability overtrust"].iloc[0]

        self.assertEqual(breakout_row["PRIMARY_BENCHMARKS"], 2)
        self.assertEqual(breakout_row["PRIMARY_HITS"], 2)
        self.assertEqual(breakout_row["EVIDENCE_LEVEL"], "repeat_exact_league")

        self.assertEqual(availability_row["PRIMARY_HITS"], 0)
        self.assertEqual(availability_row["PRIMARY_BENCHMARKS"], 0)
        self.assertEqual(availability_row["SECONDARY_HITS"], 1)
        self.assertEqual(availability_row["EVIDENCE_LEVEL"], "secondary_only")

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
