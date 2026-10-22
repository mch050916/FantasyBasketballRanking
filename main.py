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

import pandas as pd

import causes

from benchmark_ingest import assess_benchmark_readiness, benchmark_snapshot_filename
from config   import LEAGUE_CONFIG
from data     import load_bbr_csv, filter_qualified, fetch_game_logs, \
                     fetch_tech_per_game, derive_stats_from_logs, \
                     build_non_actionable_suppression_report, fetch_draft_history, \
                     fetch_combine_stats, \
                     fetch_current_teams, detect_team_changes, \
                     fetch_injury_reports, summarize_season_injuries, reformat_lastfirst_name, \
                     classify_injury_tier_with_carryover, INJURY_TIER_YEAR1_DISCOUNT
from identity import canonical_player_key
from model    import project_stats, compute_tau, compute_g_scores, compute_positional_value
from output   import format_rankings, save_rankings
from rookie_baseline import build_rookie_rows
from rookie_baseline_fitted import FITTED_MODEL as ROOKIE_FITTED_MODEL
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
    "basketball_reference_2025_26_total_stats.csv",
    "basketball_reference_2024_25_total_stats.csv",
    "basketball_reference_2023_24_total_stats.csv",
]


def derive_projection_season_label(most_recent_completed_season: str) -> tuple[str, str]:
    """
    Derive the season being projected — one year after the most recent
    completed season — as (underscore_slug, dash_label), e.g.
    "2025-26" -> ("2026_27", "2026-27").

    Kept derived rather than hand-maintained so a rollover that updates
    BBR_FILES/game_log_seasons can't silently leave stale season labels in
    output filenames or console text (see CLAUDE.md, 2026-08-15 entry).
    """
    start_year = int(most_recent_completed_season.split("-")[0])
    next_start = start_year + 1
    next_end_suffix = str((next_start + 1) % 100).zfill(2)
    return f"{next_start}_{next_end_suffix}", f"{next_start}-{next_end_suffix}"


PROJECTION_SEASON_SLUG, PROJECTION_SEASON_LABEL = derive_projection_season_label(
    LEAGUE_CONFIG["game_log_seasons"][0]
)


def derive_pool_size(config: dict, qualified_pool: pd.DataFrame,
                     rosters_file: str = "rosters.csv", buffer: int = 30) -> int:
    # Deliberately unwired -- no caller in main(). Widening the pool to this
    # size regressed MAE on the ADR-0001 validation gate; kept as plumbing
    # for a future, better-scoped attempt. Do not re-wire without reading
    # the 2026-10-21 pool-size-widening final whole-branch review.
    # Superseded for the real fix by build_extra_rows (below) + compute_g_scores'
    # extra_rows param -- scores real rostered players outside the pool without
    # widening the normalization baseline this function's approach required.
    """
    Real-roster-aware pool size for compute_g_scores' nlargest truncation.

    At minimum num_teams*roster_size (today's flat ceiling). When
    `rosters_file` exists, grown to cover the deepest real rostered
    player's MIN rank in `qualified_pool` (the post-project_stats,
    pre-G-score population -- the exact population compute_g_scores itself
    ranks by MIN before truncating) plus `buffer` extra slots for in-season
    waiver-wire depth. Falls back to the flat floor pre-draft, or on a
    fresh checkout with no rosters.csv yet -- zero behavior change until a
    real roster exists.

    A rostered name that doesn't match anything in `qualified_pool` is
    silently skipped here -- it's not this function's job to raise on an
    unresolved name (resolve_roster_players, called elsewhere in the
    pipeline, already does that clearly).
    """
    floor = config["num_teams"] * config["roster_size"]

    rosters_path = Path(rosters_file)
    if not rosters_path.exists():
        return floor

    from rosters import load_rosters
    rostered_keys = {
        canonical_player_key(name)
        for players in load_rosters(rosters_file).values()
        for name in players
    }

    ranked = qualified_pool.sort_values("MIN", ascending=False).reset_index(drop=True)
    key_to_rank = {
        canonical_player_key(name): i + 1 for i, name in enumerate(ranked["PLAYER_NAME"])
    }

    deepest_rank = max(
        (key_to_rank[key] for key in rostered_keys if key in key_to_rank),
        default=0,
    )

    return max(floor, deepest_rank + buffer)


