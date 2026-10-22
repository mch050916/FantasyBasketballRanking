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
    compute_g_scores,
    compute_gp_factor,
    compute_kappa,
    compute_positional_value,
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

    def test_project_stats_excludes_injury_confirmed_season_via_cause_profile(self) -> None:
        season_recent = pd.DataFrame([{
            "PLAYER_NAME": "Hurt Guy", "AGE": 27, "GP": 30, "MIN": 30.0,
            "FGM": 5.0, "FGA": 10.0, "FG%": 0.500, "3PTM": 2.0, "FTM": 4.0,
            "PTS": 16.0, "REB": 5.0, "AST": 5.0, "ST": 1.0, "BLK": 0.5,
            "TO": 2.0, "PF": 2.0,
        }])
        season_mid = pd.DataFrame([{
            "PLAYER_NAME": "Hurt Guy", "AGE": 26, "GP": 82, "MIN": 30.0,
            "FGM": 5.0, "FGA": 10.0, "FG%": 0.500, "3PTM": 2.0, "FTM": 4.0,
            "PTS": 16.0, "REB": 5.0, "AST": 5.0, "ST": 1.0, "BLK": 0.5,
            "TO": 2.0, "PF": 2.0,
        }])
        season_prior = pd.DataFrame([{
            "PLAYER_NAME": "Hurt Guy", "AGE": 25, "GP": 82, "MIN": 30.0,
            "FGM": 5.0, "FGA": 10.0, "FG%": 0.500, "3PTM": 2.0, "FTM": 4.0,
            "PTS": 16.0, "REB": 5.0, "AST": 5.0, "ST": 1.0, "BLK": 0.5,
            "TO": 2.0, "PF": 2.0,
        }])

        without_profile = project_stats(
            season_dfs=[season_recent, season_mid, season_prior],
            weights=[0.5, 0.3, 0.2],
            derived_stats={},
            tech_per_game={},
            seasons=["2025-26", "2024-25", "2023-24"],
        )
        with_profile = project_stats(
            season_dfs=[season_recent, season_mid, season_prior],
            weights=[0.5, 0.3, 0.2],
            derived_stats={},
            tech_per_game={},
            seasons=["2025-26", "2024-25", "2023-24"],
            player_cause_profile={"Hurt Guy": {"2025-26": "injury_confirmed", "2024-25": "full_season", "2023-24": "full_season"}},
        )

        gp_factor_without = without_profile.iloc[0]["GP_FACTOR"]
        gp_factor_with = with_profile.iloc[0]["GP_FACTOR"]
        self.assertEqual(gp_factor_with, 1.0)
        self.assertGreater(gp_factor_with, gp_factor_without)


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


