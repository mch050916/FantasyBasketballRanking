import unittest

import numpy as np
import pandas as pd

from trade import BANK_COLUMNS, build_week_bank


def make_log(dates: list[str], **stats) -> pd.DataFrame:
    """Build a minimal NBA-API-shaped game log for testing."""
    n = len(dates)
    base = {"GAME_DATE": dates, "FGM": [0] * n, "FGA": [0] * n, "FG3M": [0] * n,
            "FTM": [0] * n, "PTS": [0] * n, "REB": [0] * n, "AST": [0] * n,
            "STL": [0] * n, "BLK": [0] * n, "TOV": [0] * n, "PF": [0] * n,
            "DD2": [0] * n, "TD3": [0] * n}
    base.update(stats)
    return pd.DataFrame(base)


class BuildWeekBankTests(unittest.TestCase):
    def test_sums_games_within_a_week_and_splits_across_weeks(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(
            ["2026-01-05", "2026-01-07", "2026-01-12"],
            PTS=[10, 20, 30], REB=[1, 2, 3])}}
        bank = build_week_bank(logs)["Test Player"]
        pts = bank[:, BANK_COLUMNS.index("PTS")]
        games = bank[:, BANK_COLUMNS.index("GAMES")]
        self.assertEqual(bank.shape[0], 2)
        self.assertEqual(sorted(pts.tolist()), [30.0, 30.0])
        self.assertEqual(sorted(games.tolist()), [1.0, 2.0])

    def test_renames_api_columns_to_league_category_names(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(
            ["2026-01-05"], STL=[3], TOV=[4], FG3M=[5], DD2=[1], TD3=[1])}}
        bank = build_week_bank(logs)["Test Player"]
        self.assertEqual(bank[0, BANK_COLUMNS.index("ST")], 3.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("TO")], 4.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("3PTM")], 5.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("DD")], 1.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("TD")], 1.0)

    def test_tech_is_proxied_from_personal_fouls(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(["2026-01-05"], PF=[5])}}
        bank = build_week_bank(logs)["Test Player"]
        self.assertAlmostEqual(bank[0, BANK_COLUMNS.index("TECH")], 5 * 0.012)

    def test_stacks_weeks_from_every_season(self) -> None:
        logs = {"2025-26": {"P": make_log(["2026-01-05"], PTS=[10])},
                "2024-25": {"P": make_log(["2025-01-06"], PTS=[20])}}
        self.assertEqual(build_week_bank(logs)["P"].shape[0], 2)

    def test_skips_players_with_empty_logs(self) -> None:
        logs = {"2025-26": {"P": pd.DataFrame()}}
        self.assertNotIn("P", build_week_bank(logs))

    def test_a_missing_column_reads_as_zero_rather_than_dropping_the_player(self) -> None:
        log = make_log(["2026-01-05"], PTS=[10]).drop(columns=["DD2"])
        bank = build_week_bank({"2025-26": {"P": log}})["P"]
        self.assertEqual(bank[0, BANK_COLUMNS.index("PTS")], 10.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("DD")], 0.0)