def build_extra_rows(projected: pd.DataFrame, pool_size: int,
                     rosters_file: str = "rosters.csv") -> pd.DataFrame:
    """
    Real rostered players outside compute_g_scores' normalization pool.

    Returns rows from `projected` (same schema) for every rostered player
    whose canonical name doesn't appear in the pool_size-truncated,
    MIN-ranked population compute_g_scores would otherwise limit itself to
    -- the exact population compute_g_scores' `extra_rows` parameter exists
    for: real drafted players scored against the pool's fixed normalization
    baseline instead of silently excluded (see model.py's docstring and
    the 2026-10-21 pool-size-widening final whole-branch review for why
    THIS is the narrow fix, not widening pool_size itself). Empty (same
    columns, zero rows) when `rosters_file` doesn't exist (pre-draft) or
    every rostered player is already inside the pool -- zero behavior
    change in either case.

    A rostered name that doesn't match anything in `projected` is silently
    skipped here, same convention as derive_pool_size -- it's not this
    function's job to raise on an unresolved name (resolve_roster_players,
    called elsewhere in the pipeline, already does that clearly).
    """
    rosters_path = Path(rosters_file)
    if not rosters_path.exists():
        return projected.iloc[0:0]

    from rosters import load_rosters
    rostered_keys = {
        canonical_player_key(name)
        for players in load_rosters(rosters_file).values()
        for name in players
    }

    pool = projected.dropna(subset=["PTS"]).nlargest(pool_size, "MIN")
    pool_keys = {canonical_player_key(name) for name in pool["PLAYER_NAME"]}
    missing_keys = rostered_keys - pool_keys

    name_keys = projected["PLAYER_NAME"].apply(canonical_player_key)
    return projected[name_keys.isin(missing_keys)].drop_duplicates(subset="PLAYER_NAME")


