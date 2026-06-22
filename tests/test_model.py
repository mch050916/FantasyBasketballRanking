import unittest

import numpy as np
import pandas as pd

from config import LEAGUE_CONFIG
from model import (
    calibrate_category_values,
    calibrate_milestone_value,
    compute_decline_factor,
    compute_tau,
    compute_trend_profile,
    project_stats,
)


class ProjectStatsTests(unittest.TestCase):
    def test_fg_percent_projection_stays_in_percentage_range(self) -> None:
        season_recent = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Sample Player",
                    "AGE": 27,
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
                    "AGE": 26,
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
        trend_profile = compute_trend_profile(
            player_season_stats={
                "2024-25": season_recent.iloc[0],
                "2023-24": season_prior.iloc[0],
            },
            available_seasons=["2024-25", "2023-24"],
            base_weights=[0.6, 0.4],
        )
        expected_fg_pct = (
            (10.0 * 0.500 * trend_profile["weights"][0]) + (20.0 * 0.250 * trend_profile["weights"][1])
        ) / ((10.0 * trend_profile["weights"][0]) + (20.0 * trend_profile["weights"][1]))

        self.assertAlmostEqual(fg_pct, expected_fg_pct, places=6)
        self.assertGreaterEqual(fg_pct, 0.0)
        self.assertLessEqual(fg_pct, 1.0)

    def test_composite_trend_weights_react_to_non_points_growth(self) -> None:
        player_season_stats = {
            "2024-25": pd.Series(
                {
                    "PTS": 14.0,
                    "AST": 8.0,
                    "REB": 6.5,
                    "3PTM": 2.0,
                    "ST": 1.4,
                    "BLK": 0.8,
                    "MIN": 35.0,
                }
            ),
            "2023-24": pd.Series(
                {
                    "PTS": 14.0,
                    "AST": 5.0,
                    "REB": 4.5,
                    "3PTM": 1.1,
                    "ST": 0.9,
                    "BLK": 0.5,
                    "MIN": 29.0,
                }
            ),
        }

        trend_profile = compute_trend_profile(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25", "2023-24"],
            base_weights=[0.625, 0.375],
        )

        self.assertGreater(trend_profile["composite_score"], 0.0)
        self.assertGreater(trend_profile["weights"][0], 0.625)

    def test_role_change_boost_is_capped(self) -> None:
        player_season_stats = {
            "2024-25": pd.Series(
                {
                    "PTS": 24.0,
                    "AST": 8.0,
                    "REB": 7.0,
                    "3PTM": 2.8,
                    "ST": 1.6,
                    "BLK": 0.9,
                    "MIN": 36.0,
                }
            ),
            "2023-24": pd.Series(
                {
                    "PTS": 10.0,
                    "AST": 3.0,
                    "REB": 3.0,
                    "3PTM": 1.0,
                    "ST": 0.7,
                    "BLK": 0.4,
                    "MIN": 21.0,
                }
            ),
        }

        trend_profile = compute_trend_profile(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25", "2023-24"],
            base_weights=[0.625, 0.375],
        )

        self.assertGreater(trend_profile["role_boost"], 0.0)
        self.assertLessEqual(trend_profile["role_boost"], 0.08)
        self.assertLessEqual(trend_profile["weights"][0], 0.85)

    def test_decline_factor_requires_age_and_negative_trend_alignment(self) -> None:
        older_negative = compute_decline_factor(age=35, composite_score=-0.22)
        older_stable = compute_decline_factor(age=35, composite_score=0.06)
        younger_negative = compute_decline_factor(age=28, composite_score=-0.22)

        self.assertLess(older_negative, older_stable)
        self.assertLess(older_negative, younger_negative)
        self.assertGreater(older_stable, 0.95)

    def test_milestone_calibration_keeps_dd_and_td_separate_and_bounded(self) -> None:
        raw_value = 0.35

        calibrated_dd = calibrate_milestone_value(raw_value, "DD", LEAGUE_CONFIG)
        calibrated_td = calibrate_milestone_value(raw_value, "TD", LEAGUE_CONFIG)

        self.assertGreater(calibrated_dd, 0.0)
        self.assertGreater(calibrated_td, 0.0)
        self.assertLess(calibrated_dd, raw_value)
        self.assertLess(calibrated_td, raw_value)
        self.assertLess(calibrated_td, calibrated_dd)

    def test_milestone_calibration_preserves_zero_and_does_not_noop(self) -> None:
        self.assertEqual(calibrate_milestone_value(0.0, "DD", LEAGUE_CONFIG), 0.0)
        self.assertEqual(calibrate_milestone_value(0.0, "TD", LEAGUE_CONFIG), 0.0)
        self.assertNotEqual(calibrate_milestone_value(0.50, "DD", LEAGUE_CONFIG), 0.50)
        self.assertNotEqual(calibrate_milestone_value(0.10, "TD", LEAGUE_CONFIG), 0.10)

    def test_milestone_calibration_compresses_high_end_values_more_strongly(self) -> None:
        low_value = 0.10
        high_value = 0.80

        dd_low = calibrate_milestone_value(low_value, "DD", LEAGUE_CONFIG) / low_value
        dd_high = calibrate_milestone_value(high_value, "DD", LEAGUE_CONFIG) / high_value
        td_low = calibrate_milestone_value(low_value, "TD", LEAGUE_CONFIG) / low_value
        td_high = calibrate_milestone_value(high_value, "TD", LEAGUE_CONFIG) / high_value

        self.assertLess(dd_high, dd_low)
        self.assertLess(td_high, td_low)
        self.assertLess(td_high, dd_high)

    def test_calibrate_category_values_leaves_non_milestones_untouched(self) -> None:
        raw = np.array([0.05, 0.20, 0.60], dtype=float)

        dd_values = calibrate_category_values(raw, "DD", LEAGUE_CONFIG)
        td_values = calibrate_category_values(raw, "TD", LEAGUE_CONFIG)
        pts_values = calibrate_category_values(raw, "PTS", LEAGUE_CONFIG)

        self.assertTrue(np.allclose(pts_values, raw))
        self.assertTrue(np.all(np.diff(dd_values) > 0))
        self.assertTrue(np.all(np.diff(td_values) > 0))
        self.assertTrue(np.all(dd_values < raw))
        self.assertTrue(np.all(td_values < raw))
        self.assertTrue(np.all(td_values < dd_values))

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
