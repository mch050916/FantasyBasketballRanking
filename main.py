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

from config   import LEAGUE_CONFIG
from data     import load_bbr_csv, filter_qualified, fetch_game_logs, \
                     fetch_tech_per_game, derive_stats_from_logs
from model    import project_stats, compute_tau, compute_g_scores
from output   import format_rankings, save_rankings
from validate import validate


# ── Season data files — update this list each season ────────────────────────
# Most recent season first. Must match game_log_seasons in config.py.
BBR_FILES = [
    "basketball_reference_2024_25_total_stats.csv",
    "basketball_reference_2023_24_total_stats.csv",
]

OUTPUT_FILE     = "durant_rankings_2025_26.csv"
VALIDATION_TARGETS = [
    {
        "path": "actual_14cat_24_25_snapshot.csv",
        "label": "actual_14cat_24_25_snapshot.csv",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": "14-cat exact-league validation snapshot for 2024-25",
    },
    {
        "path": "actual_14cat_23_24_snapshot.csv",
        "label": "actual_14cat_23_24_snapshot.csv",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": "14-cat exact-league validation snapshot for 2023-24",
    },
    {
        "path": "yahoo_25_26_market_export.csv",
        "label": "yahoo_25_26_adp_proxy",
        "name_col": ["First Name", "Last Name"],
        "rank_col": "Avg. Pick",
        "rank_from_metric": True,
        "rank_metric_ascending": True,
        "note": "Market comparison only — lower Yahoo Avg. Pick is treated as a better preseason rank",
    },
    {
        "path": "yahoo_25_26_market_export.csv",
        "label": "yahoo_25_26_live_snapshot",
        "name_col": ["First Name", "Last Name"],
        "rank_col": "OR",
        "note": "Live Yahoo season-to-date rank snapshot from the export's OR column",
    },
    {
        "path": "actual_9cat_24_25.csv",
        "label": "actual_9cat_24_25.csv",
        "name_col": "Player Name",
        "rank_col": "Rank",
        "note": "14-cat model vs 9-cat actual — directional comparison only",
    },
]


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

    ok_labels = [r["label"] for r in validation_results if r["status"] == "ok"]
    weak_labels = [r["label"] for r in validation_results if r["status"] == "weak_matches"]
    failed_labels = [r["label"] for r in validation_results if r["status"] == "no_matches"]
    skipped_labels = [r["label"] for r in validation_results if r["status"] == "missing_file"]

    print("  Validation      :")
    print(f"    ok            : {len(ok_labels)}")
    print(f"    weak          : {len(weak_labels)}")
    print(f"    failed        : {len(failed_labels)}")
    print(f"    skipped       : {len(skipped_labels)}")

    if weak_labels:
        print(f"    weak targets  : {', '.join(weak_labels)}")
    if failed_labels:
        print(f"    failed targets: {', '.join(failed_labels)}")
    if skipped_labels:
        print(f"    skipped files : {', '.join(skipped_labels)}")


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
    for path in BBR_FILES:
        df = load_bbr_csv(path)
        df = filter_qualified(df, config)
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
    print(f"   Fetching logs for {len(game_log_players)} players "
          f"(top {limit} by MIN + {len(extra)} returnees)")

    game_logs, game_log_health = fetch_game_logs(
        player_names=game_log_players,
        seasons=config["game_log_seasons"],
        cache_file=config["game_log_cache"],
        return_health=True,
    )

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
    for target in VALIDATION_TARGETS:
        path = target["path"]
        if Path(path).exists():
            validation_results.append(validate(
                rankings,
                path,
                name_col=target.get("name_col", "Player Name"),
                rank_col=target.get("rank_col", "Rank"),
                rank_from_metric=target.get("rank_from_metric", False),
                rank_metric_ascending=target.get("rank_metric_ascending", True),
                label=target.get("label"),
                note=target.get("note"),
            ))
        else:
            print(f"\n[skip] Validation file not found: {path}")
            validation_results.append(
                {
                    "label": target.get("label", path),
                    "status": "missing_file",
                    "matched_players": 0,
                }
            )

    print_run_health_summary(game_log_health, validation_results)


if __name__ == "__main__":
    main()