OUTPUT_FILE     = f"durant_rankings_{PROJECTION_SEASON_SLUG}.csv"
ROOKIE_OUTPUT_FILE = f"durant_rankings_rookies_{PROJECTION_SEASON_SLUG}.csv"
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
    {
        "path": benchmark_snapshot_filename("2026-27"),
        "label": benchmark_snapshot_filename("2026-27"),
        # Deliberately NOT "historical_snapshot" -- 2026-27 hasn't happened yet, so this
        # entry has no backing file and must stay out of exact_league_targets() in
        # compare_baselines.py (which assumes all "historical_snapshot" targets have real
        # data to paired-bootstrap against). It'll show up as "[skip] Validation file not
        # found" in main.py's own validation loop until the season completes and the
        # snapshot file is added -- that transition is the point.
        "benchmark_class": "pending_holdout",
        "trust_tier": "not_yet_available",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": "Live preseason holdout for 2026-27 -- not yet available; this season isn't "
        "in the model's input blend, so it will be the first genuine out-of-sample test "
        "once it completes. See docs/adr/0001-aggregate-acceptance-criterion.md's "
        "2026-08-15 note: every benchmark below is retrodictive, not held out.",
    },
    build_historical_snapshot_target("2025-26", "14-cat exact-league validation snapshot for 2025-26"),
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
        "rank_ceiling_from_pool_size": True,
        "note": "Live Yahoo season-to-date rank snapshot from the export's OR column. "
                "OR ranks across Yahoo's full rostered-player universe (~700 players), "
                "far larger than our own pool — rank_ceiling_from_pool_size caps the "
                "comparison to our pool size so rank deltas stay commensurate.",
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
    season_raw_gp: list[dict[str, int]] = []
    season_raw_team: list[dict[str, str]] = []
    position_by_player: dict[str, str] = {}
    for path in BBR_FILES:
        raw_df = load_bbr_csv(path)
        season_player_sets.append(set(raw_df["PLAYER_NAME"]))
        season_raw_gp.append(dict(zip(raw_df["PLAYER_NAME"], raw_df["GP"])))
        season_raw_team.append(dict(zip(raw_df["PLAYER_NAME"], raw_df["BBR_TEAM"])))
        # Newest season's position wins when a player appears in more than
        # one (setdefault, processed newest-first) -- position rarely
        # changes, but this also covers the issue #11 case where a player
        # is entirely absent from the newest BBR file (no position to read
        # there at all) by falling back to their last season with one.
        for name, position in zip(raw_df["PLAYER_NAME"], raw_df["POSITION"]):
            position_by_player.setdefault(name, position)
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

    # ── Recent severe injuries — fetched here, before projection, because
    # a confirmed injury-type match now feeds a real discount into
    # project_stats below (not just a display flag). Real NBA injury-report
    # data (body part + mechanism) for the pool's most recent loaded season
    # -- addresses the healthy-worker survivorship bias flagged around
    # GitHub issue #11: GP_FACTOR can see THAT a season was thin, never WHY.
    # Best-effort: needs a local Java runtime for nbainjuries' PDF parsing,
    # which may not be installed everywhere this pipeline runs.
    try:
        injury_reports = fetch_injury_reports(
            seasons=config["game_log_seasons"],
            cache_file=config["injury_reports_cache"],
        )
        all_season_injuries = summarize_season_injuries(injury_reports)
        season_injuries = all_season_injuries.get(config["game_log_seasons"][0], {})
        severe_injury_by_key = {
            canonical_player_key(reformat_lastfirst_name(name)): info["severe_reasons"]
            for name, info in season_injuries.items()
            if info["had_severe_injury"]
        }
        # One season back only -- a real diagnosis report (e.g. "ACL tear")
        # sometimes only appears in the season the injury actually happened
        # in, with the current season's own reports genericizing an ongoing
        # absence as just "Surgery" (see classify_injury_tier_with_carryover
        # in data.py). Used only to recover a tier when the current season's
        # text alone doesn't name one, gated on matching body-part location.
        prior_season_injuries = (
            all_season_injuries.get(config["game_log_seasons"][1], {})
            if len(config["game_log_seasons"]) > 1 else {}
        )
        prior_severe_by_key = {
            canonical_player_key(reformat_lastfirst_name(name)): info["severe_reasons"]
            for name, info in prior_season_injuries.items()
            if info["had_severe_injury"]
        }
        # For causes.py's per-season cause attribution (all 3 loaded
        # seasons, not just current+prior -- the data was already fetched
        # above for all 3, this just reads the rest of what's there).
        severe_reasons_by_season = {
            season: {
                canonical_player_key(reformat_lastfirst_name(name)): info["severe_reasons"]
                for name, info in all_season_injuries.get(season, {}).items()
                if info["had_severe_injury"]
            }
            for season in config["game_log_seasons"]
        }
    except Exception as e:
        print(f"   [warn] Injury-report fetch skipped: {e.__class__.__name__}: {e}")
        severe_injury_by_key = {}
        prior_severe_by_key = {}
        severe_reasons_by_season = {}

    # Only ACL/Achilles/meniscus carry a real NBA-outcome-study-backed
    # discount (see data.py's INJURY_TIER_YEAR1_DISCOUNT for the full
    # citations and reasoning) -- every other severe-injury match stays
    # flagged on the board but doesn't move the projection, since no
    # NBA-specific study was found to ground a number for it.
    injury_tier_by_key = {
        key: classify_injury_tier_with_carryover(reasons, prior_severe_by_key.get(key, []))
        for key, reasons in severe_injury_by_key.items()
    }
    injury_discount_by_key = {
        key: INJURY_TIER_YEAR1_DISCOUNT[tier]
        for key, tier in injury_tier_by_key.items()
        if tier is not None
    }

    player_cause_profile = causes.build_player_cause_profile(
        seasons=config["game_log_seasons"],
        gp_by_season=dict(zip(config["game_log_seasons"], season_raw_gp)),
        team_by_season=dict(zip(config["game_log_seasons"], season_raw_team)),
        severe_reasons_by_season=severe_reasons_by_season,
    )

    # ── 5. Project stats and compute G-scores ────────────────────────────
    print("\n[5/5] Projecting stats and computing G-scores...")

    projected = project_stats(
        season_dfs, weights, derived_stats, tech_per_game,
        seasons=config["game_log_seasons"],
        raw_player_sets=season_player_sets,
        raw_gp_by_season=season_raw_gp,
        injury_discount_by_player=injury_discount_by_key,
        player_cause_profile=player_cause_profile,
    )
    projected = projected.dropna(subset=["PTS"])
    print(f"   {len(projected)} players with projections")

    draft_history = fetch_draft_history(
        draft_years=config["draft_years"],
        cache_file=config["draft_history_cache"],
    )
    combine_stats = fetch_combine_stats(cache_file=config["combine_stats_cache"])
    rookie_rows = build_rookie_rows(
        draft_history, combine_stats, ROOKIE_FITTED_MODEL,
        existing_players=set(projected["PLAYER_NAME"]),
    )

    # extra_rows: real rostered players outside the top pool_size (today's
    # flat num_teams*roster_size) get a real TOTAL_VALUE scored against the
    # pool's fixed normalization baseline, without widening that baseline
    # itself -- see compute_g_scores' docstring and the 2026-10-21
    # pool-size-widening final whole-branch review for why pool_size stays
    # untouched here (widening it directly failed the ADR-0001 gate).
    flat_pool_size = config["num_teams"] * config["roster_size"]
    extra_rows = build_extra_rows(projected, flat_pool_size)
    rankings = compute_g_scores(projected, player_tau, league_tau, config, extra_rows=extra_rows)

    # Positional scarcity — supplementary metric only, doesn't touch
    # TOTAL_VALUE/RANK. Every pool player has a position here: position_by_player
    # is built above from all 3 raw BBR seasons (setdefault, newest wins),
    # the same source every pool player's row ultimately comes from.
    rankings["POSITION"] = rankings["PLAYER_NAME"].map(position_by_player)
    rankings = compute_positional_value(rankings, config)

    # ── Team changes — diagnostic flag only, no projection adjustment ──────
    # Whether a trade/signing helps or hurts a player's output is a much
    # harder, higher-risk question than detecting that it happened (see
    # GitHub issue #13) -- this only flags who moved, so the pool has no
    # awareness of team context otherwise.
    current_teams = fetch_current_teams(
        season=PROJECTION_SEASON_LABEL,
        cache_file=config["current_teams_cache"],
    )
    team_changes = detect_team_changes(
        previous_team_by_player=season_raw_team[0],
        current_team_by_player=current_teams,
    )
    rankings["TEAM_CHANGED"] = rankings["PLAYER_NAME"].map(team_changes).fillna("")

    rankings["RECENT_SEVERE_INJURY"] = rankings["PLAYER_NAME"].apply(
        lambda name: "; ".join(severe_injury_by_key.get(canonical_player_key(name), []))
    )

    rankings["CAUSE_PROFILE_SUMMARY"] = rankings["PLAYER_NAME"].apply(
        lambda name: causes.summarize_cause_profile(
            player_cause_profile.get(name, {}), config["game_log_seasons"],
        )
    )

    # ── Output ───────────────────────────────────────────────────────────
    pool_size = config["num_teams"] * config["roster_size"]
    print(f"\n\nTOP 30 PLAYERS — {PROJECTION_SEASON_LABEL} PROJECTIONS")
    print(f"(pool: {pool_size} players | {config['num_teams']} teams × "
          f"{config['roster_size']} roster spots)")
    print(format_rankings(rankings, config, top_n=30))

    save_rankings(rankings, OUTPUT_FILE)

    # ── Data availability notes ─────────────────────────────────────────────
    # Players entirely absent from the newest BBR season (not just a low-GP
    # season, no row at all) get silently projected from an older season --
    # GP_FACTOR/DECLINE_FACTOR can't see this, since they only ever look at
    # seasons that exist for the player. No cause data exists anywhere in
    # this pipeline to say why (injury, trade, retirement, ...), so this is
    # a flag, not a discount -- named source season, judgment left to
    # whoever's drafting. See GitHub issue #11.
    availability_notes = rankings[rankings["DATA_AVAILABILITY_NOTE"] != ""]
    if not availability_notes.empty:
        print(f"\n\nDATA AVAILABILITY NOTES — {len(availability_notes)} player(s)")
        for _, note_row in availability_notes.sort_values("RANK").iterrows():
            print(f"  #{int(note_row['RANK']):<3d} {note_row['PLAYER_NAME']:<24s} "
                  f"{note_row['DATA_AVAILABILITY_NOTE']}")

    # ── Team change notes ───────────────────────────────────────────────────
    # Flag only -- projected stats above are unchanged by a team move either
    # way. See GitHub issue #13.
    team_change_notes = rankings[rankings["TEAM_CHANGED"] != ""]
    if not team_change_notes.empty:
        print(f"\n\nTEAM CHANGES — {len(team_change_notes)} player(s)")
        for _, change_row in team_change_notes.sort_values("RANK").iterrows():
            print(f"  #{int(change_row['RANK']):<3d} {change_row['PLAYER_NAME']:<24s} "
                  f"{change_row['TEAM_CHANGED']}")

    # ── Rookies — ranked separately, not mixed into the veteran pool ───────
    # Rookies with no prior NBA history can't meaningfully compete for the
    # main pool's MIN-based cutoff (a debut season's diluted per-game minutes
    # will almost never clear an established-veteran floor). Instead of
    # forcing them through that cutoff, rank them against each other using
    # the same G-score machinery, scored against their own population's
    # distribution, and save as a separate file. This is a speculative,
    # lower-confidence list: rookies are projected from a two-stage pick-
    # curve + combine-residual regression (see rookie_baseline.py), not
    # real in-season data. Individually ranked, not tiered -- the model
    # now gives each rookie a genuinely distinct prediction (see
    # docs/superpowers/specs/2026-10-04-rookie-baseline-combine-regression-design.md),
    # unlike the old discrete draft-slot buckets this replaced.
    if not rookie_rows.empty:
        rookie_rankings = compute_g_scores(rookie_rows, {}, league_tau, config)
        print(f"\n\nROOKIE WATCH LIST — {len(rookie_rankings)} incoming rookies, ranked separately")
        print("(speculative: pick-curve + combine-residual regression, not real in-season data)")
        print(format_rankings(rookie_rankings, config, top_n=len(rookie_rankings)))
        save_rankings(rookie_rankings, ROOKIE_OUTPUT_FILE)

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
            rank_ceiling = pool_size if target.get("rank_ceiling_from_pool_size") else target.get("rank_ceiling")
            result = validate(
                rankings,
                path,
                name_col=target.get("name_col", "Player Name"),
                rank_col=target.get("rank_col", "Rank"),
                rank_from_metric=target.get("rank_from_metric", False),
                rank_metric_ascending=target.get("rank_metric_ascending", True),
                rank_ceiling=rank_ceiling,
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
