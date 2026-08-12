"""
main.py — Run the DURANT ranking pipeline
==========================================
This is the entry point. Run it with:

    python main.py

To update for a new season:
  1. Download new Basketball Reference totals CSV and add to this folder
  2. Update BBR_FILES below to include the new season (most recent first)
  3. Update game_log_seasons in config.py
  4. Delete game_log_cache.pkl and tech_cache.pkl to force a fresh API fetch
  5. Run python main.py

Everything else is automatic.
"""

from pathlib import Path
from datetime import datetime

from benchmark_ingest import assess_benchmark_readiness, benchmark_snapshot_filename
from config   import LEAGUE_CONFIG
from data     import load_bbr_csv, filter_qualified, fetch_game_logs, \
                     fetch_tech_per_game, derive_stats_from_logs, \
                     build_non_actionable_suppression_report
from model    import project_stats, compute_tau, compute_g_scores
from output   import format_rankings, save_rankings
from validate import (
    append_benchmark_history,
    build_breakout_availability_summary,
    build_category_distortion_summary,
    build_validation_summary_row,
    compute_metric_deltas,
    find_previous_baseline,
    load_benchmark_history,
    print_metric_deltas,
    validate,
    write_analysis_artifact,
)


# ── Season data files — update this list each season ────────────────────────
# Most recent season first. Must match game_log_seasons in config.py.
BBR_FILES = [
    "basketball_reference_2024_25_total_stats.csv",
    "basketball_reference_2023_24_total_stats.csv",
]

OUTPUT_FILE     = "durant_rankings_2025_26.csv"
DIAGNOSTICS_DIR = Path("diagnostics")
BENCHMARK_HISTORY_FILE = DIAGNOSTICS_DIR / "benchmark_history.csv"
TOP_MISS_DIR = DIAGNOSTICS_DIR / "top_misses"
MILESTONE_CONTRIBUTION_DIR = DIAGNOSTICS_DIR / "milestone_contributions"
CATEGORY_DISTORTION_DIR = DIAGNOSTICS_DIR / "category_distortions"
CATEGORY_DISTORTION_SUMMARY_FILE = CATEGORY_DISTORTION_DIR / "category_distortion_summary.csv"
BREAKOUT_AVAILABILITY_DIR = DIAGNOSTICS_DIR / "breakout_availability"
BREAKOUT_AVAILABILITY_SUMMARY_FILE = BREAKOUT_AVAILABILITY_DIR / "breakout_availability_summary.csv"
SUPPRESSION_MAINTENANCE_FILE = DIAGNOSTICS_DIR / "non_actionable_suppression_maintenance.md"


def build_historical_snapshot_target(season: str, note: str) -> dict[str, object]:
    """Return one historical snapshot target using the canonical ingestion filename."""
    filename = benchmark_snapshot_filename(season)
    return {
        "path": filename,
        "label": filename,
        "benchmark_class": "historical_snapshot",
        "trust_tier": "snapshot_derived",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": note,
    }


VALIDATION_TARGETS = [
    build_historical_snapshot_target(
        "2025-26",
        "True holdout: our own preseason 2025-26 projections vs the completed season's exact-league result",
    ),
    build_historical_snapshot_target("2024-25", "14-cat exact-league validation snapshot for 2024-25"),
    build_historical_snapshot_target("2023-24", "14-cat exact-league validation snapshot for 2023-24"),
    {
        "path": "yahoo_25_26_market_export.csv",
        "label": "yahoo_25_26_adp_proxy",
        "benchmark_class": "direct_export_market",
        "trust_tier": "direct_export",
        "name_col": ["First Name", "Last Name"],
        "rank_col": "Avg. Pick",
        "rank_from_metric": True,
        "rank_metric_ascending": True,
        "note": "Market comparison only — lower Yahoo Avg. Pick is treated as a better preseason rank",
    },
    {
        "path": "yahoo_25_26_market_export.csv",
        "label": "yahoo_25_26_live_snapshot",
        "benchmark_class": "direct_export_live",
        "trust_tier": "direct_export",
        "name_col": ["First Name", "Last Name"],
        "rank_col": "OR",
        "note": "Live Yahoo season-to-date rank snapshot from the export's OR column",
    },
    {
        "path": "actual_9cat_24_25.csv",
        "label": "actual_9cat_24_25.csv",
        "benchmark_class": "directional_legacy",
        "trust_tier": "legacy_directional",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": "14-cat model vs 9-cat actual — directional comparison only",
    },
]


