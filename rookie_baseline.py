"""
rookie_baseline.py — Two-stage rookie production model (pick curve + combine residual)
=========================================================================================
Stage 1: a continuous pick-slot curve (value = slope * ln(overall_pick) +
intercept per category), fit once from the 3 most recent completed draft
classes. Stage 2: a ridge-regularized residual adjustment from NBA Draft
Combine measurements, included only for categories where leave-one-class-
out cross-validation showed it actually reduces error (see
run_leave_one_class_out_cv). Fitted coefficients live in the auto-generated
rookie_baseline_fitted.py -- regenerate via scripts/build_rookie_baseline.py
after a new draft class completes its rookie season.

See docs/superpowers/specs/2026-10-04-rookie-baseline-combine-regression-design.md
for the full design rationale.
"""

import math

import numpy as np
import pandas as pd

from identity import canonical_player_key

CATEGORIES = [
    "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF",
    "FGM", "FGA", "FG%", "3PTM", "FTM",
]

TECH_DEFAULT = 0.05   # matches data.py:fetch_tech_per_game's own fallback estimate


def fit_stage1_curve(rows: list[dict]) -> dict[str, dict[str, float]]:
    """
    Fit value = slope * ln(overall_pick) + intercept per category via
    ordinary least squares, over every row with a real "actual" (rows with
    actual=None -- no rookie-season data yet -- are skipped).
    """
    usable = [r for r in rows if r["actual"] is not None]
    picks = np.array([r["overall_pick"] for r in usable], dtype=float)
    ln_picks = np.log(picks)

    coeffs: dict[str, dict[str, float]] = {}
    for category in CATEGORIES:
        values = np.array([r["actual"][category] for r in usable], dtype=float)
        slope, intercept = np.polyfit(ln_picks, values, deg=1)
        coeffs[category] = {"slope": float(slope), "intercept": float(intercept)}
    return coeffs


def predict_stage1(stage1_coeffs: dict[str, dict[str, float]], category: str, overall_pick: int) -> float:
    params = stage1_coeffs[category]
    return params["slope"] * math.log(overall_pick) + params["intercept"]


CURATED_COMBINE_FEATURES = [
    "WINGSPAN", "WEIGHT", "MAX_VERTICAL_LEAP", "LANE_AGILITY_TIME",
    "THREE_QUARTER_SPRINT",
]


def extract_combine_features(raw_combine_row: dict[str, float] | None) -> dict[str, float] | None:
    """
    Reduce a raw combine row (data.py's COMBINE_RAW_COLUMNS) to the 5
    curated Stage 2 features, or None if the player can't be scored --
    triggers the Stage-1-only fallback (see predict_rookie_stats). Every
    field is required -- each is an irreplaceable single measurement, not
    an aggregate that tolerates partial data.
    """
    if raw_combine_row is None:
        return None

    for field in CURATED_COMBINE_FEATURES:
        value = raw_combine_row.get(field)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None

    return {field: float(raw_combine_row[field]) for field in CURATED_COMBINE_FEATURES}


def fit_stage2_ridge(rows: list[dict], stage1_coeffs: dict[str, dict[str, float]],
                     lam: float) -> dict[str, dict]:
    """
    Ridge-regress each category's Stage 1 residual (actual - Stage 1
    prediction) against the 5 standardized CURATED_COMBINE_FEATURES, via
    the closed-form solution beta = (X'X + lam*I)^-1 X'r. Only rows with
    both a real "actual" and complete combine_features (see
    extract_combine_features) are used.
    """
    usable = [r for r in rows if r["actual"] is not None and r["combine_features"] is not None]
    if not usable:
        return {}

    X_raw = np.array(
        [[r["combine_features"][f] for f in CURATED_COMBINE_FEATURES] for r in usable],
        dtype=float,
    )
    feature_mean = X_raw.mean(axis=0)
    feature_std = X_raw.std(axis=0, ddof=0)
    feature_std = np.where(feature_std == 0, 1.0, feature_std)
    X = (X_raw - feature_mean) / feature_std
    identity = np.eye(X.shape[1])

    params: dict[str, dict] = {}
    for category in CATEGORIES:
        residuals = np.array([
            r["actual"][category] - predict_stage1(stage1_coeffs, category, r["overall_pick"])
            for r in usable
        ], dtype=float)
        beta = np.linalg.solve(X.T @ X + lam * identity, X.T @ residuals)
        params[category] = {
            "beta": beta.tolist(),
            "feature_mean": feature_mean.tolist(),
            "feature_std": feature_std.tolist(),
            "lambda": lam,
        }
    return params


def predict_stage2_residual(stage2_params: dict[str, dict], category: str,
                            combine_features: dict[str, float]) -> float:
    params = stage2_params[category]
    x = np.array([combine_features[f] for f in CURATED_COMBINE_FEATURES], dtype=float)
    x_std = (x - np.array(params["feature_mean"])) / np.array(params["feature_std"])
    return float(np.dot(x_std, params["beta"]))


LAMBDA_GRID = [1.0, 3.0, 10.0, 30.0, 100.0]


