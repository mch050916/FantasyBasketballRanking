import unittest

import pandas as pd

from model import compute_tau, project_stats


class ProjectStatsTests(unittest.TestCase):
    def test_fg_percent_projection_stays_in_percentage_range(self) -> None:
        season_recent = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Sample Player",
                    "GP": 82,
                    "MIN": 34.0,
                    "FGM": 5.0,
                    "FGA": 10.0,
                    "FG%": 0.500,
                    "3PTM": 2.0,
                    "FTM": 4.0,
                    "PTS": 16.0,
                    "REB": 5.0,
                    "AST": 5.0,
                    "ST": 1.0,
                    "BLK": 0.5,
                    "TO": 2.0,
                    "PF": 2.0,
                }
            ]
        )
        season_prior = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Sample Player",
                    "GP": 82,
                    "MIN": 32.0,
                    "FGM": 5.0,
                    "FGA": 20.0,
                    "FG%": 0.250,
                    "3PTM": 1.0,
                    "FTM": 3.0,
                    "PTS": 14.0,
                    "REB": 4.0,
                    "AST": 4.0,
                    "ST": 0.8,
                    "BLK": 0.4,
                    "TO": 1.8,
                    "PF": 1.8,
                }
            ]
        )

        projected = project_stats(
            season_dfs=[season_recent, season_prior],
            weights=[0.6, 0.4],
            derived_stats={},
            tech_per_game={},
            seasons=["2024-25", "2023-24"],
        )

        fg_pct = projected.loc[projected["PLAYER_NAME"] == "Sample Player", "FG%"].iloc[0]

        self.assertAlmostEqual(fg_pct, 5.0 / 14.0, places=6)
        self.assertGreaterEqual(fg_pct, 0.0)
        self.assertLessEqual(fg_pct, 1.0)

    def test_compute_tau_derives_tech_from_weekly_pf_proxy(self) -> None:
        game_logs = {
            "2024-25": {
                "Sample Player": pd.DataFrame(
                    [
                        {"GAME_DATE": "2025-01-01", "PF": 1.0},
                        {"GAME_DATE": "2025-01-08", "PF": 2.0},
                        {"GAME_DATE": "2025-01-15", "PF": 3.0},
                        {"GAME_DATE": "2025-01-22", "PF": 4.0},
                    ]
                )
            }
        }

        player_tau, league_tau = compute_tau(
            game_logs=game_logs,
            categories=["PF", "TECH"],
            season_weights=[1.0],
        )

        self.assertIn("TECH", player_tau["Sample Player"])
        self.assertAlmostEqual(
            player_tau["Sample Player"]["TECH"],
            player_tau["Sample Player"]["PF"] * 0.012,
            places=9,
        )
        self.assertAlmostEqual(
            league_tau["TECH"],
            player_tau["Sample Player"]["TECH"],
            places=9,
        )


if __name__ == "__main__":
    unittest.main()