def slugify_label(label: str) -> str:
    """Build a deterministic filename-safe label slug."""
    chars = []
    for ch in label.lower():
        chars.append(ch if ch.isalnum() else "_")
    slug = "".join(chars)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def save_top_miss_artifact(result: dict[str, object]) -> None:
    """Persist the latest top-miss CSV for a benchmark target."""
    top_misses = result.get("top_misses")
    if top_misses is None or len(top_misses) == 0:
        return

    label = str(result.get("label", "benchmark"))
    path = TOP_MISS_DIR / f"{slugify_label(label)}_top_misses.csv"
    write_analysis_artifact(top_misses, path)
    print(f"  Miss artifact   : {path}")


def save_milestone_contribution_artifact(result: dict[str, object]) -> None:
    """Persist the latest DD/TD contribution artifact for a benchmark target."""
    artifact = result.get("milestone_contributions")
    if artifact is None or len(artifact) == 0:
        return

    label = str(result.get("label", "benchmark"))
    path = MILESTONE_CONTRIBUTION_DIR / f"{slugify_label(label)}_milestone_contributions.csv"
    write_analysis_artifact(artifact, path)
    print(f"  DD/TD artifact  : {path}")


def save_category_distortion_artifact(result: dict[str, object]) -> None:
    """Persist the latest family-level category-distortion artifact for a benchmark target."""
    artifact = result.get("category_distortions")
    if artifact is None or len(artifact) == 0:
        return

    label = str(result.get("label", "benchmark"))
    path = CATEGORY_DISTORTION_DIR / f"{slugify_label(label)}_category_distortions.csv"
    write_analysis_artifact(artifact, path)
    print(f"  Distortion artf : {path}")


def save_breakout_availability_artifact(result: dict[str, object]) -> None:
    """Persist the latest breakout/availability diagnostic artifact for a benchmark target."""
    artifact = result.get("breakout_availability")
    if artifact is None or len(artifact) == 0:
        return

    label = str(result.get("label", "benchmark"))
    path = BREAKOUT_AVAILABILITY_DIR / f"{slugify_label(label)}_breakout_availability.csv"
    write_analysis_artifact(artifact, path)
    print(f"  Breakout artf   : {path}")


def print_breakout_availability_summary(summary: object) -> None:
    """Render a compact cross-benchmark breakout/availability summary."""
    if summary is None or len(summary) == 0:
        return

    print(f"\n{'='*60}")
    print("Breakout / Availability Summary")
    print(f"{'='*60}")
    print("  Primary surface : exact-league 14-cat snapshots")

    for _, row in summary.iterrows():
        print(
            f"    {row['BREAKOUT_AVAILABILITY_LABEL']:<28} "
            f"{int(row['PRIMARY_HITS'])} primary hits / "
            f"{int(row['PRIMARY_BENCHMARKS'])} snapshots / "
            f"{int(row['SECONDARY_HITS'])} secondary"
        )
        print(f"      evidence: {row['EVIDENCE_LEVEL']}")
        if row["REPRESENTATIVE_PLAYERS"]:
            print(f"      reps: {row['REPRESENTATIVE_PLAYERS']}")
        if row["REPRESENTATIVE_REASONS"]:
            print(f"      reasons: {row['REPRESENTATIVE_REASONS']}")

    print(f"  Summary artifact: {BREAKOUT_AVAILABILITY_SUMMARY_FILE}")


def print_category_distortion_summary(summary: object) -> None:
    """Render a compact cross-benchmark category-distortion summary."""
    if summary is None or len(summary) == 0:
        return

    print(f"\n{'='*60}")
    print("Category Distortion Summary")
    print(f"{'='*60}")
    print("  Primary surface : exact-league 14-cat snapshots")

    real_families = summary[summary["EVIDENCE_LEVEL"] == "repeat_exact_league"]
    if real_families.empty:
        print("  Real families   : none yet")
    else:
        print("  Real families   :")
        for _, row in real_families.iterrows():
            print(
                f"    {row['DISTORTION_FAMILY']:<24} "
                f"{int(row['PRIMARY_HITS'])} hits / "
                f"{int(row['PRIMARY_BENCHMARKS'])} snapshots"
            )
            print(f"      reps: {row['REPRESENTATIVE_PLAYERS']}")
            print(f"      follow-up: {row['FOLLOW_UP_DECISION']}")

    supporting_families = summary[summary["EVIDENCE_LEVEL"] != "repeat_exact_league"]
    if not supporting_families.empty:
        print("  Supporting only :")
        for _, row in supporting_families.iterrows():
            print(
                f"    {row['DISTORTION_FAMILY']:<24} "
                f"{row['EVIDENCE_LEVEL']} / {row['FOLLOW_UP_DECISION']}"
            )

    print(f"  Summary artifact: {CATEGORY_DISTORTION_SUMMARY_FILE}")


