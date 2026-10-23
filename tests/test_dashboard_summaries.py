import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import buy_low_sell_high   # noqa: E402
import find_trades          # noqa: E402
import punt_planner         # noqa: E402
import schedule_strength    # noqa: E402


class SummarizePuntResultTests(unittest.TestCase):
    def test_marks_the_punt_category_and_sorts_categories_as_given(self) -> None:
        shares = {"PTS": 0.6, "DD": 0.24, "REB": 0.3}
        ranked = ["DD", "REB", "PTS"]
        top_players = [("Shai", 6.27, 6.21, True), ("Jokic", 7.42, 8.60, False)]
        summary = punt_planner.summarize_punt_result("AR15", 6.44, shares, ranked, "DD", top_players)

        self.assertEqual(summary["kind"], "punt_planner")
        self.assertEqual(summary["team"], "AR15")
        self.assertEqual(summary["n"], 3)
        self.assertEqual([c["category"] for c in summary["categories"]], ranked)
        self.assertTrue(summary["categories"][0]["isPunt"])
        self.assertFalse(summary["categories"][1]["isPunt"])
        self.assertEqual(summary["punt"], "DD")

    def test_remaining_expected_excludes_the_punted_category(self) -> None:
        shares = {"PTS": 0.6, "DD": 0.24}
        summary = punt_planner.summarize_punt_result(
            "AR15", 0.84, shares, ["DD", "PTS"], "DD", [])
        self.assertAlmostEqual(summary["remaining"]["expected"], 0.60, places=6)
        self.assertEqual(summary["remaining"]["n"], 1)

    def test_player_rows_carry_the_mine_flag(self) -> None:
        top_players = [("Shai", 6.27, 6.21, True), ("Jokic", 7.42, 8.60, False)]
        summary = punt_planner.summarize_punt_result(
            "AR15", 1.0, {"PTS": 0.6, "DD": 0.4}, ["DD", "PTS"], "DD", top_players)
        self.assertEqual(summary["players"][0], {"name": "Shai", "value": 6.27, "was": 6.21, "mine": True})
        self.assertFalse(summary["players"][1]["mine"])


class SummarizeFindTradesResultTests(unittest.TestCase):
    def test_no_hits_still_reports_the_screening_params(self) -> None:
        summary = find_trades.summarize_find_trades_result(399, 0.15, 2000, [], 10)
        self.assertEqual(summary["kind"], "find_trades")
        self.assertEqual(summary["screened"], 399)
        self.assertEqual(summary["totalHits"], 0)
        self.assertEqual(summary["trades"], [])

    def test_trades_are_truncated_to_top_but_totalHits_counts_all(self) -> None:
        hits = [(0.01 * i, "A", "B", "GiveX", "GetY", 0.02 * i, 0.01 * i) for i in range(5)]
        summary = find_trades.summarize_find_trades_result(100, 0.1, 2000, hits, 2)
        self.assertEqual(summary["totalHits"], 5)
        self.assertEqual(len(summary["trades"]), 2)
        self.assertEqual(summary["trades"][0]["teamA"], "A")
        self.assertEqual(summary["trades"][0]["give"], "GiveX")


class SummarizeBuyLowSellHighResultTests(unittest.TestCase):
    def test_sell_high_is_the_front_and_buy_low_is_the_reversed_tail(self) -> None:
        rows = [("Up1", 20, 0.5), ("Up2", 15, 0.3), ("Down2", 10, -0.3), ("Down1", 12, -0.5)]
        summary = buy_low_sell_high.summarize_buy_low_sell_high_result(
            "2026-27", 5, rows, 2, False)
        self.assertEqual(summary["kind"], "buy_low_sell_high")
        self.assertEqual(summary["count"], 4)
        self.assertEqual([r["name"] for r in summary["sellHigh"]], ["Up1", "Up2"])
        # Reversed tail: Down1 (worst) first, matching the CLI report's own order.
        self.assertEqual([r["name"] for r in summary["buyLow"]], ["Down1", "Down2"])

    def test_empty_rows_summary_still_carries_the_season_and_threshold(self) -> None:
        summary = buy_low_sell_high.summarize_buy_low_sell_high_result("2026-27", 5, [], 15, True)
        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["sellHigh"], [])
        self.assertEqual(summary["buyLow"], [])
        self.assertTrue(summary["degraded"])


class SummarizeScheduleStrengthResultTests(unittest.TestCase):
    def test_teams_are_sorted_by_games_descending(self) -> None:
        counts = pd.Series({"PHI": 4, "OKC": 3, "LAL": 2})
        summary = schedule_strength.summarize_schedule_strength_result(
            "2026-10-23", "2026-27", counts)
        self.assertEqual(summary["kind"], "schedule_strength")
        self.assertEqual([t["team"] for t in summary["teams"]], ["PHI", "OKC", "LAL"])
        self.assertEqual(summary["teams"][0]["games"], 4)

    def test_roster_is_omitted_when_not_given(self) -> None:
        summary = schedule_strength.summarize_schedule_strength_result(
            "2026-10-23", "2026-27", pd.Series({"PHI": 4}))
        self.assertNotIn("roster", summary)

    def test_roster_passes_through_when_given(self) -> None:
        roster = {"team": "AR15", "players": [{"name": "SGA", "nbaTeam": "OKC", "games": 3}]}
        summary = schedule_strength.summarize_schedule_strength_result(
            "2026-10-23", "2026-27", pd.Series({"OKC": 3}), roster)
        self.assertEqual(summary["roster"], roster)


if __name__ == "__main__":
    unittest.main()
