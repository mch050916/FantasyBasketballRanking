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
