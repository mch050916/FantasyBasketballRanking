import tempfile
import unittest
from pathlib import Path

import pandas as pd

from identity import canonical_player_key
from validate import build_player_name, build_rank_series, normalize_player_name, validate


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


if __name__ == "__main__":
    unittest.main()
