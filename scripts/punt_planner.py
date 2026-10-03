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
"""

import argparse
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


def category_shares(rates: dict) -> dict[str, float]:
    """Win share per category: a win counts 1, a tie counts 0.5."""
    return {cat: r["win"] + 0.5 * r["tie"] for cat, r in rates.items()}


def repriced_total_value(projections, cat, new_weight):
    """
    TOTAL_VALUE recomputed with one category's weight swapped out.

    Every category's stored {cat}_G column is already `g * old_weight`
    (model.py's compute_g_scores) -- dividing it back out and multiplying by
    the new weight reproduces exactly what a full rerun would give for that
    weight change, without redoing Box-Cox/tau/G-score math that doesn't
    depend on category_weights at all.
    """
    weights = LEAGUE_CONFIG["category_weights"]
    total = 0.0
    for c in LEAGUE_CONFIG["categories"]:
        col = f"{c}_G"
        if col not in projections.columns:
            continue
        old_weight = weights.get(c, 1.0) or 1.0
        w = new_weight if c == cat else weights.get(c, 1.0)
        total = total + projections[col] / old_weight * w
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank punt candidates for a roster")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--team", required=True)
    parser.add_argument("--punt", default=None,
                        help="Category to analyze (default: the worst-performing one)")
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
    punt = args.punt or ranked[0]
    if punt not in shares:
        sys.exit(f"'{punt}' is not a scored category: {sorted(shares)}")

    n = len(shares)
    print(f"\n{args.team} — expected categories won per week: {expected:.2f} / {n}, "
          f"vs league field\n")
    print("Categories ranked worst to best (punt candidates first):")
    for cat in ranked:
        marker = " <-- punt" if cat == punt else ""
        print(f"  {cat:<6} {shares[cat]:5.3f}{marker}")

    remaining = expected - shares[punt]
    print(f"\nConceding {punt} outright: {remaining:.2f} / {n - 1} remaining categories "
          f"(avg {remaining / (n - 1):.3f}/cat, vs {expected / n:.3f}/cat today)")

    print(f"\nTop {args.show_players} players re-ranked with {punt} weighted to 0 "
          f"(* = on {args.team}'s roster):")
    repriced = projections.assign(PUNT_VALUE=repriced_total_value(projections, punt, 0.0))
    top = repriced.sort_values("PUNT_VALUE", ascending=False).head(args.show_players)
    for _, row in top.iterrows():
        mark = "*" if row["PLAYER_NAME"] in rosters[args.team] else " "
        print(f"  {mark} {row['PLAYER_NAME']:<28} {row['PUNT_VALUE']:6.2f}  "
              f"(was {row['TOTAL_VALUE']:6.2f})")


if __name__ == "__main__":
    main()
