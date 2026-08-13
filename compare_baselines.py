"""
compare_baselines.py — Aggregate acceptance-criterion comparison
===================================================================
Prints aggregate Spearman + MAE across the three exact-league benchmarks
(2025-26, 2024-25, 2023-24) for two saved rankings snapshots, side by side.

These three benchmarks are the acceptance GATE for any model change.
Family-level diagnostics (e.g. an avg |delta| within a single miss family)
are useful for investigation but never decide whether a change ships — the
n within a single family is too small to be sensitive to real effect sizes
(see issue #1's role-growth tune, evaluated on n=6 role-growth-underreaction
hits, where the metric couldn't have detected success even if achieved).

Usage:
    # 1. Before making a change, save the current rankings as a baseline:
    cp durant_rankings_2025_26.csv diagnostics/baselines/before.csv

    # 2. Make the change, rerun the pipeline (regenerates durant_rankings_2025_26.csv)

    # 3. Compare:
    python compare_baselines.py --before diagnostics/baselines/before.csv \\
        --after durant_rankings_2025_26.csv

    # Optionally, flag deltas against a threshold declared in the plan doc
    # BEFORE the change was made:
    python compare_baselines.py --before before.csv --after after.csv \\
        --spearman-threshold 0.02 --mae-threshold 1.0

Threshold flags are optional and only used to flag/count deltas — they do
not ship the change for you. Whether a given delta is "meaningful," and
whether the resulting pattern of regressions/improvements clears your bar,
is the judgment call you declared in the plan doc. This script's job is to
make the pre-declared numbers checkable in one command, nothing more.

Bootstrap confidence estimation (see docs/adr/0001):

    # Part A — noise floor for a single rankings snapshot (how much Spearman/
    # MAE naturally wobble from sample composition alone, no comparison):
    python compare_baselines.py --noise-floor durant_rankings_2025_26.csv

    # Part B — paired bootstrap delta for a before/after comparison. Reports
    # the proportion of resampled deltas that improved, which is the number
    # to set a defensible "meaningful" threshold against — 95%+ improved is
    # a real signal even with a small point estimate, ~55% is noise:
    python compare_baselines.py --before before.csv --after after.csv --bootstrap

Both bootstrap modes accept --bootstrap-iterations (default 5000) and --seed
(default 42, for reproducibility).
"""
import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from main import VALIDATION_TARGETS
from validate import validate

EXACT_LEAGUE_BENCHMARK_CLASS = "historical_snapshot"
DEFAULT_BOOTSTRAP_ITERATIONS = 5000
DEFAULT_BOOTSTRAP_SEED = 42


