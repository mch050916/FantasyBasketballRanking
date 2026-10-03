"""
buy_low_sell_high.py — In-season performance vs. projection
==============================================================
Fetches this season's real game logs and diffs each player's actual
per-game rate against their preseason projection, weighted the same way
the model weights categories for value -- a single score per player:
positive means outperforming (sell high), negative means underperforming
(buy low).

Usage:
    python scripts/buy_low_sell_high.py --season 2026-27
    python scripts/buy_low_sell_high.py --season 2026-27 --min-games 10 --top 15
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LEAGUE_CONFIG                      # noqa: E402
from data import fetch_game_logs                      # noqa: E402
from rosters import load_projections                   # noqa: E402
from trade import API_COL_MAP                           # noqa: E402

RATE_COLUMNS = {
    "PTS": "PTS", "REB": "REB", "AST": "AST", "ST": "ST", "BLK": "BLK",
    "TO": "TO", "FTM": "FTM", "3PTM": "3PTM", "DD": "DD", "TD": "TD",
}


def actual_per_game(logs: pd.DataFrame) -> dict[str, float] | None:
    """Real per-game rates for one player's season-to-date game log."""
    games = len(logs)
    if games == 0:
        return None
    out = {"GP": games}
    for cat in RATE_COLUMNS:
        api_col = API_COL_MAP.get(cat, cat)
        out[cat] = float(logs[api_col].sum()) / games if api_col in logs.columns else None
    if "FGM" in logs.columns and "FGA" in logs.columns and logs["FGA"].sum() > 0:
        out["FG%"] = float(logs["FGM"].sum()) / float(logs["FGA"].sum())
    else:
        out["FG%"] = None
    return out


def performance_score(actual: dict, projected: pd.Series) -> float | None:
    """
    Weighted sum of direction-adjusted, projection-relative deltas.

    Reuses the model's own category_weights so categories that matter more
    for value dominate the signal the same way they dominate TOTAL_VALUE --
    this is "how is the projection holding up," not a new ranking metric.
    """
    weights = LEAGUE_CONFIG["category_weights"]
    total = 0.0
    counted = 0
    for cat in list(RATE_COLUMNS) + ["FG%"]:
        a = actual.get(cat)
        p = projected.get(cat)
        if a is None or p is None or pd.isna(p) or p == 0:
            continue
        diff = (a - p) / abs(p)
        if LEAGUE_CONFIG["categories"][cat]["direction"] == "low":
            diff = -diff
        total += diff * weights.get(cat, 1.0)
        counted += 1
    return total / counted if counted else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag players over/underperforming their preseason projection")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--season", default=LEAGUE_CONFIG["game_log_seasons"][0],
                        help="Season to fetch actuals for (default: the current "
                             "projected season). The game-log cache is keyed to "
                             "the exact season list it was built with -- changing "
                             "this rebuilds this tool's own cache from scratch, "
                             "but never touches game_log_cache.pkl.")
    parser.add_argument("--min-games", type=int, default=5)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    projections = load_projections(args.rankings, args.rookies)
    by_name = projections.set_index("PLAYER_NAME")

    # Scope to the same veteran population the game-log cache was built for
    # (main.py's game_log_player_limit) -- anyone outside it triggers a live,
    # rate-limited NBA API fetch per missing player, which this bulk report
    # has no business doing. Rookies have no veteran game-log history either
    # way; they show up here once they've actually played the season in hand.
    veterans = projections[projections["SOURCE"] == "veteran"].sort_values(
        "TOTAL_VALUE", ascending=False)
    players = list(veterans.head(LEAGUE_CONFIG["game_log_player_limit"])["PLAYER_NAME"])

    # A cache dedicated to this tool, never the pipeline's game_log_cache.pkl:
    # the cache is keyed to its exact seasons list and a mismatch rebuilds the
    # whole thing from scratch (data.py's _load_cached_game_logs), so sharing
    # a cache file across tools that ask for different season lists is a
    # standing footgun, not a one-off mistake.
    game_logs, health = fetch_game_logs(
        player_names=players, seasons=[args.season],
        cache_file="buy_low_sell_high_cache.pkl", return_health=True)
    season_logs = game_logs.get(args.season, {})
    if health and health.get("degraded"):
        print(f"[warn] game-log fetch is DEGRADED for {args.season} -- "
              f"results below only cover players the API actually returned")

    rows = []
    for name, logs in season_logs.items():
        if name not in by_name.index:
            continue
        actual = actual_per_game(logs)
        if actual is None or actual["GP"] < args.min_games:
            continue
        score = performance_score(actual, by_name.loc[name])
        if score is not None:
            rows.append((name, actual["GP"], score))

    if not rows:
        print(f"No players with >= {args.min_games} logged games in {args.season} yet.")
        return

    rows.sort(key=lambda r: r[2], reverse=True)
    print(f"{len(rows)} player(s) with >= {args.min_games} games in {args.season}\n")

    print(f"SELL HIGH (top {args.top}, outperforming projection):")
    for name, gp, score in rows[:args.top]:
        print(f"  {name:<28} {score:+.3f}   ({gp} GP)")

    print(f"\nBUY LOW (top {args.top}, underperforming projection):")
    for name, gp, score in rows[-args.top:][::-1]:
        print(f"  {name:<28} {score:+.3f}   ({gp} GP)")


if __name__ == "__main__":
    main()
