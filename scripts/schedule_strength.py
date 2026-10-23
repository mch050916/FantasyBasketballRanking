"""
scripts/schedule_strength.py — Upcoming-week schedule strength
=================================================================
Shows how many real games each NBA team plays in a given fantasy week
(Monday-Sunday) -- more games means more raw counting-stat opportunity for
that team's players that week, a real streaming/start-sit signal the
pre-draft ranking pipeline doesn't (and shouldn't) capture: an 82-game
season evens this out, but a single week doesn't.

Usage:
    python scripts/schedule_strength.py
    python scripts/schedule_strength.py --week 2026-01-08
    python scripts/schedule_strength.py --team "Chester"
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LEAGUE_CONFIG                                                     # noqa: E402
from data   import fetch_current_teams, fetch_season_schedule, games_per_team_for_week  # noqa: E402
from main   import derive_projection_season_label                                     # noqa: E402
from rosters import load_rosters                                                      # noqa: E402

# Set by dashboard_server.py's subprocess env only -- plain CLI usage never
# sees this extra line. Lets the web dashboard render a structured card
# instead of parsing the printed report's aligned text.
DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__"


def summarize_schedule_strength_result(week_of: str, season: str, counts,
                                       roster: dict | None = None) -> dict:
    """
    Pure JSON-summary builder for the web dashboard's schedule-strength card.
    roster, if given: {"team": str, "players": [{"name", "nbaTeam", "games"}, ...]}.
    """
    summary = {
        "kind": "schedule_strength",
        "weekOf": week_of,
        "season": season,
        "teams": [{"team": team, "games": int(n)}
                  for team, n in counts.sort_values(ascending=False).items()],
    }
    if roster is not None:
        summary["roster"] = roster
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Show each NBA team's game count for a fantasy week")
    parser.add_argument("--week", default=None,
                        help="Any date (YYYY-MM-DD) in the target week; default: today")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--team", default=None,
                        help="Annotate this roster's players with their team's game count")
    args = parser.parse_args()

    week_of = args.week or date.today().isoformat()
    # The season actually being played right now, not game_log_seasons[0]
    # (the most recent *completed* season the ranking pipeline projects
    # from) -- same derivation main.py uses for PROJECTION_SEASON_LABEL.
    _, season = derive_projection_season_label(LEAGUE_CONFIG["game_log_seasons"][0])

    schedule = fetch_season_schedule(season, LEAGUE_CONFIG["season_schedule_cache"])
    counts = games_per_team_for_week(schedule, week_of)

    if counts.empty:
        sys.exit(f"No scheduled games found for the week of {week_of} in {season}.")

    print(f"\nGames per team — week of {week_of} ({season}):\n")
    for team, n in counts.sort_values(ascending=False).items():
        print(f"  {team:<4} {n}")

    roster_summary = None
    if args.team:
        rosters = load_rosters(args.rosters)
        if args.team not in rosters:
            sys.exit(f"'{args.team}' is not one of the league rosters: {sorted(rosters)}")

        current_teams = fetch_current_teams(season=season, cache_file=LEAGUE_CONFIG["current_teams_cache"])
        print(f"\n{args.team}'s roster this week:\n")
        roster_players = []
        for player in sorted(rosters[args.team]):
            team = current_teams.get(player)
            games = counts.get(team, 0) if team else 0
            print(f"  {player:<28} {team or '?':<4} {games} games")
            roster_players.append({"name": player, "nbaTeam": team, "games": int(games)})
        roster_summary = {"team": args.team, "players": roster_players}

    if os.environ.get("DASHBOARD_JSON_SUMMARY"):
        summary = summarize_schedule_strength_result(week_of, season, counts, roster_summary)
        print(DASHBOARD_RESULT_PREFIX + json.dumps(summary))


if __name__ == "__main__":
    main()
