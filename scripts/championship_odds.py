"""
championship_odds.py — Odds of finishing 1st, from Monte Carlo season replication
=============================================================================
Resamples the entire remaining season thousands of times from each matchup
pair's precomputed win/tie/loss probability (trade.matchup_win_rates, computed
once per pair -- not re-derived per replication) to report each team's odds
of finishing 1st (title odds) and average projected final rank.

Usage:
    python scripts/championship_odds.py
    python scripts/championship_odds.py --replications 10000 --team "AR15s And Saboners"
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_trade import (build_all_banks, build_replacement_bank,  # noqa: E402
                           warn_league_shape)
from config import LEAGUE_CONFIG, TRADE_CONFIG                      # noqa: E402
from data import (fetch_game_logs, fetch_tech_per_game,              # noqa: E402
                  expected_missing_game_log_pairs)
from model import compute_tau                                        # noqa: E402
from rosters import (load_actual_record, load_projections, load_rosters,  # noqa: E402
                     resolve_roster_players)
from trade import (build_week_bank, matchup_pair_counts, matchup_win_rates,  # noqa: E402
                   pad_to_roster_size, simulate_season_replications, simulate_team_totals)

# Set by dashboard_server.py's subprocess env only -- plain CLI usage never
# sees this extra line. Lets the web dashboard render a structured card
# instead of parsing the printed report's aligned text.
DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__"


def summarize_championship_odds_result(highlight_team: str | None,
                                       results: dict[str, dict]) -> dict:
    """Pure JSON-summary builder for the web dashboard's championship-odds card."""
    ranked = sorted(results, key=lambda t: results[t]["titleOdds"], reverse=True)
    return {
        "kind": "championship_odds",
        "teams": [
            {
                "rank": i + 1,
                "team": team,
                "titleOdds": results[team]["titleOdds"],
                "averageRank": results[team]["averageRank"],
                "mine": team == highlight_team,
            }
            for i, team in enumerate(ranked)
        ],
    }


def main() -> None:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(
        description="Monte Carlo odds of finishing 1st, from the real remaining schedule")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--schedule", default="fantasy_schedule.csv")
    parser.add_argument("--actual-record", default=None,
                        help="CSV of TEAM,WINS,LOSSES,TIES for weeks already played "
                             "(default: every team starts 0-0-0)")
    parser.add_argument("--through-week", type=int, default=0,
                        help="Last completed week -- weeks after this are simulated "
                             "(default: 0, nothing completed yet)")
    parser.add_argument("--weeks-per-matchup", type=int,
                        default=TRADE_CONFIG["weeks_per_opponent"],
                        help="Simulated weeks used to compute each pair's underlying "
                             "win/tie/loss probability (lower = faster, noisier)")
    parser.add_argument("--replications", type=int, default=5000,
                        help="Season replications to run (default: 5000)")
    parser.add_argument("--team", default=None,
                        help="Highlight this team's row in the output (optional)")
    args = parser.parse_args()

    projections = load_projections(args.rankings, args.rookies)
    rosters = resolve_roster_players(load_rosters(args.rosters), projections)
    teams = sorted(rosters)

    for warning in warn_league_shape(rosters):
        print(f"[warn] {warning}")

    schedule = pd.read_csv(args.schedule)
    schedule_teams = set(schedule["TEAM_A"]) | set(schedule["TEAM_B"])
    unknown = schedule_teams - set(rosters)
    if unknown:
        sys.exit(f"Schedule names team(s) not in the league rosters: {sorted(unknown)}")
    if args.through_week > schedule["WEEK"].max():
        sys.exit(f"--through-week {args.through_week} is beyond the schedule's last "
                 f"week ({schedule['WEEK'].max()}) -- nothing left to project")
    if args.through_week > 0 and args.actual_record is None:
        sys.exit(f"--through-week {args.through_week} requires --actual-record "
                 f"(real results for weeks 1-{args.through_week}) -- without it, every "
                 f"team would start from 0-0-0 and the title odds would be based on a "
                 f"season short by {args.through_week} weeks' worth of games")
    if args.replications < 1:
        sys.exit(f"--replications must be at least 1 (got {args.replications})")

    cat_names = list(LEAGUE_CONFIG["categories"].keys())
    roster_players = sorted({p for players in rosters.values() for p in players})
    game_logs, _ = fetch_game_logs(
        player_names=roster_players, seasons=LEAGUE_CONFIG["game_log_seasons"],
        cache_file=LEAGUE_CONFIG["game_log_cache"], return_health=True,
        expected_missing_pairs=expected_missing_game_log_pairs(
            roster_players, LEAGUE_CONFIG["game_log_seasons"], LEAGUE_CONFIG["bbr_files"]))
    _, league_tau = compute_tau(game_logs, cat_names, LEAGUE_CONFIG["season_weights"])
    tech_rates = fetch_tech_per_game(
        LEAGUE_CONFIG["game_log_seasons"], LEAGUE_CONFIG["tech_cache"],
        LEAGUE_CONFIG["season_weights"])

    banks, games_pool, _ = build_all_banks(
        rosters, projections, game_logs, league_tau, TRADE_CONFIG, tech_rates)
    raw_banks = build_week_bank(game_logs, tech_rates)
    replacement = build_replacement_bank(
        projections, rosters, league_tau, games_pool, TRADE_CONFIG, raw_banks)

    roster_size = max([LEAGUE_CONFIG["roster_size"]] + [len(p) for p in rosters.values()])
    padded_rosters, padded_banks = pad_to_roster_size(rosters, banks, roster_size, replacement)

    try:
        actual = load_actual_record(args.actual_record, teams)
    except ValueError as exc:
        sys.exit(str(exc))

    remaining_schedule = schedule[schedule["WEEK"] > args.through_week]

    pair_rates = {}
    for pair in matchup_pair_counts(remaining_schedule):
        a, b = sorted(pair)
        a_totals = simulate_team_totals(
            {p: padded_banks[p] for p in padded_rosters[a]}, args.weeks_per_matchup,
            TRADE_CONFIG["seed"])
        b_totals = simulate_team_totals(
            {p: padded_banks[p] for p in padded_rosters[b]}, args.weeks_per_matchup,
            TRADE_CONFIG["seed"])
        pair_rates[pair] = matchup_win_rates(a_totals, b_totals, LEAGUE_CONFIG["categories"])

    results = simulate_season_replications(
        remaining_schedule, actual, pair_rates, args.replications, TRADE_CONFIG["seed"])
    summary = summarize_championship_odds_result(args.team, results)

    print(f"\nChampionship odds through week {args.through_week} "
          f"({args.replications} replications, "
          f"{args.weeks_per_matchup} weeks/matchup for pair probabilities):\n")
    for row in summary["teams"]:
        marker = " *" if row["mine"] else ""
        print(f"  {row['rank']:>2}. {row['team']:<28} "
              f"{row['titleOdds'] * 100:5.1f}%   avg rank {row['averageRank']:4.2f}{marker}")

    if os.environ.get("DASHBOARD_JSON_SUMMARY"):
        print(DASHBOARD_RESULT_PREFIX + json.dumps(summary))


if __name__ == "__main__":
    main()
