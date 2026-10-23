"""
punt_planner.py — Category punt planner
=========================================
For a roster, ranks categories by how often they're already being lost
against the league field (real simulated win rate, same engine as
analyze_trade.py) and shows what the roster's record looks like if the
worst one is conceded outright. Also re-ranks the full player pool with
that category's weight zeroed, so you can see who gains/loses value under
the punt build and where your own players land.

Usage:
    python scripts/punt_planner.py --team "Chester"
    python scripts/punt_planner.py --team "Chester" --punt "FG%"
    python scripts/punt_planner.py --team "Chester" --punt "FG%,AST"
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_trade import (build_all_banks, build_replacement_bank,  # noqa: E402
                           warn_league_shape)
from config import LEAGUE_CONFIG, TRADE_CONFIG                        # noqa: E402
from data import fetch_game_logs, fetch_tech_per_game                 # noqa: E402
from model import compute_tau                                          # noqa: E402
from rosters import load_projections, load_rosters, resolve_roster_players  # noqa: E402
from trade import build_week_bank, evaluate_roster_vs_field, pad_to_roster_size  # noqa: E402

# Set by dashboard_server.py's subprocess env only -- plain CLI usage never
# sees this extra line. Lets the web dashboard render a structured card
# instead of parsing the printed report's aligned text.
DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__"


def summarize_punt_result(team: str, expected: float, shares: dict, ranked: list,
                          punts: list, top_players: list) -> dict:
    """
    Pure JSON-summary builder for the web dashboard's punt-planner card.

    punts: one or more categories conceded together (multi-punt), in the
    order the user listed them -- "isPunt" and the remaining-categories math
    both just check membership, so punting two categories is summing two
    shares instead of one, not a different model.
    top_players: list of (name, punt_value, was_value, mine) tuples, already
    sorted/limited to the requested --show-players count -- mirrors exactly
    what main()'s printed report shows, just structured instead of aligned text.
    """
    n = len(shares)
    punt_set = set(punts)
    remaining = expected - sum(shares[c] for c in punts)
    remaining_n = n - len(punts)
    return {
        "kind": "punt_planner",
        "team": team,
        "expected": expected,
        "n": n,
        "categories": [{"category": c, "share": shares[c], "isPunt": c in punt_set} for c in ranked],
        "punt": punts,
        "remaining": {
            "expected": remaining,
            "n": remaining_n,
            "avgRemaining": remaining / remaining_n,
            "avgToday": expected / n,
        },
        "players": [
            {"name": name, "value": value, "was": was, "mine": mine}
            for name, value, was, mine in top_players
        ],
    }


def category_shares(rates: dict) -> dict[str, float]:
    """Win share per category: a win counts 1, a tie counts 0.5."""
    return {cat: r["win"] + 0.5 * r["tie"] for cat, r in rates.items()}


def repriced_total_value(projections, cats, new_weight):
    """
    TOTAL_VALUE recomputed with one or more categories' weight swapped out
    (multi-punt: every category in `cats` gets `new_weight`, together).

    Every category's stored {cat}_G column is already `g * old_weight`
    (model.py's compute_g_scores) -- dividing it back out and multiplying by
    the new weight reproduces exactly what a full rerun would give for that
    weight change, without redoing Box-Cox/tau/G-score math that doesn't
    depend on category_weights at all.
    """
    cats = set(cats) if not isinstance(cats, str) else {cats}
    weights = LEAGUE_CONFIG["category_weights"]
    total = 0.0
    for c in LEAGUE_CONFIG["categories"]:
        col = f"{c}_G"
        if col not in projections.columns:
            continue
        old_weight = weights.get(c, 1.0) or 1.0
        w = new_weight if c in cats else weights.get(c, 1.0)
        total = total + projections[col] / old_weight * w
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank punt candidates for a roster")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--team", required=True)
    parser.add_argument("--punt", default=None,
                        help="Category (or comma-separated categories, for a multi-punt build) "
                             "to analyze -- default: the worst-performing one")
    parser.add_argument("--show-players", type=int, default=15,
                        help="How many top players to show under the punt weighting")
    args = parser.parse_args()

    projections = load_projections(args.rankings, args.rookies)
    rosters = resolve_roster_players(load_rosters(args.rosters), projections)
    if args.team not in rosters:
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

    roster_size = max([LEAGUE_CONFIG["roster_size"]] + [len(p) for p in rosters.values()])
    padded_rosters, padded_banks = pad_to_roster_size(rosters, banks, roster_size, replacement)

    expected, rates = evaluate_roster_vs_field(
        args.team, padded_rosters, padded_banks, LEAGUE_CONFIG["categories"],
        TRADE_CONFIG["weeks_per_opponent"], TRADE_CONFIG["seed"])

    shares = category_shares(rates)
    ranked = sorted(shares, key=shares.get)
    punts = [c.strip() for c in args.punt.split(",")] if args.punt else [ranked[0]]
    for punt in punts:
        if punt not in shares:
            sys.exit(f"'{punt}' is not a scored category: {sorted(shares)}")
    if len(punts) >= len(shares):
        sys.exit(f"Can't punt every scored category ({len(punts)} of {len(shares)}) -- "
                 f"there'd be nothing left to rank players on")
    punt_label = "+".join(punts)

    n = len(shares)
    print(f"\n{args.team} — expected categories won per week: {expected:.2f} / {n}, "
          f"vs league field\n")
    print("Categories ranked worst to best (punt candidates first):")
    for cat in ranked:
        marker = " <-- punt" if cat in punts else ""
        print(f"  {cat:<6} {shares[cat]:5.3f}{marker}")

    remaining = expected - sum(shares[c] for c in punts)
    remaining_n = n - len(punts)
    print(f"\nConceding {punt_label} outright: {remaining:.2f} / {remaining_n} remaining categories "
          f"(avg {remaining / remaining_n:.3f}/cat, vs {expected / n:.3f}/cat today)")

    print(f"\nTop {args.show_players} players re-ranked with {punt_label} weighted to 0 "
          f"(* = on {args.team}'s roster):")
    repriced = projections.assign(PUNT_VALUE=repriced_total_value(projections, punts, 0.0))
    top = repriced.sort_values("PUNT_VALUE", ascending=False).head(args.show_players)
    top_players = []
    for _, row in top.iterrows():
        mine = row["PLAYER_NAME"] in rosters[args.team]
        mark = "*" if mine else " "
        print(f"  {mark} {row['PLAYER_NAME']:<28} {row['PUNT_VALUE']:6.2f}  "
              f"(was {row['TOTAL_VALUE']:6.2f})")
        top_players.append((row["PLAYER_NAME"], float(row["PUNT_VALUE"]),
                            float(row["TOTAL_VALUE"]), mine))

    if os.environ.get("DASHBOARD_JSON_SUMMARY"):
        summary = summarize_punt_result(args.team, expected, shares, ranked, punts, top_players)
        print(DASHBOARD_RESULT_PREFIX + json.dumps(summary))


if __name__ == "__main__":
    main()