class ComputeGpFactorTests(unittest.TestCase):
    def test_unexplained_low_gp_season_behaves_identically_to_current_code(self) -> None:
        # Regression guard: no season_causes argument at all (the exact
        # call shape every existing caller uses today) must produce the
        # exact same factor as before this change -- zero behavior change
        # for the unexplained majority.
        player_season_stats = {
            "2024-25": pd.Series({"GP": 40}),
            "2023-24": pd.Series({"GP": 82}),
        }
        factor_without_causes_arg = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25", "2023-24"],
            weights=[0.6, 0.4],
        )
        factor_with_unexplained_causes = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25", "2023-24"],
            weights=[0.6, 0.4],
            season_causes={"2024-25": "unexplained", "2023-24": "full_season"},
        )
        self.assertEqual(factor_without_causes_arg, factor_with_unexplained_causes)
        # 0.6*40 + 0.4*82 = 56.8; 56.8/82 = 0.6927
        self.assertAlmostEqual(factor_without_causes_arg, 0.6927, places=3)

    def test_injury_confirmed_season_is_excluded_when_enough_seasons_remain(self) -> None:
        player_season_stats = {
            "2025-26": pd.Series({"GP": 40}),  # the injury-confirmed shortfall
            "2024-25": pd.Series({"GP": 82}),  # a clean full season
            "2023-24": pd.Series({"GP": 82}),  # a second clean full season
        }
        factor_with_injury_excluded = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2024-25", "2023-24"],
            weights=[0.5, 0.3, 0.2],
            season_causes={"2025-26": "injury_confirmed", "2024-25": "full_season", "2023-24": "full_season"},
        )
        factor_without_exclusion = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2024-25", "2023-24"],
            weights=[0.5, 0.3, 0.2],
        )
        # Excluding the confirmed-injury season leaves two clean 82-GP
        # seasons -> factor of 1.0, strictly higher than the blended
        # (lower) unmodified factor. 2 remaining seasons clears
        # MIN_REMAINING_SEASONS_AFTER_EXCLUSION, so the exclusion applies.
        self.assertEqual(factor_with_injury_excluded, 1.0)
        self.assertGreater(factor_with_injury_excluded, factor_without_exclusion)

    def test_injury_confirmed_exclusion_suppressed_when_it_would_leave_zero_seasons(self) -> None:
        # The guard suppresses the exclusion before it ever empties
        # gp_vals, so this returns the single season's own (unexcluded,
        # floor-clamped) factor, not the pre-existing "no gp_vals at all"
        # fallback of 1.0.
        player_season_stats = {"2024-25": pd.Series({"GP": 20})}
        factor = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2024-25"],
            weights=[1.0],
            season_causes={"2024-25": "injury_confirmed"},
        )
        # 20/82 = 0.2439, clipped to the 0.50 floor.
        self.assertEqual(factor, 0.50)

    def test_injury_confirmed_season_not_excluded_when_only_one_season_would_remain(self) -> None:
        # Real shape from the ADR-0001 validation gate: a player with
        # exactly 2 real seasons, one injury-confirmed. Excluding it would
        # leave only 1 remaining season -- below the 2-season guard -- so
        # this must NOT apply the exclusion: the result must be identical
        # to the unexcluded blend.
        player_season_stats = {
            "2025-26": pd.Series({"GP": 40}),
            "2023-24": pd.Series({"GP": 82}),
        }
        factor_with_causes = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2023-24"],
            weights=[0.6, 0.4],
            season_causes={"2025-26": "injury_confirmed", "2023-24": "full_season"},
        )
        factor_without_causes = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2023-24"],
            weights=[0.6, 0.4],
        )
        self.assertEqual(factor_with_causes, factor_without_causes)
        self.assertAlmostEqual(factor_with_causes, 0.6927, places=3)

    def test_unlabeled_synthetic_season_does_not_count_toward_remaining(self) -> None:
        # Real shape from the whole-branch review: Saddiq Bey has 2 real
        # seasons (one injury-confirmed) plus one synthetic GP=0 entry
        # for a season he's fully absent from (_missing_season_gp) --
        # causes.py never labels a synthetic season, so it must not
        # count toward "remaining" real seasons. Without this fix, the
        # guard would see 2 "remaining" entries (the 1 real non-injury
        # season + the unlabeled synthetic one) and wrongly apply the
        # exclusion, leaving only 1 real season actually backing the
        # blend -- exactly the pathology this guard exists to prevent.
        player_season_stats = {
            "2025-26": pd.Series({"GP": 72}),   # real, not injury-confirmed
            "2023-24": pd.Series({"GP": 63}),   # real, injury-confirmed
            "2024-25": pd.Series({"GP": 0}),    # synthetic _missing_season_gp entry
        }
        season_causes = {
            "2025-26": "unexplained",
            "2023-24": "injury_confirmed",
            # "2024-25" deliberately absent -- causes.py never labels a
            # season it has no real GP/team data for.
        }
        factor_with_causes = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2023-24", "2024-25"],
            weights=[0.5, 0.3, 0.2],
            season_causes=season_causes,
        )
        factor_without_causes = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2023-24", "2024-25"],
            weights=[0.5, 0.3, 0.2],
        )
        # Only 1 real labeled non-injury season ("2025-26") would remain
        # -- below MIN_REMAINING_SEASONS_AFTER_EXCLUSION -- so the
        # exclusion must be suppressed: identical to the unexcluded blend.
        self.assertEqual(factor_with_causes, factor_without_causes)

    def test_injury_confirmed_exclusion_can_lower_the_factor_too(self) -> None:
        # The exclusion removes a season because its cause is already
        # priced in elsewhere, not because it was a bad season -- if the
        # excluded season happens to be the player's BEST availability
        # data point, removing it can legitimately lower the factor.
        # Real shape: a player whose confirmed-injury season was their
        # highest-GP season of the three (e.g. Jerami Grant).
        player_season_stats = {
            "2025-26": pd.Series({"GP": 57}),  # injury-confirmed, but his best season
            "2024-25": pd.Series({"GP": 47}),
            "2023-24": pd.Series({"GP": 54}),
        }
        season_causes = {
            "2025-26": "injury_confirmed",
            "2024-25": "unexplained",
            "2023-24": "unexplained",
        }
        factor_with_exclusion = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2024-25", "2023-24"],
            weights=[0.5, 0.3, 0.2],
            season_causes=season_causes,
        )
        factor_without_exclusion = compute_gp_factor(
            player_season_stats=player_season_stats,
            available_seasons=["2025-26", "2024-25", "2023-24"],
            weights=[0.5, 0.3, 0.2],
        )
        # 2 real non-injury seasons remain (clears the guard floor), so
        # the exclusion applies -- and here it legitimately LOWERS the
        # factor, since the excluded season was the best of the three.
        self.assertLess(factor_with_exclusion, factor_without_exclusion)


