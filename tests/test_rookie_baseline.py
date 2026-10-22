import math
import unittest

import pandas as pd

from rookie_baseline import (
    CATEGORIES,
    CURATED_COMBINE_FEATURES,
    TECH_DEFAULT,
    build_rookie_rows,
    extract_combine_features,
    fit_stage1_curve,
    fit_stage2_ridge,
    predict_rookie_stats,
    predict_stage1,
    predict_stage2_residual,
    run_leave_one_class_out_cv,
)


def _flat_fitted_model(value: float = 10.0) -> dict:
    # No pick/combine dependence at all -- every category predicts `value`
    # everywhere. Simplest possible fitted_model for testing build_rookie_rows'
    # plumbing without needing real Stage 1/2 numbers.
    return {
        "categories": CATEGORIES,
        "stage1": {cat: {"slope": 0.0, "intercept": value} for cat in CATEGORIES},
        "stage2": {},
    }


class PredictRookieStatsTests(unittest.TestCase):
    def test_stage1_only_when_combine_features_is_none(self) -> None:
        result = predict_rookie_stats(_flat_fitted_model(12.0), overall_pick=5, combine_features=None)
        for cat in CATEGORIES:
            self.assertAlmostEqual(result[cat], 12.0, places=9)

    def test_includes_dd_td_tech_flat_defaults(self) -> None:
        result = predict_rookie_stats(_flat_fitted_model(), overall_pick=1, combine_features=None)
        self.assertEqual(result["DD"], 0.0)
        self.assertEqual(result["TD"], 0.0)
        self.assertEqual(result["TECH"], TECH_DEFAULT)

    def test_stage2_residual_applied_when_category_included_and_features_present(self) -> None:
        fitted_model = _flat_fitted_model(10.0)
        fitted_model["stage2"] = {
            "PTS": {
                "beta": [1.0, 0.0, 0.0, 0.0, 0.0],
                "feature_mean": [80.0, 200.0, 32.0, 11.2, 3.25],
                "feature_std": [4.0, 20.0, 4.0, 0.5, 0.2],
                "lambda": 10.0,
            }
        }
        features = {
            "WINGSPAN": 84.0, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
            "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
        }
        result = predict_rookie_stats(fitted_model, overall_pick=1, combine_features=features)
        # standardized WINGSPAN = (84-80)/4 = 1.0, beta[0]=1.0 -> residual = 1.0
        self.assertAlmostEqual(result["PTS"], 11.0, places=9)
        # REB has no stage2 entry -- stays at stage1-only 10.0
        self.assertAlmostEqual(result["REB"], 10.0, places=9)


class BuildRookieRowsTests(unittest.TestCase):
    def test_drafted_player_with_no_prior_history_gets_a_row(self) -> None:
        draft_history = {"AJ Dybantsa": {"overall_pick": 1, "round_number": 1, "person_id": 1, "draft_year": "2026"}}
        rows = build_rookie_rows(draft_history, combine_stats={}, fitted_model=_flat_fitted_model(13.5),
                                 existing_players=set())

        self.assertEqual(len(rows), 1)
        row = rows.iloc[0]
        self.assertEqual(row["PLAYER_NAME"], "AJ Dybantsa")
        self.assertAlmostEqual(row["PTS"], 13.5, places=9)

    def test_player_already_in_existing_players_is_skipped(self) -> None:
        draft_history = {"Cameron Boozer": {"overall_pick": 3, "round_number": 1, "person_id": 2, "draft_year": "2026"}}
        rows = build_rookie_rows(draft_history, combine_stats={}, fitted_model=_flat_fitted_model(),
                                 existing_players={"Cameron Boozer"})

        self.assertTrue(rows.empty)

    def test_matching_is_identity_aware_not_exact_string_only(self) -> None:
        draft_history = {"Bilal Coulibaly": {"overall_pick": 7, "round_number": 1, "person_id": 3, "draft_year": "2026"}}
        rows = build_rookie_rows(draft_history, combine_stats={}, fitted_model=_flat_fitted_model(),
                                 existing_players={"bilal coulibaly"})

        self.assertTrue(rows.empty)

    def test_undrafted_or_out_of_range_picks_are_excluded(self) -> None:
        draft_history = {
            "Second Rounder": {"overall_pick": 60, "round_number": 2, "person_id": 4, "draft_year": "2026"},
            "Out Of Range": {"overall_pick": 61, "round_number": 2, "person_id": 5, "draft_year": "2026"},
        }
        rows = build_rookie_rows(draft_history, combine_stats={}, fitted_model=_flat_fitted_model(),
                                 existing_players=set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["PLAYER_NAME"], "Second Rounder")

    def test_empty_draft_history_returns_empty_dataframe_with_expected_columns(self) -> None:
        rows = build_rookie_rows({}, combine_stats={}, fitted_model=_flat_fitted_model(), existing_players=set())

        self.assertTrue(rows.empty)
        expected_columns = {
            "PLAYER_NAME", "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK",
            "TO", "PF", "FGM", "FGA", "FG%", "3PTM", "FTM", "DD", "TD", "TECH",
            "OVERALL_PICK",
        }
        self.assertEqual(set(rows.columns), expected_columns)

    def test_player_with_combine_data_gets_stage2_adjustment(self) -> None:
        draft_history = {"Combine Guy": {"overall_pick": 1, "round_number": 1, "person_id": 6, "draft_year": "2026"}}
        combine_stats = {
            "combineguy": {
                "WINGSPAN": 84.0, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
                "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
            }
        }
        fitted_model = _flat_fitted_model(10.0)
        fitted_model["stage2"] = {
            "PTS": {
                "beta": [1.0, 0.0, 0.0, 0.0, 0.0],
                "feature_mean": [80.0, 200.0, 32.0, 11.2, 3.25],
                "feature_std": [4.0, 20.0, 4.0, 0.5, 0.2],
                "lambda": 10.0,
            }
        }
        rows = build_rookie_rows(draft_history, combine_stats=combine_stats, fitted_model=fitted_model,
                                 existing_players=set())
        self.assertAlmostEqual(rows.iloc[0]["PTS"], 11.0, places=9)