def load_rankings(path: str) -> pd.DataFrame:
    """Load a saved rankings CSV, validating it has the columns validate() needs."""
    df = pd.read_csv(path)
    required = {"PLAYER_NAME", "RANK"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required column(s): {sorted(missing)}")
    return df


def exact_league_targets() -> list[dict[str, object]]:
    """Return the three exact-league benchmark definitions from VALIDATION_TARGETS."""
    return [
        target for target in VALIDATION_TARGETS
        if target.get("benchmark_class") == EXACT_LEAGUE_BENCHMARK_CLASS
    ]


def run_quiet(rankings: pd.DataFrame, target: dict[str, object]) -> dict[str, object]:
    """Run validate() for one target, suppressing its per-player console report."""
    with contextlib.redirect_stdout(io.StringIO()):
        return validate(
            rankings,
            target["path"],
            name_col=target.get("name_col", "Player Name"),
            rank_col=target.get("rank_col", "Rank"),
            rank_from_metric=target.get("rank_from_metric", False),
            rank_metric_ascending=target.get("rank_metric_ascending", True),
            rank_ceiling=target.get("rank_ceiling"),
            label=target.get("label"),
            benchmark_class=target.get("benchmark_class"),
            trust_tier=target.get("trust_tier"),
        )


def _summarize_samples(samples: np.ndarray) -> dict[str, float]:
    """Summarize a bootstrap sample array as mean/std/95% interval."""
    return {
        "mean": float(np.nanmean(samples)),
        "std": float(np.nanstd(samples, ddof=1)),
        "ci_low": float(np.nanpercentile(samples, 2.5)),
        "ci_high": float(np.nanpercentile(samples, 97.5)),
    }


def bootstrap_single_run(details: pd.DataFrame,
                         n_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
                         seed: int = DEFAULT_BOOTSTRAP_SEED) -> dict[str, object]:
    """
    Part A: bootstrap the noise floor for one run's matched-player set.

    Resamples matched players with replacement (n = original matched count),
    recomputes aggregate Spearman and MAE each time, and summarizes the
    resulting distributions. This is the wobble a single benchmark's numbers
    carry from sample composition alone, independent of any model change.
    """
    n = len(details)
    if n == 0:
        return {"n_matched": 0, "n_iterations": n_iterations, "spearman": None, "mae": None}

    rng = np.random.default_rng(seed)
    ranks = details["RANK"].to_numpy(dtype=float)
    actual = details["ACTUAL_RANK"].to_numpy(dtype=float)

    spearman_samples = np.empty(n_iterations)
    mae_samples = np.empty(n_iterations)
    for i in range(n_iterations):
        idx = rng.integers(0, n, size=n)
        r, a = ranks[idx], actual[idx]
        spearman_samples[i] = spearmanr(r, a).correlation
        mae_samples[i] = np.mean(np.abs(r - a))

    return {
        "n_matched": n,
        "n_iterations": n_iterations,
        "spearman": _summarize_samples(spearman_samples),
        "mae": _summarize_samples(mae_samples),
    }


def paired_bootstrap(before_details: pd.DataFrame, after_details: pd.DataFrame,
                     n_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
                     seed: int = DEFAULT_BOOTSTRAP_SEED) -> dict[str, object]:
    """
    Part B: paired bootstrap for a before/after comparison.

    Only players matched in BOTH runs are included, so the comparison is
    genuinely paired. Each iteration draws one set of indices and applies it
    to both sides, so the delta isolates the effect of the change itself
    rather than sampling noise from two independently-resampled sets —
    independent confidence bands overlap even when a change is real.
    """
    before_keys = set(before_details["PLAYER_KEY"])
    after_keys = set(after_details["PLAYER_KEY"])
    excluded_before_only = len(before_keys - after_keys)
    excluded_after_only = len(after_keys - before_keys)

    paired = pd.merge(
        before_details[["PLAYER_KEY", "RANK", "ACTUAL_RANK"]],
        after_details[["PLAYER_KEY", "RANK", "ACTUAL_RANK"]],
        on="PLAYER_KEY",
        suffixes=("_before", "_after"),
    )
    n = len(paired)
    if n == 0:
        return {
            "n_paired": 0,
            "n_iterations": n_iterations,
            "excluded_before_only": excluded_before_only,
            "excluded_after_only": excluded_after_only,
            "spearman_delta": None,
            "mae_delta": None,
        }

    rng = np.random.default_rng(seed)
    rank_before = paired["RANK_before"].to_numpy(dtype=float)
    rank_after = paired["RANK_after"].to_numpy(dtype=float)
    actual_before = paired["ACTUAL_RANK_before"].to_numpy(dtype=float)
    actual_after = paired["ACTUAL_RANK_after"].to_numpy(dtype=float)

    spearman_delta = np.empty(n_iterations)
    mae_delta = np.empty(n_iterations)
    for i in range(n_iterations):
        idx = rng.integers(0, n, size=n)
        sp_before = spearmanr(rank_before[idx], actual_before[idx]).correlation
        sp_after = spearmanr(rank_after[idx], actual_after[idx]).correlation
        spearman_delta[i] = sp_after - sp_before

        mae_before = np.mean(np.abs(rank_before[idx] - actual_before[idx]))
        mae_after = np.mean(np.abs(rank_after[idx] - actual_after[idx]))
        mae_delta[i] = mae_after - mae_before

    return {
        "n_paired": n,
        "n_iterations": n_iterations,
        "excluded_before_only": excluded_before_only,
        "excluded_after_only": excluded_after_only,
        "spearman_delta": {
            "median": float(np.nanmedian(spearman_delta)),
            "ci_low": float(np.nanpercentile(spearman_delta, 2.5)),
            "ci_high": float(np.nanpercentile(spearman_delta, 97.5)),
            # Spearman: higher is better, so "improved" means delta > 0.
            "pct_improved": float(np.mean(spearman_delta > 0) * 100),
        },
        "mae_delta": {
            "median": float(np.nanmedian(mae_delta)),
            "ci_low": float(np.nanpercentile(mae_delta, 2.5)),
            "ci_high": float(np.nanpercentile(mae_delta, 97.5)),
            # MAE: lower is better, so "improved" means delta < 0.
            "pct_improved": float(np.mean(mae_delta < 0) * 100),
        },
    }


def classify_season(sp_delta: float | None, mae_delta: float | None,
                     spearman_threshold: float | None, mae_threshold: float | None) -> str:
    """
    Classify one season as regressed/improved/neutral against declared thresholds.

    Regression takes priority: if either metric moves the wrong way beyond its
    threshold, the season counts as regressed even if the other metric improved —
    matching the "no meaningful regression on any" half of the acceptance shape.
    """
    regressed = (
        (spearman_threshold is not None and sp_delta is not None and sp_delta <= -spearman_threshold)
        or (mae_threshold is not None and mae_delta is not None and mae_delta >= mae_threshold)
    )
    if regressed:
        return "regressed"

    improved = (
        (spearman_threshold is not None and sp_delta is not None and sp_delta >= spearman_threshold)
        or (mae_threshold is not None and mae_delta is not None and mae_delta <= -mae_threshold)
    )
    return "improved" if improved else "neutral"


def compare(before: pd.DataFrame, after: pd.DataFrame,
            spearman_threshold: float | None, mae_threshold: float | None) -> None:
    targets = exact_league_targets()
    if not targets:
        print("No exact-league (historical_snapshot) benchmarks found in VALIDATION_TARGETS.")
        return

    thresholds_given = spearman_threshold is not None or mae_threshold is not None
    header = f"{'Season':<28}{'n':>5}  {'Spearman (before → after)':<28}{'MAE (before → after)':<24}"
    if thresholds_given:
        header += "flag"
    print(header)
    print("-" * len(header))

    regressed_count = 0
    improved_count = 0
    seasons_scored = 0

    for target in targets:
        path = target["path"]
        label = target.get("label", path)
        if not Path(path).exists():
            print(f"{label:<28}  [missing: {path}]")
            continue

        before_result = run_quiet(before, target)
        after_result = run_quiet(after, target)

        b_sp, a_sp = before_result.get("spearman"), after_result.get("spearman")
        b_mae, a_mae = before_result.get("mae"), after_result.get("mae")
        n = after_result.get("matched_players")

        sp_delta = (a_sp - b_sp) if b_sp is not None and a_sp is not None else None
        mae_delta = (a_mae - b_mae) if b_mae is not None and a_mae is not None else None

        sp_str = f"{b_sp:.3f} → {a_sp:.3f} ({sp_delta:+.3f})" if sp_delta is not None else "n/a"
        mae_str = f"{b_mae:.1f} → {a_mae:.1f} ({mae_delta:+.1f})" if mae_delta is not None else "n/a"

        row = f"{label:<28}{n:>5}  {sp_str:<28}{mae_str:<24}"
        if thresholds_given:
            status = classify_season(sp_delta, mae_delta, spearman_threshold, mae_threshold)
            seasons_scored += 1
            if status == "regressed":
                regressed_count += 1
                row += "REGRESSED"
            elif status == "improved":
                improved_count += 1
                row += "improved"
        print(row)

    if thresholds_given:
        print()
        print(f"Seasons regressed : {regressed_count}/{seasons_scored}")
        print(f"Seasons improved  : {improved_count}/{seasons_scored}")
        print("(Whether this pattern clears your declared acceptance shape is your call.)")


def print_noise_floor_report(rankings: pd.DataFrame,
                             n_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
                             seed: int = DEFAULT_BOOTSTRAP_SEED) -> None:
    """Part A: print the bootstrap noise floor for one rankings snapshot, per exact-league benchmark."""
    targets = exact_league_targets()
    if not targets:
        print("No exact-league (historical_snapshot) benchmarks found in VALIDATION_TARGETS.")
        return

    print(f"Bootstrap noise floor ({n_iterations} resamples, seed={seed})")
    print("=" * 78)

    for target in targets:
        path = target["path"]
        label = target.get("label", path)
        if not Path(path).exists():
            print(f"{label}: [missing: {path}]")
            continue

        result = run_quiet(rankings, target)
        details = result.get("details")
        if details is None or len(details) == 0:
            print(f"{label}: no matched players")
            continue

        boot = bootstrap_single_run(details, n_iterations=n_iterations, seed=seed)
        sp, mae = boot["spearman"], boot["mae"]

        print(f"\n{label} (n={boot['n_matched']})")
        print(f"  Spearman : mean={sp['mean']:.3f}  std={sp['std']:.3f}  "
              f"95% CI=[{sp['ci_low']:.3f}, {sp['ci_high']:.3f}]")
        print(f"  MAE      : mean={mae['mean']:.2f}  std={mae['std']:.2f}  "
              f"95% CI=[{mae['ci_low']:.2f}, {mae['ci_high']:.2f}]")


def print_paired_bootstrap_report(before: pd.DataFrame, after: pd.DataFrame,
                                  n_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
                                  seed: int = DEFAULT_BOOTSTRAP_SEED) -> None:
    """Part B: print the paired bootstrap delta report for a before/after comparison."""
    targets = exact_league_targets()
    if not targets:
        return

    print(f"\nPaired bootstrap delta ({n_iterations} resamples, seed={seed})")
    print("=" * 78)

    for target in targets:
        path = target["path"]
        label = target.get("label", path)
        if not Path(path).exists():
            continue

        before_details = run_quiet(before, target).get("details")
        after_details = run_quiet(after, target).get("details")
        if before_details is None or after_details is None or before_details.empty or after_details.empty:
            print(f"\n{label}: no matched players")
            continue

        boot = paired_bootstrap(before_details, after_details, n_iterations=n_iterations, seed=seed)
        if boot["n_paired"] == 0:
            print(f"\n{label}: no players matched in both runs")
            continue

        sp, mae = boot["spearman_delta"], boot["mae_delta"]
        excluded_before = boot["excluded_before_only"]
        excluded_after = boot["excluded_after_only"]
        excluded_total = excluded_before + excluded_after
        union = boot["n_paired"] + excluded_total

        print(f"\n{label} (n paired={boot['n_paired']})")
        if excluded_total > 0:
            # Its own line, not a header suffix — a shift in who qualifies
            # (e.g. availability shading moving someone across the GP/MPG
            # bar) shrinks the paired sample and quietly weakens the
            # comparison. That's worth noticing at the time, not later.
            excluded_pct = (excluded_total / union * 100) if union else 0.0
            flag = "  <- INVESTIGATE: qualifying player set shifted" if excluded_pct > 20.0 else ""
            print(f"  Excluded from pairing: {excluded_before} before-only, "
                  f"{excluded_after} after-only ({excluded_pct:.0f}% of the union){flag}")
        print(f"  Spearman delta : median={sp['median']:+.3f}  "
              f"95% CI=[{sp['ci_low']:+.3f}, {sp['ci_high']:+.3f}]  "
              f"improved in {sp['pct_improved']:.1f}% of resamples")
        print(f"  MAE delta      : median={mae['median']:+.2f}  "
              f"95% CI=[{mae['ci_low']:+.2f}, {mae['ci_high']:+.2f}]  "
              f"improved in {mae['pct_improved']:.1f}% of resamples")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare aggregate Spearman/MAE across the exact-league benchmarks for two rankings snapshots.",
    )
    parser.add_argument("--before", help="Rankings CSV before the change")
    parser.add_argument("--after", help="Rankings CSV after the change")
    parser.add_argument(
        "--noise-floor", metavar="RANKINGS_CSV",
        help="Report the Part-A bootstrap noise floor for a single rankings snapshot, then exit "
             "(ignores --before/--after)",
    )
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="Add the Part-B paired bootstrap delta report to the --before/--after comparison",
    )
    parser.add_argument(
        "--bootstrap-iterations", type=int, default=DEFAULT_BOOTSTRAP_ITERATIONS,
        help=f"Number of bootstrap resamples (default {DEFAULT_BOOTSTRAP_ITERATIONS})",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_BOOTSTRAP_SEED,
        help=f"Bootstrap random seed, for reproducibility (default {DEFAULT_BOOTSTRAP_SEED})",
    )
    parser.add_argument(
        "--spearman-threshold", type=float, default=None,
        help="Minimum |delta| for a season's Spearman move to count as regressed/improved",
    )
    parser.add_argument(
        "--mae-threshold", type=float, default=None,
        help="Minimum |delta| for a season's MAE move to count as regressed/improved",
    )
    args = parser.parse_args()

    if args.noise_floor:
        rankings = load_rankings(args.noise_floor)
        print_noise_floor_report(rankings, args.bootstrap_iterations, args.seed)
        return

    if not args.before or not args.after:
        parser.error("--before and --after are required unless --noise-floor is given")

    before = load_rankings(args.before)
    after = load_rankings(args.after)
    compare(before, after, args.spearman_threshold, args.mae_threshold)

    if args.bootstrap:
        print_paired_bootstrap_report(before, after, args.bootstrap_iterations, args.seed)


if __name__ == "__main__":
    main()
