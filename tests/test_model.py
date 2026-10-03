import unittest

import numpy as np
import pandas as pd

from config import LEAGUE_CONFIG
from model import (
    RECENT_WEIGHT_MAX,
    add_week_key,
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
        raw_expected_fg_pct = (
            (10.0 * 0.500 * trend_profile["weights"][0]) + (20.0 * 0.250 * trend_profile["weights"][1])
        ) / ((10.0 * trend_profile["weights"][0]) + (20.0 * trend_profile["weights"][1]))

        # project_stats shrinks the raw blend toward a league-wide prior,
        # weighted by real total attempts across the loaded seasons (see
        # compute_weighted_fg_pct) -- the prior here is season_recent's own
        # (and only) player's FG%, since that's the newest season's table.
        total_attempts = (10.0 * 82) + (20.0 * 82)
        confidence = total_attempts / (total_attempts + 150.0)
        expected_fg_pct = confidence * raw_expected_fg_pct + (1 - confidence) * 0.500

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

        # This scenario is the fully-headroom-constrained case named in
        # finding #3 of the whole-branch review: composite_score clips to its
        # max (0.5), so trend_shift is fully maxed at 0.14, and role_score
        # also saturates the ratio to 1.0. Under the headroom-aware cap
        # (option (c) from docs/superpowers/specs/2026-08-12-role-growth-
        # calibration-followup-research.md #3), role_boost is no longer the
        # nominal role_boost_cap (0.12) — it's capped at whatever headroom is
        # left under RECENT_WEIGHT_MAX (0.85) after base_weights[0] (0.625)
        # and trend_shift (0.14): available_headroom = 0.85 - 0.625 - 0.14 =
        # 0.085, so effective_role_boost_cap = min(0.12, 0.085) = 0.085, and
        # since the ratio clips to 1.0, role_boost == 0.085 (verified by
        # running compute_trend_profile directly against this scenario).
        # Before this fix, role_boost computed to the full 0.12, and
        # base_weights[0] + trend_shift + role_boost = 0.885 was silently
        # truncated to 0.85 by _rebalance_recent_weight's clamp — discarding
        # 0.035 of the nominal boost unpredictably. Now weights[0] arrives at
        # 0.85 directly through the headroom-aware calculation itself, with
        # the downstream clamp acting as a no-op safety net rather than the
        # thing doing the truncating.
        self.assertGreater(trend_profile["role_boost"], 0.0)
        self.assertAlmostEqual(trend_profile["role_boost"], 0.085, places=6)
        self.assertLessEqual(trend_profile["weights"][0], 0.85)
        self.assertAlmostEqual(trend_profile["weights"][0], 0.85, places=6)

    def test_role_boost_saturates_for_moderate_role_growth(self) -> None:
        player_season_stats = {
            "2024-25": pd.Series(
                {
                    "PTS": 18.0,
                    "AST": 4.0,
                    "REB": 5.0,
                    "3PTM": 1.5,
                    "ST": 1.0,
                    "BLK": 0.5,
                    "MIN": 33.0,
                }
            ),
            "2023-24": pd.Series(
                {
                    "PTS": 15.0,
                    "AST": 3.3,
                    "REB": 4.3,
                    "3PTM": 1.2,
                    "ST": 0.9,
                    "BLK": 0.45,
                    "MIN": 27.0,
                }
            ),
        }

        trend_profile = compute_trend_profile(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25", "2023-24"],
            base_weights=[0.625, 0.375],
        )

        # role_score here is ~0.22 — below the OLD 0.25 saturation point
        # (would only have produced a partial ~0.069 boost under the old
        # constants) but above the NEW 0.18 saturation point, so the ratio
        # role_score / ROLE_BOOST_SATURATION clips to 1.0. This is the exact
        # shape of miss the issue names: real minutes/production growth that
        # the old boost mechanism under-delivered on.
        #
        # Under the headroom-aware cap (finding #3, option (c)), role_boost
        # is min(role_boost_cap, headroom) rather than a fixed 0.12 budget.
        # Here trend_shift is NOT maxed (composite_score ~0.19, below the
        # 0.22 threshold for a fully-maxed trend_shift), so there's more
        # headroom than in test_role_change_boost_is_capped, but still
        # slightly less than the nominal 0.12: trend_shift computes to
        # ~0.12075, so available_headroom = 0.85 - 0.625 - 0.12075 ~= 0.10425,
        # which is < role_boost_cap (0.12), so role_boost ~= 0.10425 (verified
        # by running compute_trend_profile directly against this scenario).
        # This still demonstrates the boost reaching close to its cap for a
        # realistic moderate-growth player — just no longer exactly capped at
        # 0.12, since headroom (not the nominal cap alone) is now the
        # binding constraint even in this non-fully-maxed case.
        self.assertGreater(trend_profile["role_score"], 0.19)
        self.assertLess(trend_profile["role_score"], 0.25)
        self.assertGreaterEqual(trend_profile["role_boost"], 0.10)
        self.assertAlmostEqual(trend_profile["role_boost"], 0.10424981314199067, places=6)

    def test_role_boost_never_forces_truncation_past_recent_weight_max(self) -> None:
        # Regression test for finding #3 of the whole-branch review
        # (docs/superpowers/specs/2026-08-12-role-growth-calibration-
        # followup-research.md). Real diagnostics (TREND_ROLE_BOOST /
        # TREND_SHIFT, exposed on this branch) showed Josh Hart, Dyson
        # Daniels, and Amen Thompson all had trend_shift == 0.14 (fully
        # maxed) and nominal role_boost == 0.12 (fully saturated), whose sum
        # with base_weights[0] (0.625) is 0.885 — silently truncated to
        # RECENT_WEIGHT_MAX (0.85) by _rebalance_recent_weight before this
        # fix, discarding 0.035 of the calibrated boost unpredictably. This
        # scenario reproduces that shape: composite_score and role_score
        # both clip to their maxima, so trend_shift maxes at 0.14 and the
        # role_score/ROLE_BOOST_SATURATION ratio saturates to 1.0.
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

        self.assertAlmostEqual(trend_profile["trend_shift"], 0.14, places=6)

        base_weight = 0.625
        desired_recent_weight = (
            base_weight + trend_profile["trend_shift"] + trend_profile["role_boost"]
        )

        # The whole point of the fix: no truncation is needed downstream
        # because desired_recent_weight never exceeds RECENT_WEIGHT_MAX
        # through this path in the first place.
        self.assertLessEqual(desired_recent_weight, RECENT_WEIGHT_MAX)
        self.assertAlmostEqual(desired_recent_weight, RECENT_WEIGHT_MAX, places=6)

        # role_boost adapted down from the nominal cap (0.12) rather than
        # being silently clamped elsewhere — proving the headroom-aware cap
        # fired, not just that the old clamp happened to land at the same
        # place.
        nominal_role_boost_cap = 0.12
        self.assertLess(trend_profile["role_boost"], nominal_role_boost_cap)
        self.assertGreater(trend_profile["role_boost"], 0.0)

    def test_project_stats_row_exposes_trend_profile_values(self) -> None:
        # Same player shape as test_role_change_boost_is_capped, but built as
        # full season DataFrames so we can run it through project_stats() and
        # confirm the row's TREND_* fields match compute_trend_profile()'s
        # direct output for the same input — a plumbing regression guard.
        season_recent = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Breakout Player",
                    "AGE": 24,
                    "GP": 82,
                    "MIN": 36.0,
                    "FGM": 9.0,
                    "FGA": 18.0,
                    "FG%": 0.500,
                    "3PTM": 2.8,
                    "FTM": 4.0,
                    "PTS": 24.0,
                    "REB": 7.0,
                    "AST": 8.0,
                    "ST": 1.6,
                    "BLK": 0.9,
                    "TO": 2.5,
                    "PF": 2.0,
                }
            ]
        )
        season_prior = pd.DataFrame(
            [
                {
                    "PLAYER_NAME": "Breakout Player",
                    "AGE": 23,
                    "GP": 82,
                    "MIN": 21.0,
                    "FGM": 4.0,
                    "FGA": 9.0,
                    "FG%": 0.444,
                    "3PTM": 1.0,
                    "FTM": 2.0,
                    "PTS": 10.0,
                    "REB": 3.0,
                    "AST": 3.0,
                    "ST": 0.7,
                    "BLK": 0.4,
                    "TO": 1.2,
                    "PF": 1.6,
                }
            ]
        )

        projected = project_stats(
            season_dfs=[season_recent, season_prior],
            weights=[0.625, 0.375],
            derived_stats={},
            tech_per_game={},
            seasons=["2024-25", "2023-24"],
        )

        row = projected.loc[projected["PLAYER_NAME"] == "Breakout Player"].iloc[0]

        expected_trend_profile = compute_trend_profile(
            player_season_stats={
                "2024-25": season_recent.iloc[0],
                "2023-24": season_prior.iloc[0],
            },
            available_seasons=["2024-25", "2023-24"],
            base_weights=[0.625, 0.375],
        )

        self.assertAlmostEqual(
            row["TREND_ROLE_SCORE"], round(float(expected_trend_profile["role_score"]), 3), places=6
        )
        self.assertAlmostEqual(
            row["TREND_ROLE_BOOST"], round(float(expected_trend_profile["role_boost"]), 3), places=6
        )
        self.assertAlmostEqual(
            row["TREND_SHIFT"], round(float(expected_trend_profile["trend_shift"]), 3), places=6
        )
        self.assertAlmostEqual(
            row["TREND_COMPOSITE_SCORE"], round(float(expected_trend_profile["composite_score"]), 3), places=6
        )
        self.assertGreater(row["TREND_ROLE_BOOST"], 0.0)

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


class AddWeekKeyTests(unittest.TestCase):
    def test_groups_dates_into_iso_weeks_without_mutating_input(self) -> None:
        logs = pd.DataFrame({"GAME_DATE": ["2026-01-05", "2026-01-07", "2026-01-12"],
                             "PTS": [10, 20, 30]})
        result = add_week_key(logs)
        self.assertEqual(list(result["WEEK_KEY"]), ["2026_2", "2026_2", "2026_3"])
        self.assertNotIn("WEEK_KEY", logs.columns)

    def test_iso_year_differs_from_calendar_year_at_new_year(self) -> None:
        logs = pd.DataFrame({"GAME_DATE": ["2025-12-30"], "PTS": [5]})
        result = add_week_key(logs)
        self.assertEqual(result.loc[0, "WEEK_KEY"], "2026_1")


if __name__ == "__main__":
    unittest.main()