class Stage1Tests(unittest.TestCase):
    def test_fit_stage1_curve_recovers_exact_line_for_two_points(self) -> None:
        rows = [
            {"overall_pick": 1, "actual": {cat: 20.0 for cat in CATEGORIES}, "combine_features": None},
            {"overall_pick": 60, "actual": {cat: 2.0 for cat in CATEGORIES}, "combine_features": None},
        ]
        coeffs = fit_stage1_curve(rows)

        expected_slope = (2.0 - 20.0) / math.log(60)
        self.assertAlmostEqual(coeffs["PTS"]["slope"], expected_slope, places=6)
        self.assertAlmostEqual(coeffs["PTS"]["intercept"], 20.0, places=6)
        self.assertAlmostEqual(predict_stage1(coeffs, "PTS", 1), 20.0, places=6)
        self.assertAlmostEqual(predict_stage1(coeffs, "PTS", 60), 2.0, places=6)

    def test_fit_stage1_curve_skips_rows_with_no_actual(self) -> None:
        rows = [
            {"overall_pick": 1, "actual": {cat: 20.0 for cat in CATEGORIES}, "combine_features": None},
            {"overall_pick": 60, "actual": {cat: 2.0 for cat in CATEGORIES}, "combine_features": None},
            {"overall_pick": 30, "actual": None, "combine_features": None},
        ]
        coeffs_with_junk = fit_stage1_curve(rows)
        coeffs_clean = fit_stage1_curve(rows[:2])
        self.assertAlmostEqual(coeffs_with_junk["PTS"]["slope"], coeffs_clean["PTS"]["slope"], places=9)

    def test_fit_stage1_curve_covers_every_category(self) -> None:
        rows = [
            {"overall_pick": 1, "actual": {cat: 20.0 for cat in CATEGORIES}, "combine_features": None},
            {"overall_pick": 60, "actual": {cat: 2.0 for cat in CATEGORIES}, "combine_features": None},
        ]
        coeffs = fit_stage1_curve(rows)
        self.assertEqual(set(coeffs.keys()), set(CATEGORIES))


class ExtractCombineFeaturesTests(unittest.TestCase):
    COMPLETE_ROW = {
        "WINGSPAN": 84.0, "WEIGHT": 220.0, "MAX_VERTICAL_LEAP": 36.0,
        "LANE_AGILITY_TIME": 11.0, "THREE_QUARTER_SPRINT": 3.2,
    }

    def test_none_input_returns_none(self) -> None:
        self.assertIsNone(extract_combine_features(None))

    def test_complete_row_returns_all_five_curated_features(self) -> None:
        features = extract_combine_features(self.COMPLETE_ROW)
        self.assertEqual(set(features.keys()), set(CURATED_COMBINE_FEATURES))
        self.assertAlmostEqual(features["WINGSPAN"], 84.0)
        self.assertAlmostEqual(features["THREE_QUARTER_SPRINT"], 3.2)

    def test_missing_field_returns_none(self) -> None:
        row = dict(self.COMPLETE_ROW)
        row["WINGSPAN"] = float("nan")
        self.assertIsNone(extract_combine_features(row))

    def test_field_absent_entirely_returns_none(self) -> None:
        row = dict(self.COMPLETE_ROW)
        del row["LANE_AGILITY_TIME"]
        self.assertIsNone(extract_combine_features(row))


