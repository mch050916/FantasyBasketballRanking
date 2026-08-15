import unittest

import pandas as pd

from rookie_baseline import build_rookie_rows, get_rookie_baseline


class RookieBaselineTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF",
        "FGM", "FGA", "FG%", "3PTM", "FTM", "DD", "TD", "TECH",
    }

    def test_bucket_boundaries_resolve_to_the_correct_bucket(self) -> None:
        # Top-5 bucket
        self.assertAlmostEqual(get_rookie_baseline(1)["PTS"], 13.547, places=3)
        self.assertAlmostEqual(get_rookie_baseline(5)["PTS"], 13.547, places=3)
        # 6-14 bucket
        self.assertAlmostEqual(get_rookie_baseline(6)["PTS"], 7.235, places=3)
        self.assertAlmostEqual(get_rookie_baseline(14)["PTS"], 7.235, places=3)
        # 15-30 bucket
        self.assertAlmostEqual(get_rookie_baseline(15)["PTS"], 6.417, places=3)
        self.assertAlmostEqual(get_rookie_baseline(30)["PTS"], 6.417, places=3)
        # 31-60 bucket
        self.assertAlmostEqual(get_rookie_baseline(31)["PTS"], 3.992, places=3)
        self.assertAlmostEqual(get_rookie_baseline(60)["PTS"], 3.992, places=3)

    def test_out_of_range_picks_return_none(self) -> None:
        self.assertIsNone(get_rookie_baseline(0))
        self.assertIsNone(get_rookie_baseline(-1))
        self.assertIsNone(get_rookie_baseline(61))
        self.assertIsNone(get_rookie_baseline(100))

    def test_baseline_has_every_category_the_pipeline_needs(self) -> None:
        baseline = get_rookie_baseline(1)
        self.assertEqual(set(baseline.keys()), self.EXPECTED_KEYS)
        for key in self.EXPECTED_KEYS:
            self.assertIsInstance(baseline[key], float)

    def test_baseline_production_declines_monotonically_across_buckets(self) -> None:
        # Sanity check on the real computed data: earlier picks should
        # average more production than later picks, for the pipeline's
        # primary counting stats.
        top5 = get_rookie_baseline(1)
        lottery = get_rookie_baseline(10)
        round1 = get_rookie_baseline(20)
        round2 = get_rookie_baseline(45)
        # AST is deliberately excluded: real data shows a legitimate
        # small-sample crossover between the 6-14 bucket (n=26, AST=1.573)
        # and 15-30 bucket (n=46, AST=1.63) -- not a data error, just
        # normal variance in which draft years happened to produce more
        # assist-heavy players in one bucket. Every other category
        # declines monotonically.
        for cat in ("PTS", "REB", "MIN", "GP"):
            self.assertGreater(top5[cat], lottery[cat])
            self.assertGreater(lottery[cat], round1[cat])
            self.assertGreater(round1[cat], round2[cat])

    def test_returned_dict_is_a_copy_not_a_shared_reference(self) -> None:
        first = get_rookie_baseline(1)
        first["PTS"] = -999.0
        second = get_rookie_baseline(1)
        self.assertAlmostEqual(second["PTS"], 13.547, places=3)


class BuildRookieRowsTests(unittest.TestCase):
    def test_drafted_player_with_no_prior_history_gets_a_row(self) -> None:
        draft_history = {"AJ Dybantsa": {"overall_pick": 1, "round_number": 1}}
        rows = build_rookie_rows(draft_history, existing_players=set())

        self.assertEqual(len(rows), 1)
        row = rows.iloc[0]
        self.assertEqual(row["PLAYER_NAME"], "AJ Dybantsa")
        self.assertAlmostEqual(row["PTS"], 13.547, places=3)
        self.assertAlmostEqual(row["GP"], 70.333, places=3)

    def test_player_already_in_existing_players_is_skipped(self) -> None:
        # Simulates a player who somehow already has BBR history (e.g. a
        # prior-class draftee who appears in draft_history again for some
        # reason) -- must not be double-counted.
        draft_history = {"Cameron Boozer": {"overall_pick": 3, "round_number": 1}}
        rows = build_rookie_rows(draft_history, existing_players={"Cameron Boozer"})

        self.assertTrue(rows.empty)

    def test_matching_is_identity_aware_not_exact_string_only(self) -> None:
        # existing_players and draft_history names should be matched via
        # canonical_player_key (accent/punctuation-insensitive), same as
        # every other cross-source match in this pipeline.
        draft_history = {"Bilal Coulibaly": {"overall_pick": 7, "round_number": 1}}
        rows = build_rookie_rows(draft_history, existing_players={"bilal coulibaly"})

        self.assertTrue(rows.empty)

    def test_undrafted_or_out_of_range_picks_are_excluded(self) -> None:
        draft_history = {
            "Second Rounder": {"overall_pick": 60, "round_number": 2},
            "Out Of Range": {"overall_pick": 61, "round_number": 2},
        }
        rows = build_rookie_rows(draft_history, existing_players=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["PLAYER_NAME"], "Second Rounder")

    def test_empty_draft_history_returns_empty_dataframe_with_expected_columns(self) -> None:
        rows = build_rookie_rows({}, existing_players=set())

        self.assertTrue(rows.empty)
        expected_columns = {
            "PLAYER_NAME", "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK",
            "TO", "PF", "FGM", "FGA", "FG%", "3PTM", "FTM", "DD", "TD", "TECH",
            "OVERALL_PICK",
        }
        self.assertEqual(set(rows.columns), expected_columns)
