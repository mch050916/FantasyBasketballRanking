"""
find_trades.py — Two-team trade finder
========================================
Searches every 1-for-1 swap across the league for trades that improve BOTH
sides' expected categories won per week against the field -- the trades a
real manager might actually accept, not just ones that help you.

Cheap value-fairness filter first (within-source TOTAL_VALUE percentile,
same scale trim_to_roster_size already uses) cuts the search space before
the expensive simulation runs only on plausible pairs. Screening uses a
lighter week count by default; re-confirm any finalist with
analyze_trade.py's full precision before proposing it.

Usage:
    python scripts/find_trades.py --team "Chester"
    python scripts/find_trades.py --team "Chester" --max-value-gap 0.1 --top 5
"""

import argparse
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_trade import (build_all_banks, build_replacement_bank,  # noqa: E402
                           warn_league_shape)
from config import LEAGUE_CONFIG, TRADE_CONFIG                        # noqa: E402
from data import fetch_game_logs, fetch_tech_per_game                 # noqa: E402
from model import compute_tau                                          # noqa: E402
from rosters import (load_projections, load_rosters,                   # noqa: E402
                     player_value_percentiles, resolve_roster_players)
from trade import build_week_bank, evaluate_trade                      # noqa: E402


def candidate_pairs(rosters: dict, team: str | None, max_value_gap: float,
                    values: dict[str, float]):
    """1-for-1 swaps within max_value_gap of each other, cheap to generate."""
    teams = [team] if team else list(rosters)
    for a, b in itertools.combinations(rosters, 2):
        if a not in teams and b not in teams:
            continue
        for give, get in itertools.product(rosters[a], rosters[b]):
            if abs(values.get(give, 0.0) - values.get(get, 0.0)) <= max_value_gap:
                yield a, b, give, get


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search 1-for-1 trades that help both sides")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--team", default=None,
                        help="Only search trades involving this team (default: whole league)")
    parser.add_argument("--max-value-gap", type=float, default=0.15,
                        help="Max TOTAL_VALUE percentile gap between swapped players (0-1)")
    parser.add_argument("--sim-weeks", type=int, default=2000,
                        help="Weeks per opponent for the search pass (lower = faster, noisier)")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    projections = load_projections(args.rankings, args.rookies)
    rosters = resolve_roster_players(load_rosters(args.rosters), projections)
    if args.team and args.team not in rosters:
        sys.exit(f"'{args.team}' is not one of the league rosters: {sorted(rosters)}")

    for warning in warn_league_shape(rosters):
        print(f"[warn] {warning}")

    cat_names = list(LEAGUE_CONFIG["categories"].keys())
    roster_players = sorted({p for players in rosters.values() for p in players})
    game_logs, _ = fetch_game_logs(
        player_names=roster_players, seasons=LEAGUE_CONFIG["game_log_seasons"],
        cache_file=LEAGUE_CONFIG["game_log_cache"], return_health=True)
    _, league_tau = compute_tau(game_logs, cat_names, LEAGUE_CONFIG["season_weights"])
    tech_rates = fetch_tech_per_game(
        LEAGUE_CONFIG["game_log_seasons"], LEAGUE_CONFIG["tech_cache"],
        LEAGUE_CONFIG["season_weights"])

    banks, games_pool, _ = build_all_banks(
        rosters, projections, game_logs, league_tau, TRADE_CONFIG, tech_rates)
    raw_banks = build_week_bank(game_logs, tech_rates)
    replacement = build_replacement_bank(
        projections, rosters, league_tau, games_pool, TRADE_CONFIG, raw_banks)

    values = player_value_percentiles(projections)
    search_config = dict(TRADE_CONFIG, weeks_per_opponent=args.sim_weeks)

    pairs = list(candidate_pairs(rosters, args.team, args.max_value_gap, values))
    print(f"Screening {len(pairs)} value-fair 1-for-1 swap(s) "
          f"(gap <= {args.max_value_gap}, {args.sim_weeks} weeks/opponent)...\n")

    hits = []
    for a, b, give, get in pairs:
        result = evaluate_trade(rosters, banks, a, b, [give], [get],
                                LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                                search_config, replacement, values)
        delta_a = result["delta"][a]["expected"]
        delta_b = result["delta"][b]["expected"]
        if delta_a > 0 and delta_b > 0:
            hits.append((min(delta_a, delta_b), a, b, give, get, delta_a, delta_b))

    hits.sort(reverse=True)
    if not hits:
        print("No mutually-improving 1-for-1 swap found at this value-gap threshold.")
        return

    print(f"Top {min(args.top, len(hits))} of {len(hits)} mutually-improving trade(s):\n")
    for _, a, b, give, get, delta_a, delta_b in hits[:args.top]:
        print(f"  {a} gives {give} <-> {b} gives {get}")
        print(f"      {a:<12} {delta_a:+.3f} cats/wk    {b:<12} {delta_b:+.3f} cats/wk")

    print(f"\nScreened at {args.sim_weeks} weeks/opponent for speed -- confirm any of "
          f"these with analyze_trade.py's full {TRADE_CONFIG['weeks_per_opponent']} "
          f"weeks before proposing it.")


if __name__ == "__main__":
    main()