def print_run_health_summary(game_log_health: dict[str, object],
                             validation_results: list[dict[str, object]]) -> None:
    print(f"\n{'='*60}")
    print("Run Health Summary")
    print(f"{'='*60}")

    if game_log_health["degraded"]:
        print("  Game-log fetch  : DEGRADED")
        print(f"  Missing pairs   : {game_log_health['missing_pair_count']} / {game_log_health['requested_pair_count']}")
        for player_name, season in game_log_health["missing_pairs"][:10]:
            print(f"    - {player_name} ({season})")
        extra = game_log_health["missing_pair_count"] - min(len(game_log_health["missing_pairs"]), 10)
        if extra > 0:
            print(f"    ... plus {extra} more missing pair(s)")
    else:
        print("  Game-log fetch  : OK")
        print(f"  Missing pairs   : 0 / {game_log_health['requested_pair_count']}")
    print(
        "  Severity split  : "
        f"{game_log_health['current_season_missing_pair_count']} current-season / "
        f"{game_log_health['historical_missing_pair_count']} historical / "
        f"{game_log_health['non_actionable_pair_count']} non-actionable"
    )
    if game_log_health["current_season_missing_pair_count"]:
        print("  Current-season  :")
        for player_name, season in game_log_health["current_season_missing_pairs"][:10]:
            print(f"    - {player_name} ({season})")
    if game_log_health["historical_missing_pair_count"]:
        print("  Historical      :")
        for player_name, season in game_log_health["historical_missing_pairs"][:10]:
            print(f"    - {player_name} ({season})")
    if game_log_health["non_actionable_pair_count"]:
        print("  Non-actionable  :")
        reasons = game_log_health.get("non_actionable_reasons", {})
        for player_name, season in game_log_health["non_actionable_pairs"][:10]:
            reason = reasons.get((player_name, season), "non-actionable")
            print(f"    - {player_name} ({season}): {reason}")
    if game_log_health["expected_missing_pair_count"]:
        print(f"  Expected misses : {game_log_health['expected_missing_pair_count']} suppressed")
    suppression_review = game_log_health.get("suppression_registry_review") or {}
    if suppression_review:
        print(
            "  Registry review : "
            f"{suppression_review.get('active_entry_count', 0)} active / "
            f"{suppression_review.get('expired_entry_count', 0)} expired / "
            f"{suppression_review.get('retired_entry_count', 0)} retired"
        )
        if suppression_review.get("expired_entries"):
            print("  Needs review    :")
            for entry in suppression_review["expired_entries"][:10]:
                print(f"    - {entry['Player Name']} ({entry['Season']}): reaffirm or retire")
        if game_log_health.get("suppression_maintenance_report"):
            print(f"  Maintenance rpt : {game_log_health['suppression_maintenance_report']}")

    ok_labels = [r["label"] for r in validation_results if r["status"] == "ok"]
    weak_labels = [r["label"] for r in validation_results if r["status"] == "weak_matches"]
    failed_labels = [r["label"] for r in validation_results if r["status"] == "no_matches"]
    not_ready_labels = [r["label"] for r in validation_results if r["status"] == "not_ready"]
    skipped_labels = [r["label"] for r in validation_results if r["status"] == "missing_file"]

    print("  Validation      :")
    print(f"    ok            : {len(ok_labels)}")
    print(f"    weak          : {len(weak_labels)}")
    print(f"    failed        : {len(failed_labels)}")
    print(f"    not_ready     : {len(not_ready_labels)}")
    print(f"    skipped       : {len(skipped_labels)}")

    if weak_labels:
        print(f"    weak targets  : {', '.join(weak_labels)}")
    if failed_labels:
        print(f"    failed targets: {', '.join(failed_labels)}")
    if not_ready_labels:
        print(f"    not ready     : {', '.join(not_ready_labels)}")
    if skipped_labels:
        print(f"    skipped files : {', '.join(skipped_labels)}")


