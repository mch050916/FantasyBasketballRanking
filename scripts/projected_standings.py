"""
projected_standings.py — Projected final standings from the real schedule
=============================================================================
Blends each team's real completed-week record (--actual-record, or 0-0-0 if
every week is still ahead) with simulated results for every remaining
scheduled matchup, to project a final win-loss-tie record and rank.

Usage:
    python scripts/projected_standings.py
    python scripts/projected_standings.py --through-week 3 --actual-record actual_record.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_trade import (build_all_banks, build_replacement_bank,  # noqa: E402
                           warn_league_shape)
from config import LEAGUE_CONFIG, TRADE_CONFIG                      # noqa: E402
from data import fetch_game_logs, fetch_tech_per_game               # noqa: E402
from model import compute_tau                                        # noqa: E402
from rosters import load_projections, load_rosters, resolve_roster_players  # noqa: E402
from trade import (build_week_bank, matchup_win_rates,                # noqa: E402
                   pad_to_roster_size, simulate_team_totals)

# Set by dashboard_server.py's subprocess env only -- plain CLI usage never
# sees this extra line. Lets the web dashboard render a structured card
# instead of parsing the printed report's aligned text.
DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__"


def load_actual_record(path: str | None, teams: list[str]) -> dict[str, tuple[float, float, float]]:
    """
    Real completed-week record per team, (wins, losses, ties).

    A team absent from the file -- or every team, if path is None -- starts
    at 0-0-0: real fantasy standings before any real record has been entered
    (true for this season's week 1, still in progress as of this tool).
    """
    record = {team: (0.0, 0.0, 0.0) for team in teams}
    if path is None:
        return record
    df = pd.read_csv(path)
    unknown = set(df["TEAM"].astype(str)) - set(teams)
    if unknown:
        raise ValueError(f"{path} names team(s) not in the league rosters: {sorted(unknown)}")
    for _, row in df.iterrows():
        record[str(row["TEAM"])] = (float(row["WINS"]), float(row["LOSSES"]), float(row["TIES"]))
    return record


def remaining_matchup_counts(schedule: pd.DataFrame, through_week: int) -> dict[frozenset, int]:
    """
    Unique unordered team-pairs -> how many remaining (week > through_week)
    matchups they share.

    Deduping before simulating matters: rosters don't change mid-projection,
    so the same pair recurring in week 3 and week 12 has the exact same win
    probability -- simulate each unique pair once, not each schedule row.
    """
    counts: dict[frozenset, int] = {}
    remaining = schedule[schedule["WEEK"] > through_week]
    for _, row in remaining.iterrows():
        pair = frozenset({row["TEAM_A"], row["TEAM_B"]})
        counts[pair] = counts.get(pair, 0) + 1
    return counts


def summarize_standings_result(through_week: int, highlight_team: str | None,
                               records: dict[str, tuple[float, float, float]]) -> dict:
    """Pure JSON-summary builder for the web dashboard's standings card."""
    ranked = sorted(records, key=lambda t: records[t][0] + 0.5 * records[t][2], reverse=True)
    return {
        "kind": "projected_standings",
        "throughWeek": through_week,
        "teams": [
            {
                "rank": i + 1,
                "team": team,
                "wins": records[team][0],
                "losses": records[team][1],
                "ties": records[team][2],
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
        description="Project final win-loss-tie record and rank from the real schedule")
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
                        help="Simulated weeks per unique matchup (lower = faster, noisier)")
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

    roster_size = max([LEAGUE_CONFIG["roster_size"]] + [len(p) for p in rosters.values()])
    padded_rosters, padded_banks = pad_to_roster_size(rosters, banks, roster_size, replacement)

    try:
        actual = load_actual_record(args.actual_record, teams)
    except ValueError as exc:
        sys.exit(str(exc))
    wins = {t: actual[t][0] for t in teams}
    losses = {t: actual[t][1] for t in teams}
    ties = {t: actual[t][2] for t in teams}

    pair_counts = remaining_matchup_counts(schedule, args.through_week)
    for pair, count in pair_counts.items():
        a, b = sorted(pair)
        a_totals = simulate_team_totals(
            {p: padded_banks[p] for p in padded_rosters[a]},
            args.weeks_per_matchup, TRADE_CONFIG["seed"])
        b_totals = simulate_team_totals(
            {p: padded_banks[p] for p in padded_rosters[b]},
            args.weeks_per_matchup, TRADE_CONFIG["seed"])
        rate = matchup_win_rates(a_totals, b_totals, LEAGUE_CONFIG["categories"])

        wins[a] += count * rate["win"]
        losses[a] += count * rate["loss"]
        ties[a] += count * rate["tie"]
        wins[b] += count * rate["loss"]
        losses[b] += count * rate["win"]
        ties[b] += count * rate["tie"]

    records = {t: (wins[t], losses[t], ties[t]) for t in teams}
    summary = summarize_standings_result(args.through_week, args.team, records)

    print(f"\nProjected standings through week {args.through_week} "
          f"(remaining weeks simulated at {args.weeks_per_matchup} weeks/matchup):\n")
    for row in summary["teams"]:
        marker = " *" if row["mine"] else ""
        print(f"  {row['rank']:>2}. {row['team']:<28} "
              f"{row['wins']:5.1f} - {row['losses']:5.1f} - {row['ties']:4.1f}{marker}")

    if os.environ.get("DASHBOARD_JSON_SUMMARY"):
        print(DASHBOARD_RESULT_PREFIX + json.dumps(summary))


if __name__ == "__main__":
    main()
