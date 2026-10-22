import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dashboard_server import (
    ARGV_BUILDERS,
    build_analyze_trade_argv,
    build_buy_low_sell_high_argv,
    build_find_trades_argv,
    build_meta,
    build_punt_planner_argv,
    build_schedule_strength_argv,
)

FIXED_FLAGS = [
    "--rosters", "rosters.csv",
    "--rankings", "durant_rankings_2026_27.csv",
    "--rookies", "durant_rankings_rookies_2026_27.csv",
]


class BuildPuntPlannerArgvTests(unittest.TestCase):
    def test_team_only(self) -> None:
        argv = build_punt_planner_argv({"team": "AR15"})
        self.assertEqual(
            argv,
            ["scripts/punt_planner.py"] + FIXED_FLAGS + ["--team", "AR15"],
        )

    def test_with_punt_and_show_players(self) -> None:
        argv = build_punt_planner_argv({"team": "AR15", "punt": "DD", "show_players": 20})
        self.assertEqual(
            argv,
            ["scripts/punt_planner.py"] + FIXED_FLAGS
            + ["--team", "AR15", "--punt", "DD", "--show-players", "20"],
        )

    def test_missing_team_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_punt_planner_argv({})

    def test_blank_team_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_punt_planner_argv({"team": "  "})

    def test_none_team_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_punt_planner_argv({"team": None})


class BuildFindTradesArgvTests(unittest.TestCase):
    def test_team_only(self) -> None:
        argv = build_find_trades_argv({"team": "AR15"})
        self.assertEqual(
            argv,
            ["scripts/find_trades.py"] + FIXED_FLAGS + ["--team", "AR15"],
        )

    def test_all_optional_fields(self) -> None:
        argv = build_find_trades_argv({
            "team": "AR15", "max_value_gap": 0.2, "sim_weeks": 500, "top": 3,
        })
        self.assertEqual(
            argv,
            ["scripts/find_trades.py"] + FIXED_FLAGS
            + ["--team", "AR15", "--max-value-gap", "0.2", "--sim-weeks", "500", "--top", "3"],
        )

    def test_no_team_omits_the_flag_for_whole_league_search(self) -> None:
        argv = build_find_trades_argv({})
        self.assertEqual(argv, ["scripts/find_trades.py"] + FIXED_FLAGS)
        self.assertNotIn("--team", argv)


class BuildAnalyzeTradeArgvTests(unittest.TestCase):
    def test_team_and_partner_only(self) -> None:
        argv = build_analyze_trade_argv({"team": "AR15", "partner": "LA Losers"})
        self.assertEqual(
            argv,
            ["scripts/analyze_trade.py"] + FIXED_FLAGS
            + ["--team", "AR15", "--partner", "LA Losers"],
        )

    def test_with_give_and_get(self) -> None:
        argv = build_analyze_trade_argv({
            "team": "AR15", "partner": "LA Losers",
            "give": "Matas Buzelis", "get": "Michael Porter Jr.",
        })
        self.assertEqual(
            argv,
            ["scripts/analyze_trade.py"] + FIXED_FLAGS
            + ["--team", "AR15", "--partner", "LA Losers",
               "--give", "Matas Buzelis", "--get", "Michael Porter Jr."],
        )

    def test_missing_partner_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_analyze_trade_argv({"team": "AR15"})

    def test_missing_team_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_analyze_trade_argv({"partner": "LA Losers"})


class BuildBuyLowSellHighArgvTests(unittest.TestCase):
    def test_no_fields_omits_every_flag(self) -> None:
        argv = build_buy_low_sell_high_argv({})
        self.assertEqual(
            argv,
            ["scripts/buy_low_sell_high.py", "--rankings", "durant_rankings_2026_27.csv",
             "--rookies", "durant_rankings_rookies_2026_27.csv"],
        )

    def test_all_fields(self) -> None:
        argv = build_buy_low_sell_high_argv({"season": "2025-26", "min_games": 10, "top": 5})
        self.assertEqual(
            argv,
            ["scripts/buy_low_sell_high.py", "--rankings", "durant_rankings_2026_27.csv",
             "--rookies", "durant_rankings_rookies_2026_27.csv",
             "--season", "2025-26", "--min-games", "10", "--top", "5"],
        )


class BuildScheduleStrengthArgvTests(unittest.TestCase):
    def test_no_fields_omits_every_flag(self) -> None:
        argv = build_schedule_strength_argv({})
        self.assertEqual(
            argv,
            ["scripts/schedule_strength.py", "--rosters", "rosters.csv"],
        )

    def test_week_and_team(self) -> None:
        argv = build_schedule_strength_argv({"week": "2026-10-27", "team": "AR15"})
        self.assertEqual(
            argv,
            ["scripts/schedule_strength.py", "--rosters", "rosters.csv",
             "--week", "2026-10-27", "--team", "AR15"],
        )


class ArgvBuildersRegistryTests(unittest.TestCase):
    def test_registry_has_all_five_tools(self) -> None:
        self.assertEqual(
            set(ARGV_BUILDERS.keys()),
            {"punt_planner", "find_trades", "analyze_trade", "buy_low_sell_high", "schedule_strength"},
        )

    def test_registry_dispatches_correctly(self) -> None:
        argv = ARGV_BUILDERS["punt_planner"]({"team": "AR15"})
        self.assertIn("scripts/punt_planner.py", argv)


class BuildMetaTests(unittest.TestCase):
    def test_missing_files_return_empty_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = build_meta(
                rosters_file=str(Path(tmpdir) / "no-rosters.csv"),
                rankings_path=str(Path(tmpdir) / "no-rankings.csv"),
                rookies_path=str(Path(tmpdir) / "no-rookies.csv"),
            )
        self.assertEqual(result, {"teams": [], "players": [], "rosters": {}})

    def test_real_files_return_sorted_teams_and_players(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Zeta", "PLAYER_NAME": "Player B"},
                {"TEAM": "Alpha", "PLAYER_NAME": "Player A"},
            ]).to_csv(rosters_path, index=False)

            rankings_path = Path(tmpdir) / "rankings.csv"
            pd.DataFrame([
                {"PLAYER_NAME": "Player A", "TOTAL_VALUE": 5.0},
                {"PLAYER_NAME": "Player B", "TOTAL_VALUE": 4.0},
            ]).to_csv(rankings_path, index=False)

            result = build_meta(
                rosters_file=str(rosters_path),
                rankings_path=str(rankings_path),
                rookies_path=str(Path(tmpdir) / "no-rookies.csv"),
            )

        self.assertEqual(result["teams"], ["Alpha", "Zeta"])
        self.assertEqual(result["players"], ["Player A", "Player B"])
        self.assertEqual(result["rosters"], {"Zeta": ["Player B"], "Alpha": ["Player A"]})


if __name__ == "__main__":
    unittest.main()