def print_not_ready_benchmark(target: dict[str, object],
                              readiness: dict[str, object]) -> None:
    """Render a skipped screenshot-derived benchmark with explicit trust reasons."""
    print(f"\n{'='*60}")
    print(f"Validation vs {target.get('label', target['path'])}")
    if target.get("note"):
        print(f"  Note: {target['note']}")
    if target.get("benchmark_class"):
        print(f"  Benchmark class : {target['benchmark_class']}")
    if target.get("trust_tier"):
        print(f"  Trust tier      : {target['trust_tier']}")
    print("  Status          : not_ready")
    print("  Players matched : 0")
    if readiness.get("confidence_summary") is not None:
        file_confidence = readiness.get("file_confidence")
        if file_confidence is None:
            print(f"  Confidence      : {readiness['confidence_summary']}")
        else:
            print(f"  Confidence      : {readiness['confidence_summary']} ({float(file_confidence):.2f})")
    if readiness.get("source_batch"):
        print(f"  Source batch    : {readiness['source_batch']}")
    review_counts = readiness.get("review_counts") or {}
    if review_counts:
        print(
            "  Review counts   : "
            f"{review_counts.get('total', 0)} total / "
            f"{review_counts.get('approved', 0)} approved / "
            f"{review_counts.get('pending', 0)} pending / "
            f"{review_counts.get('rejected', 0)} rejected"
        )
    if readiness.get("generated_at"):
        print(f"  Generated at    : {readiness['generated_at']}")
    blockers = readiness.get("blocked_reasons") or []
    if blockers:
        print("  Skip reason     : " + "; ".join(str(reason) for reason in blockers))
    print(f"{'='*60}")


