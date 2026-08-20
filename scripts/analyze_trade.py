"""
analyze_trade.py — Trade analyzer CLI
======================================
Usage:
    python scripts/analyze_trade.py --team "Chester" --partner "Bob" \
        --give "Jalen Johnson,Kyrie Irving" --get "Alperen Sengun"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LEAGUE_CONFIG, TRADE_CONFIG          # noqa: E402
from data import fetch_game_logs                        # noqa: E402
from model import compute_tau                            # noqa: E402
from rosters import (load_projections, load_rosters,     # noqa: E402
                     resolve_roster_players)
from trade import (BANK_COLUMNS, build_week_bank,        # noqa: E402
                   evaluate_trade, games_per_week_pool,
                   scale_bank_to_projection, synthesize_bank)


def parse_names(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def build_all_banks(rosters, projections, game_logs, league_tau, trade_config):
    """One bank per rostered player: bootstrapped where possible, else synthetic."""
    raw_banks = build_week_bank(game_logs)
    games_pool = games_per_week_pool(raw_banks)
    by_name = projections.set_index("PLAYER_NAME")

    banks, synthetic = {}, []
    for team_players in rosters.values():
        for player in team_players:
            projected = by_name.loc[player]
            raw = raw_banks.get(player)
            if raw is not None and raw.shape[0] >= trade_config["min_weeks_for_bootstrap"]:
                banks[player] = scale_bank_to_projection(
                    raw, projected, trade_config["scale_bounds"])
            else:
                synthetic.append(player)
                banks[player] = synthesize_bank(
                    player, projected, league_tau, games_pool,
                    trade_config["seed"], trade_config["synthetic_bank_rows"])
    return banks, games_pool, synthetic


def build_replacement_bank(projections, rosters, league_tau, games_pool, trade_config):
    """Replacement level = the lowest-ranked player in the projection pool."""
    pool_size = LEAGUE_CONFIG["num_teams"] * LEAGUE_CONFIG["roster_size"]
    ranked = projections.sort_values("TOTAL_VALUE", ascending=False)
    replacement = ranked.iloc[min(pool_size, len(ranked)) - 1]
    return synthesize_bank("__replacement_level__", replacement, league_tau,
                           games_pool, trade_config["seed"],
                           trade_config["synthetic_bank_rows"])


def format_report(result, team, partner, give, get) -> str:
    lines = []
    give_text = ", ".join(give) if give else "nothing"
    get_text = ", ".join(get) if get else "nothing"
    lines.append(f"\n{team} gives {give_text} -> receives {get_text}\n")

    n_cats = len(LEAGUE_CONFIG["categories"])
    lines.append(f"Expected categories won per week (of {n_cats}, vs league field)")
    for name in (team, partner):
        before = result["before"][name]["expected"]
        after = result["after"][name]["expected"]
        lines.append(f"  {name:<12} {before:6.2f} -> {after:6.2f}   {after - before:+6.2f}")

    lines.append(f"\nPer-category, {team}      BEFORE   AFTER       D    TIE%")
    before_rates = result["before"][team]["rates"]
    after_rates = result["after"][team]["rates"]
    ordered = sorted(before_rates,
                     key=lambda c: after_rates[c]["win"] - before_rates[c]["win"],
                     reverse=True)
    for cat in ordered:
        b, a = before_rates[cat]["win"], after_rates[cat]["win"]
        tie = after_rates[cat]["tie"] * 100
        lines.append(f"  {cat:<22} {b:6.3f}  {a:6.3f}  {a - b:+7.3f}  {tie:6.1f}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a two-team fantasy trade")
    parser.add_argument("--rosters", default="rosters.csv")
    parser.add_argument("--rankings", default="durant_rankings_2026_27.csv")
    parser.add_argument("--rookies", default="durant_rankings_rookies_2026_27.csv")
    parser.add_argument("--team", required=True)
    parser.add_argument("--partner", required=True)
    parser.add_argument("--give", default="")
    parser.add_argument("--get", default="")
    args = parser.parse_args()

    projections = load_projections(args.rankings, args.rookies)
    rosters = resolve_roster_players(load_rosters(args.rosters), projections)

    give = resolve_roster_players({"g": parse_names(args.give)}, projections)["g"]
    get = resolve_roster_players({"g": parse_names(args.get)}, projections)["g"]

    cat_names = list(LEAGUE_CONFIG["categories"].keys())

    # fetch_game_logs' returned dict already contains every player-season in
    # the on-disk cache regardless of player_names -- that list only decides
    # which (player, season) pairs count as "missing" and worth an NBA API
    # call. Scoping it to just the rostered players (rather than the whole
    # projections pool, which includes hundreds of players never fetched into
    # the cache) keeps this CLI's cache-hit path network-free in the normal
    # case, while still failing loudly -- via a real API attempt -- if a
    # rostered player genuinely isn't cached yet.
    roster_players = sorted({p for players in rosters.values() for p in players})
    game_logs, _health = fetch_game_logs(
        player_names=roster_players,
        seasons=LEAGUE_CONFIG["game_log_seasons"],
        cache_file=LEAGUE_CONFIG["game_log_cache"],
        return_health=True,
    )
    _, league_tau = compute_tau(game_logs, cat_names, LEAGUE_CONFIG["season_weights"])

    banks, games_pool, synthetic = build_all_banks(
        rosters, projections, game_logs, league_tau, TRADE_CONFIG)
    replacement = build_replacement_bank(
        projections, rosters, league_tau, games_pool, TRADE_CONFIG)

    if synthetic:
        print(f"[note] {len(synthetic)} player(s) simulated from projection + league "
              f"tau rather than observed weeks: {', '.join(sorted(synthetic))}")

    result = evaluate_trade(rosters, banks, args.team, args.partner, give, get,
                            LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                            TRADE_CONFIG, replacement)
    print(format_report(result, args.team, args.partner, give, get))


if __name__ == "__main__":
    main()