class ComputePositionalValueTests(unittest.TestCase):
    def test_overflow_players_start_via_flex_and_util_before_bench(self) -> None:
        # 1 team, slots PG/G/Util (1 each) -- 4 PGs compete for 3 guard-
        # eligible slots. Highest value fills the dedicated PG slot first,
        # next fills the flex G slot, next fills Util, and the 4th is left
        # on the bench (below replacement).
        config = {
            "num_teams": 1,
            "roster_slots": ["PG", "G", "Util"],
        }
        df = pd.DataFrame([
            {"PLAYER_NAME": "P1", "POSITION": "PG", "TOTAL_VALUE": 10.0},
            {"PLAYER_NAME": "P2", "POSITION": "PG", "TOTAL_VALUE": 8.0},
            {"PLAYER_NAME": "P3", "POSITION": "PG", "TOTAL_VALUE": 6.0},
            {"PLAYER_NAME": "P4", "POSITION": "PG", "TOTAL_VALUE": 4.0},
        ])

        result = compute_positional_value(df, config)
        by_name = result.set_index("PLAYER_NAME")["POSITIONAL_VALUE"]

        # Replacement level = lowest TOTAL_VALUE among the 3 players who
        # actually started (P3, value 6) -- P1/P2/P3 all start (dedicated,
        # flex, Util in turn), P4 is pushed below replacement.
        self.assertAlmostEqual(by_name["P1"], 4.0)   # 10 - 6
        self.assertAlmostEqual(by_name["P3"], 0.0)   # 6 - 6 (at replacement)
        self.assertAlmostEqual(by_name["P4"], -2.0)  # 4 - 6 (benched)

    def test_position_with_no_flex_benches_sooner_than_one_with_flex(self) -> None:
        # 1 team, 1 dedicated slot each for PG/C, a flex G slot (PG-eligible,
        # not C-eligible), and no Util -- isolates the effect of PG having a
        # flex outlet while C has none.
        config = {
            "num_teams": 1,
            "roster_slots": ["PG", "G", "C"],
        }
        df = pd.DataFrame([
            {"PLAYER_NAME": "PG1", "POSITION": "PG", "TOTAL_VALUE": 10.0},
            {"PLAYER_NAME": "C1",  "POSITION": "C",  "TOTAL_VALUE": 9.0},
            {"PLAYER_NAME": "PG2", "POSITION": "PG", "TOTAL_VALUE": 5.0},
            {"PLAYER_NAME": "C2",  "POSITION": "C",  "TOTAL_VALUE": 4.0},
        ])

        result = compute_positional_value(df, config)
        by_name = result.set_index("PLAYER_NAME")["POSITIONAL_VALUE"]

        # PG2 starts via the G flex slot (replacement = 5, itself).
        # C2 has nowhere left to go once the single C slot is taken by C1
        # (no flex, no Util) -- benched, well below C's replacement (9).
        self.assertAlmostEqual(by_name["PG2"], 0.0)   # 5 - 5
        self.assertAlmostEqual(by_name["C2"], -5.0)   # 4 - 9