def run_leave_one_class_out_cv(rows_by_class: dict[str, list[dict]],
                               lambda_grid: list[float] = LAMBDA_GRID) -> dict[str, dict]:
    """
    Leave-one-draft-class-out cross-validation: train on all classes but
    one, predict the held-out class's real rookie-season production,
    rotate through every class. Per category, reports whether adding the
    Stage 2 combine-residual term (at whichever lambda in lambda_grid
    minimizes pooled MAE across all 3 folds) beats Stage 1 alone -- a
    category only gets stage2_included=True if the combined MAE is
    strictly lower, not merely tied (the simpler model wins ties).
    """
    classes = list(rows_by_class.keys())
    report: dict[str, dict] = {}

    for category in CATEGORIES:
        stage1_only_errors: list[float] = []
        combined_errors_by_lambda: dict[float, list[float]] = {lam: [] for lam in lambda_grid}

        for test_class in classes:
            train_rows = [r for c in classes if c != test_class for r in rows_by_class[c]]
            test_rows = [r for r in rows_by_class[test_class] if r["actual"] is not None]

            stage1_coeffs = fit_stage1_curve(train_rows)

            for r in test_rows:
                if r["combine_features"] is None:
                    continue
                pred1 = predict_stage1(stage1_coeffs, category, r["overall_pick"])
                stage1_only_errors.append(abs(pred1 - r["actual"][category]))

            for lam in lambda_grid:
                stage2_params = fit_stage2_ridge(train_rows, stage1_coeffs, lam)
                if category not in stage2_params:
                    continue
                for r in test_rows:
                    if r["combine_features"] is None:
                        continue
                    pred1 = predict_stage1(stage1_coeffs, category, r["overall_pick"])
                    pred2 = predict_stage2_residual(stage2_params, category, r["combine_features"])
                    combined_errors_by_lambda[lam].append(abs(pred1 + pred2 - r["actual"][category]))

        stage1_only_mae = float(np.mean(stage1_only_errors)) if stage1_only_errors else float("nan")

        best_lambda = None
        best_combined_mae = None
        for lam, errors in combined_errors_by_lambda.items():
            if not errors:
                continue
            mae = float(np.mean(errors))
            if best_combined_mae is None or mae < best_combined_mae:
                best_combined_mae = mae
                best_lambda = lam

        # Require a 2% relative margin, not just a bare "<" win: with the
        # row-set mismatch fixed (both MAEs now measured over the same
        # combine-complete rows), many categories' margins shrink to
        # well under 1% -- noise, not signal. The 2% margin subsumes the
        # old math.isclose tie-guard (anything within 2% is exactly the
        # kind of noise-level "win" that guard was built to catch).
        stage2_included = (
            best_combined_mae is not None
            and best_combined_mae < stage1_only_mae * 0.98
        )
        report[category] = {
            "stage1_only_mae": stage1_only_mae,
            "best_combined_mae": best_combined_mae,
            "chosen_lambda": best_lambda if stage2_included else None,
            "stage2_included": stage2_included,
        }

    return report


def predict_rookie_stats(fitted_model: dict, overall_pick: int,
                         combine_features: dict[str, float] | None) -> dict[str, float]:
    """
    Final per-rookie prediction: Stage 1 (pick curve) plus Stage 2's
    combine-residual adjustment, for whichever categories the leave-one-
    class-out CV (run_leave_one_class_out_cv) found it actually helps.
    Falls back to Stage 1 alone when combine_features is None (player has
    no complete combine record -- see extract_combine_features) or for any
    category CV didn't select Stage 2 for.
    """
    stage1_coeffs = fitted_model["stage1"]
    stage2_params = fitted_model["stage2"]

    result: dict[str, float] = {}
    for category in CATEGORIES:
        value = predict_stage1(stage1_coeffs, category, overall_pick)
        if combine_features is not None and category in stage2_params:
            value += predict_stage2_residual(stage2_params, category, combine_features)
        if category == "GP":
            value = min(value, 82.0)
        if category in ("PTS", "REB", "AST", "ST", "BLK", "TO", "PF",
                        "FGM", "FGA", "3PTM", "FTM", "MIN"):
            value = max(value, 0.0)
        result[category] = value

    result["DD"] = 0.0
    result["TD"] = 0.0
    result["TECH"] = TECH_DEFAULT
    return result


ROOKIE_ROW_COLUMNS = [
    "PLAYER_NAME", "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK",
    "TO", "PF", "FGM", "FGA", "FG%", "3PTM", "FTM", "DD", "TD", "TECH",
    "OVERALL_PICK",
]


def build_rookie_rows(draft_history: dict[str, dict], combine_stats: dict[str, dict],
                      fitted_model: dict, existing_players: set[str]) -> pd.DataFrame:
    """
    Build synthetic projection rows for drafted players (picks 1-60) with
    no prior NBA history, from the fitted two-stage regression model.

    Skips any player already present in existing_players (matched via
    canonical_player_key) and any pick outside 1-60 (undrafted/out of
    range -- not modeled, same scope as the original MVP).
    """
    existing_keys = {canonical_player_key(name) for name in existing_players}

    rows = []
    for player_name, pick_info in draft_history.items():
        if canonical_player_key(player_name) in existing_keys:
            continue

        overall_pick = pick_info["overall_pick"]
        if not (1 <= overall_pick <= 60):
            continue

        raw_combine = combine_stats.get(canonical_player_key(player_name))
        combine_features = extract_combine_features(raw_combine) if raw_combine is not None else None

        row = {"PLAYER_NAME": player_name}
        row.update(predict_rookie_stats(fitted_model, overall_pick, combine_features))
        row["OVERALL_PICK"] = overall_pick
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=ROOKIE_ROW_COLUMNS)

    return pd.DataFrame(rows)[ROOKIE_ROW_COLUMNS]