class Stage2Tests(unittest.TestCase):
    def _row(self, pick: int, wingspan: float) -> dict:
        return {
            "overall_pick": pick,
            "actual": {cat: 10.0 for cat in CATEGORIES},
            "combine_features": {
                "WINGSPAN": wingspan, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
                "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
            },
        }

    def test_zero_residual_gives_zero_beta(self) -> None:
        # Stage 1 (slope=0, intercept=10) already predicts every row's
        # actual (10.0) exactly, for every category -- the residual is
        # exactly zero regardless of how WINGSPAN varies, so ridge must
        # recover an exactly-zero beta.
        stage1_coeffs = {cat: {"slope": 0.0, "intercept": 10.0} for cat in CATEGORIES}
        rows = [self._row(1, 78.0), self._row(10, 84.0), self._row(30, 78.0)]

        stage2 = fit_stage2_ridge(rows, stage1_coeffs, lam=10.0)

        for coef in stage2["PTS"]["beta"]:
            self.assertAlmostEqual(coef, 0.0, places=6)

    def test_predict_stage2_residual_matches_hand_computed_dot_product(self) -> None:
        stage2_params = {
            "PTS": {
                "beta": [1.0, 0.0, 0.0, 0.0, 2.0],
                "feature_mean": [80.0, 200.0, 32.0, 11.2, 3.25],
                "feature_std": [4.0, 20.0, 4.0, 0.5, 0.2],
                "lambda": 10.0,
            }
        }
        features = {
            "WINGSPAN": 84.0, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
            "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.65,
        }
        # standardized WINGSPAN = (84-80)/4 = 1.0, standardized THREE_QUARTER_SPRINT = (3.65-3.25)/0.2 = 2.0
        # dot product = 1.0*1.0 + 2.0*2.0 = 5.0
        result = predict_stage2_residual(stage2_params, "PTS", features)
        self.assertAlmostEqual(result, 5.0, places=9)

    def test_rows_missing_combine_features_are_excluded_from_the_fit(self) -> None:
        stage1_coeffs = {cat: {"slope": 0.0, "intercept": 10.0} for cat in CATEGORIES}
        rows = [self._row(1, 78.0), self._row(10, 84.0)]
        rows_with_junk = rows + [{"overall_pick": 30, "actual": {cat: 999.0 for cat in CATEGORIES}, "combine_features": None}]

        stage2_clean = fit_stage2_ridge(rows, stage1_coeffs, lam=10.0)
        stage2_with_junk = fit_stage2_ridge(rows_with_junk, stage1_coeffs, lam=10.0)
        for a, b in zip(stage2_clean["PTS"]["beta"], stage2_with_junk["PTS"]["beta"]):
            self.assertAlmostEqual(a, b, places=9)

    def test_fit_produces_hand_computed_beta_for_a_real_residual(self) -> None:
        # Only WINGSPAN varies; the other 4 features are held constant
        # across both rows, so their standardized columns are exactly
        # zero and must contribute nothing to beta, regardless of the
        # fit -- isolating the test to a single, hand-checkable dimension.
        stage1_coeffs = {cat: {"slope": 0.0, "intercept": 10.0} for cat in CATEGORIES}
        rows = [
            {
                "overall_pick": 1,
                "actual": {**{cat: 10.0 for cat in CATEGORIES}, "PTS": 7.0},
                "combine_features": {
                    "WINGSPAN": 78.0, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
                    "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
                },
            },
            {
                "overall_pick": 10,
                "actual": {**{cat: 10.0 for cat in CATEGORIES}, "PTS": 13.0},
                "combine_features": {
                    "WINGSPAN": 82.0, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
                    "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
                },
            },
        ]

        stage2 = fit_stage2_ridge(rows, stage1_coeffs, lam=10.0)

        # WINGSPAN mean=80, std=2.0 (ddof=0) -> standardized x = [-1.0, 1.0]
        # PTS residuals = actual - 10.0 = [-3.0, 3.0]
        # beta_wingspan = sum(x*r) / (sum(x^2) + lam) = ((-1*-3)+(1*3)) / (1+1+10) = 6/12 = 0.5
        beta = stage2["PTS"]["beta"]
        self.assertAlmostEqual(beta[0], 0.5, places=9)   # WINGSPAN
        self.assertAlmostEqual(beta[1], 0.0, places=9)   # WEIGHT (constant column)
        self.assertAlmostEqual(beta[2], 0.0, places=9)   # MAX_VERTICAL_LEAP (constant column)
        self.assertAlmostEqual(beta[3], 0.0, places=9)   # LANE_AGILITY_TIME (constant column)
        self.assertAlmostEqual(beta[4], 0.0, places=9)   # THREE_QUARTER_SPRINT (constant column)

        # Every other category had a residual of exactly zero (actual == stage1
        # prediction) -- their beta should be exactly zero too, same as the
        # existing zero-residual test, confirming the per-category loop is
        # correctly isolated.
        for coef in stage2["REB"]["beta"]:
            self.assertAlmostEqual(coef, 0.0, places=9)