class ComputeGScoresPoolSizeTests(unittest.TestCase):
    def _make_projected(self, n_players: int) -> pd.DataFrame:
        cats = list(LEAGUE_CONFIG["categories"].keys())
        rows = []
        for i in range(n_players):
            row = {"PLAYER_NAME": f"Player {i}", "MIN": float(40 - i), "PTS": float(20 - i * 0.1), "FGA": float(10.0 + i)}
            for cat in cats:
                if cat not in row:
                    row[cat] = 1.0 + (i % 5) * 0.1
            rows.append(row)
        return pd.DataFrame(rows)

    def test_pool_size_none_matches_config_derived_default(self) -> None:
        projected = self._make_projected(LEAGUE_CONFIG["num_teams"] * LEAGUE_CONFIG["roster_size"] + 20)

        default_result = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG)
        explicit_result = compute_g_scores(
            projected, {}, {}, LEAGUE_CONFIG,
            pool_size=LEAGUE_CONFIG["num_teams"] * LEAGUE_CONFIG["roster_size"],
        )

        pd.testing.assert_frame_equal(default_result, explicit_result)

    def test_explicit_pool_size_includes_more_players_than_the_config_default(self) -> None:
        floor = LEAGUE_CONFIG["num_teams"] * LEAGUE_CONFIG["roster_size"]
        projected = self._make_projected(floor + 20)

        default_result = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG)
        widened_result = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG, pool_size=floor + 20)

        self.assertEqual(len(default_result), floor)
        self.assertEqual(len(widened_result), floor + 20)


class ComputeGScoresExtraRowsTests(unittest.TestCase):
    def _row(self, name: str, min_: float, pts: float) -> dict:
        cats = list(LEAGUE_CONFIG["categories"].keys())
        row = {"PLAYER_NAME": name, "MIN": min_, "PTS": pts, "FGA": 10.0}
        for cat in cats:
            if cat not in row:
                # Constant across every row (norm pool and extra alike) so
                # every category except PTS has zero variance and
                # contributes nothing to TOTAL_VALUE -- isolates the PTS
                # math for hand verification below.
                row[cat] = 1.0
        return row

    def test_norm_pool_total_value_identical_with_or_without_extra_rows(self) -> None:
        projected = pd.DataFrame([
            self._row("P0", 40.0, 20.0),
            self._row("P1", 39.0, 10.0),
            self._row("P2", 38.0, 0.0),
        ])
        extra_rows = pd.DataFrame([self._row("Extra", 5.0, -50.0)])

        without_extra = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG, pool_size=3)
        with_extra = compute_g_scores(
            projected, {}, {}, LEAGUE_CONFIG, pool_size=3, extra_rows=extra_rows,
        )

        norm_names = ["P0", "P1", "P2"]
        a = without_extra.set_index("PLAYER_NAME").loc[norm_names, "TOTAL_VALUE"].sort_index()
        b = with_extra.set_index("PLAYER_NAME").loc[norm_names, "TOTAL_VALUE"].sort_index()
        pd.testing.assert_series_equal(a, b)

    def test_extra_row_is_scored_against_the_fixed_norm_baseline(self) -> None:
        projected = pd.DataFrame([
            self._row("P0", 40.0, 20.0),
            self._row("P1", 39.0, 10.0),
            self._row("P2", 38.0, 0.0),
        ])
        extra_rows = pd.DataFrame([self._row("Extra", 5.0, 15.0)])

        result = compute_g_scores(
            projected, {}, {}, LEAGUE_CONFIG, pool_size=3, extra_rows=extra_rows,
        )

        self.assertIn("Extra", result["PLAYER_NAME"].values)
        self.assertEqual(len(result), 4)

        # Hand-computed expected PTS_G for "Extra" using ONLY the norm
        # pool's own PTS mean/sigma (10.0 / 8.1649...) -- not a mean/sigma
        # that includes Extra's own 15.0, which would be a different
        # (lower) number.
        kappa = compute_kappa(LEAGUE_CONFIG["roster_size"])
        norm_pts = np.array([20.0, 10.0, 0.0])
        mean, sigma = norm_pts.mean(), norm_pts.std()
        tau = 1.0  # default fallback: player_tau/league_tau both {}
        denom = np.sqrt(sigma ** 2 + kappa * tau ** 2)
        expected_pts_g = np.clip((15.0 - mean) / denom, -3.5, 3.5) * LEAGUE_CONFIG["category_weights"]["PTS"]

        extra_row = result[result["PLAYER_NAME"] == "Extra"].iloc[0]
        self.assertAlmostEqual(extra_row["PTS_G"], expected_pts_g)

    def test_extra_rows_none_is_unaffected(self) -> None:
        projected = pd.DataFrame([
            self._row("P0", 40.0, 20.0),
            self._row("P1", 39.0, 10.0),
            self._row("P2", 38.0, 0.0),
        ])

        implicit = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG, pool_size=3)
        explicit = compute_g_scores(projected, {}, {}, LEAGUE_CONFIG, pool_size=3, extra_rows=None)

        pd.testing.assert_frame_equal(implicit, explicit)


if __name__ == "__main__":
    unittest.main()