def main() -> None:
    print("DURANT Fantasy Basketball Ranker")
    print("=" * 60)

    config = LEAGUE_CONFIG

    # ── 1. Load BBR season data ──────────────────────────────────────────
    print("\n[1/5] Loading Basketball Reference season data...")

    raw_weights = config["season_weights"][:len(BBR_FILES)]
    total_w     = sum(raw_weights)
    weights     = [w / total_w for w in raw_weights]   # renormalise to sum=1

    season_dfs = []
    season_player_sets: list[set[str]] = []
    for path in BBR_FILES:
        raw_df = load_bbr_csv(path)
        season_player_sets.append(set(raw_df["PLAYER_NAME"]))
        df = filter_qualified(raw_df, config)
        season_dfs.append(df)
        print(f"   {path}: {len(df)} qualified players")

    # ── 2. Fetch game logs ───────────────────────────────────────────────
    print("\n[2/5] Fetching game logs (NBA API)...")

    # Only fetch logs for the top N players by minutes — the draftable pool.
    # Fetching all 400+ qualified players takes ~25 min and is unnecessary.
    limit      = config["game_log_player_limit"]
    top_recent = season_dfs[0].nlargest(limit, "MIN")["PLAYER_NAME"].tolist()

    # Add up to 20 players from the older season who may have missed last year
    # (e.g. injury returnees who are back for 2025-26)
    if len(season_dfs) > 1:
        older = season_dfs[1].nlargest(limit, "MIN")["PLAYER_NAME"].tolist()
        seen  = set(top_recent)
        extra = [n for n in older if n not in seen][:20]
    else:
        extra = []

    game_log_players = top_recent + extra
    expected_missing_pairs: set[tuple[str, str]] = set()
    if season_player_sets:
        recent_player_set = season_player_sets[0]
        for season, player_set in zip(config["game_log_seasons"][1:], season_player_sets[1:]):
            for player_name in game_log_players:
                if player_name in recent_player_set and player_name not in player_set:
                    expected_missing_pairs.add((player_name, season))
    print(f"   Fetching logs for {len(game_log_players)} players "
          f"(top {limit} by MIN + {len(extra)} returnees)")

    game_logs, game_log_health = fetch_game_logs(
        player_names=game_log_players,
        seasons=config["game_log_seasons"],
        cache_file=config["game_log_cache"],
        expected_missing_pairs=expected_missing_pairs,
        return_health=True,
    )
    SUPPRESSION_MAINTENANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUPPRESSION_MAINTENANCE_FILE.write_text(
        build_non_actionable_suppression_report(game_log_health),
        encoding="utf-8",
    )
    game_log_health["suppression_maintenance_report"] = str(SUPPRESSION_MAINTENANCE_FILE)

    # ── 3. Derive DD and TD from game logs ───────────────────────────────
    print("\n[3/5] Deriving DD/TD from game logs...")
    derived_stats = derive_stats_from_logs(game_logs)
    dd_count = sum(1 for v in derived_stats.values() if "DD" in v)
    print(f"   DD/TD derived for {dd_count} players")

    # ── 4. Fetch TECH + compute tau ──────────────────────────────────────
    print("\n[4/5] Fetching TECH stats + computing tau...")

    tech_per_game = fetch_tech_per_game(
        seasons=config["game_log_seasons"],
        cache_file=config["tech_cache"],
        season_weights=weights,
    )

    cat_names              = list(config["categories"].keys())
    player_tau, league_tau = compute_tau(game_logs, cat_names, weights)

    print(f"   Tau computed for {len(player_tau)} players")
    print(f"   League median tau per category:")
    for cat, tau in sorted(league_tau.items()):
        print(f"     {cat:<6} {tau:.3f}")

    # ── 5. Project stats and compute G-scores ────────────────────────────
    print("\n[5/5] Projecting stats and computing G-scores...")

    projected = project_stats(season_dfs, weights, derived_stats, tech_per_game, seasons=BBR_FILES)
    projected = projected.dropna(subset=["PTS"])
    print(f"   {len(projected)} players with projections")

    rankings = compute_g_scores(projected, player_tau, league_tau, config)

    # ── Output ───────────────────────────────────────────────────────────
    pool_size = config["num_teams"] * config["roster_size"]
    print(f"\n\nTOP 30 PLAYERS — 2025-26 PROJECTIONS")
    print(f"(pool: {pool_size} players | {config['num_teams']} teams × "
          f"{config['roster_size']} roster spots)")
    print(format_rankings(rankings, config, top_n=30))

    save_rankings(rankings, OUTPUT_FILE)

    # ── Validation ───────────────────────────────────────────────────────
    validation_results: list[dict[str, object]] = []
    history = load_benchmark_history(BENCHMARK_HISTORY_FILE)
    history_rows: list[dict[str, object]] = []
    recorded_at = datetime.now().isoformat(timespec="seconds")
    for target in VALIDATION_TARGETS:
        path = target["path"]
        if Path(path).exists():
            readiness = None
            if (
                target.get("benchmark_class") == "historical_snapshot"
                and target.get("trust_tier") == "snapshot_derived"
            ):
                readiness = assess_benchmark_readiness(path)
                if readiness is not None and not readiness.get("ready", False):
                    print_not_ready_benchmark(target, readiness)
                    validation_results.append(
                        {
                            "label": target.get("label", path),
                            "benchmark_class": target.get("benchmark_class"),
                            "trust_tier": target.get("trust_tier"),
                            "status": "not_ready",
                            "matched_players": 0,
                            "benchmark_metadata": readiness,
                        }
                    )
                    continue
            previous_baseline = find_previous_baseline(
                history,
                label=target.get("label", path),
                benchmark_class=target.get("benchmark_class"),
                trust_tier=target.get("trust_tier"),
            )
            result = validate(
                rankings,
                path,
                name_col=target.get("name_col", "Player Name"),
                rank_col=target.get("rank_col", "Rank"),
                rank_from_metric=target.get("rank_from_metric", False),
                rank_metric_ascending=target.get("rank_metric_ascending", True),
                label=target.get("label"),
                note=target.get("note"),
                benchmark_class=target.get("benchmark_class"),
                trust_tier=target.get("trust_tier"),
                benchmark_metadata=readiness,
            )
            result["baseline_deltas"] = compute_metric_deltas(result, previous_baseline)
            if previous_baseline is not None:
                print_metric_deltas(result["baseline_deltas"])
            else:
                print("\n  Baseline delta:")
                print("    first saved baseline for this benchmark")
            save_top_miss_artifact(result)
            save_milestone_contribution_artifact(result)
            save_category_distortion_artifact(result)
            save_breakout_availability_artifact(result)
            history_rows.append(build_validation_summary_row(result, recorded_at))
            validation_results.append(result)
        else:
            print(f"\n[skip] Validation file not found: {path}")
            validation_results.append(
                {
                    "label": target.get("label", path),
                    "benchmark_class": target.get("benchmark_class"),
                    "trust_tier": target.get("trust_tier"),
                    "status": "missing_file",
                    "matched_players": 0,
                }
            )

    append_benchmark_history(BENCHMARK_HISTORY_FILE, history_rows)
    category_distortion_summary = build_category_distortion_summary(validation_results)
    if len(category_distortion_summary) > 0:
        write_analysis_artifact(category_distortion_summary, CATEGORY_DISTORTION_SUMMARY_FILE)
        print_category_distortion_summary(category_distortion_summary)

    breakout_availability_summary = build_breakout_availability_summary(validation_results)
    if len(breakout_availability_summary) > 0:
        write_analysis_artifact(breakout_availability_summary, BREAKOUT_AVAILABILITY_SUMMARY_FILE)
        print_breakout_availability_summary(breakout_availability_summary)

    print_run_health_summary(game_log_health, validation_results)


if __name__ == "__main__":
    main()