class LeaveOneClassOutCVTests(unittest.TestCase):
    PICKS = [1, 10, 30, 60]
    # Deliberately NOT monotonic in pick order (unlike e.g. [78, 82, 85, 88]):
    # a wingspan that climbs in lockstep with pick is collinear with
    # ln(pick), which would confound Stage 1's pick-curve fit with the
    # wingspan effect this fixture means to isolate. Raw corr(WINGSPAN,
    # ln(pick)) is ~0.98 for the monotonic ordering vs. ~0.01 for the
    # shuffled ordering used here (verified). Shuffling the pairing breaks
    # that collinearity while keeping the same four real measurements.
    WINGSPANS = [82.0, 88.0, 78.0, 85.0]
    # Small per-class additive offsets (constant within a class, so they
    # carry zero correlation with the row-level WINGSPAN values, which
    # repeat identically across classes). These keep every non-PTS
    # category's held-out residual at a stable, well-above-float-epsilon
    # magnitude instead of a ~1e-15 rounding artifact that the 2% relative
    # margin can't reliably distinguish from a real win.
    CLASS_BIAS = {"A": 0.0, "B": 0.07, "C": -0.05}

    def _build_rows_by_class(self) -> dict[str, list[dict]]:
        rows_by_class: dict[str, list[dict]] = {}
        for cls in ("A", "B", "C"):
            rows = []
            bias = self.CLASS_BIAS[cls]
            for pick, wingspan in zip(self.PICKS, self.WINGSPANS):
                ln_pick = math.log(pick)
                rows.append({
                    "overall_pick": pick,
                    # PTS has a real, noiseless wingspan-correlated residual
                    # on top of the pick trend -- Stage 2 should earn its
                    # place here.
                    "actual": {
                        **{cat: 5.0 - 1.0 * ln_pick + bias for cat in CATEGORIES},
                        "PTS": 20.0 - 3.0 * ln_pick + 0.5 * (wingspan - 80.0),
                    },
                    "combine_features": {
                        "WINGSPAN": wingspan, "WEIGHT": 200.0, "MAX_VERTICAL_LEAP": 32.0,
                        "LANE_AGILITY_TIME": 11.2, "THREE_QUARTER_SPRINT": 3.25,
                    },
                })
            rows_by_class[cls] = rows
        return rows_by_class

    def test_stage2_included_for_category_with_real_combine_signal(self) -> None:
        report = run_leave_one_class_out_cv(self._build_rows_by_class(), [1.0, 3.0, 10.0, 30.0, 100.0])
        self.assertTrue(report["PTS"]["stage2_included"])
        self.assertLess(report["PTS"]["best_combined_mae"], report["PTS"]["stage1_only_mae"] * 0.5)

    def test_stage2_not_included_when_stage1_is_already_exact(self) -> None:
        # Every other category is a function of ln(pick) plus a per-class
        # constant bias -- stage1 trained on 2 classes can't see the
        # held-out class's bias, so held-out error is driven entirely by
        # that bias mismatch, not by anything correlated with WINGSPAN
        # (which is constant across classes, so it carries zero signal
        # about a between-class bias). Stage 2 has nothing real to find.
        report = run_leave_one_class_out_cv(self._build_rows_by_class(), [1.0, 3.0, 10.0, 30.0, 100.0])
        self.assertGreater(report["AST"]["stage1_only_mae"], 1e-6)
        self.assertFalse(report["AST"]["stage2_included"])


if __name__ == "__main__":
    unittest.main()
