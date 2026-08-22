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

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LEAGUE_CONFIG, TRADE_CONFIG          # noqa: E402
from data import fetch_game_logs, fetch_tech_per_game   # noqa: E402
from model import compute_tau                            # noqa: E402
from rosters import (load_projections, load_rosters,      # noqa: E402
                     player_value_percentiles, resolve_roster_players)
from trade import (BANK_COLUMNS, add_missed_weeks,        # noqa: E402
                   build_week_bank, evaluate_trade,
                   games_per_week_pool, pooled_donor_bank,
                   quantize_bank_counts, scale_bank_to_projection,
                   synthesize_bank)


def parse_names(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _gp_factor_for(projected: pd.Series) -> float:
    """A player's GP_FACTOR, defaulting to 1.0 when absent/NaN (rookies)."""
    raw = projected.get("GP_FACTOR", 1.0)
    if raw is None or pd.isna(raw) or raw <= 0:
        return 1.0
    return float(raw)


def _true_rate_projection(projected: pd.Series, gp_factor: float) -> dict:
    """
    Undo model.py's GP_FACTOR bake-in across every BANK_COLUMNS category, so
    synthesize_bank's fallback path starts from the same TRUE per-game rate
    scale_bank_to_projection recovers for the bootstrapped path -- add_missed_weeks
    is what reintroduces availability afterwards, for both paths alike.
    """
    true_rates = dict(projected)
    for col in BANK_COLUMNS:
        if col == "GAMES":
            continue
        raw = projected.get(col, 0.0)
        if raw is None or pd.isna(raw):
            continue
        true_rates[col] = float(raw) / gp_factor
    return true_rates


def build_all_banks(rosters, projections, game_logs, league_tau, trade_config,
                    tech_rates=None):
    """
    One bank per rostered player.

    Three stages per player: rescale to their true per-game rate, reintroduce
    availability as whole missed weeks, then round the counts back to whole
    numbers so ties can happen. Players with too few observed weeks (every
    rookie) borrow a pooled shape of real weeks rather than drawing each
    category independently.
    """
    raw_banks = build_week_bank(game_logs, tech_rates)
    # Must be built from the raw, real-observed-week banks -- before any
    # add_missed_weeks zero rows exist anywhere -- or the synthetic fallback
    # would start drawing zero-game "weeks" from the pool.
    games_pool = games_per_week_pool(raw_banks)
    by_name = projections.set_index("PLAYER_NAME")

    banks, synthetic = {}, []
    for team_players in rosters.values():
        for player in team_players:
            projected = by_name.loc[player]
            gp_factor = _gp_factor_for(projected)
            raw = raw_banks.get(player)
            if raw is not None and raw.shape[0] >= trade_config["min_weeks_for_bootstrap"]:
                source = raw
            else:
                synthetic.append(player)
                source = _fallback_source(
                    player, projected, gp_factor, raw_banks, games_pool,
                    league_tau, trade_config)

            scaled = scale_bank_to_projection(
                source, projected, trade_config["scale_bounds"], gp_factor)
            banks[player] = quantize_bank_counts(
                add_missed_weeks(scaled, gp_factor), player, trade_config["seed"])
    return banks, games_pool, synthetic


def _fallback_source(player, projected, gp_factor, raw_banks, games_pool,
                     league_tau, trade_config):
    """
    Stand-in weeks for a player with no usable game log of their own.

    Preferred: borrow the pooled shape of real league weeks, so within-week
    cross-category correlation survives and the caller's rescale sets the
    level -- which also makes a genuinely zero projection come out exactly
    zero, instead of the old independent-normal path manufacturing production
    out of nothing by clipping its draws at zero.

    synthesize_bank remains only for the case where no real banks exist at all
    (a cold cache, or tests), and is fed true per-game rates so the caller's
    rescale is a near no-op rather than a second discount.
    """
    donor = pooled_donor_bank(raw_banks, player, trade_config["seed"],
                              trade_config.get("synthetic_bank_rows", 500))
    if donor is not None:
        return donor
    return synthesize_bank(
        player, _true_rate_projection(projected, gp_factor), league_tau,
        games_pool, trade_config["seed"], trade_config["synthetic_bank_rows"])


def build_replacement_bank(projections, rosters, league_tau, games_pool, trade_config,
                           raw_banks=None):
    """
    Replacement level = the lowest-ranked VETERAN in the projection pool.

    Veteran and rookie TOTAL_VALUE are not comparable (rookies are scored
    against the rookie population, veterans against the veteran pool -- see
    rosters.load_projections). Sorting the concatenated frame would land on
    a rookie, materially understating true replacement level. The pool is a
    veteran-ranked population, so replacement level is the pool_size-th
    ranked veteran, full stop.
    """
    pool_size = LEAGUE_CONFIG["num_teams"] * LEAGUE_CONFIG["roster_size"]
    veterans = projections[projections["SOURCE"] == "veteran"]
    ranked = veterans.sort_values("TOTAL_VALUE", ascending=False)
    replacement = ranked.iloc[min(pool_size, len(ranked)) - 1]

    gp_factor = _gp_factor_for(replacement)
    source = _fallback_source("__replacement_level__", replacement, gp_factor,
                              raw_banks or {}, games_pool, league_tau, trade_config)
    scaled = scale_bank_to_projection(
        source, replacement, trade_config.get("scale_bounds", (0.25, 4.0)), gp_factor)
    return quantize_bank_counts(add_missed_weeks(scaled, gp_factor),
                                "__replacement_level__", trade_config["seed"])


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

    # Each cell counts a tie as half a win, exactly as the headline does, so
    # the D column sums to the headline delta. Reporting raw win rates here
    # instead left a gap of ~14% between the table and the number it explains.
    def share(rates, cat):
        return rates[cat]["win"] + 0.5 * rates[cat]["tie"]

    lines.append(f"\nPer-category, {team}      BEFORE   AFTER       D    TIE%")
    before_rates = result["before"][team]["rates"]
    after_rates = result["after"][team]["rates"]
    ordered = sorted(before_rates,
                     key=lambda c: share(after_rates, c) - share(before_rates, c),
                     reverse=True)
    for cat in ordered:
        b, a = share(before_rates, cat), share(after_rates, cat)
        tie = after_rates[cat]["tie"] * 100
        lines.append(f"  {cat:<22} {b:6.3f}  {a:6.3f}  {a - b:+7.3f}  {tie:6.1f}")

    column_total = sum(share(after_rates, c) - share(before_rates, c)
                       for c in before_rates)
    headline = result["after"][team]["expected"] - result["before"][team]["expected"]
    lines.append(f"  {'(column sum)':<22} {'':6}  {'':6}  {column_total:+7.3f}"
                 f"   headline {headline:+.3f}")

    return "\n".join(lines)


def warn_league_shape(rosters: dict[str, list[str]]) -> list[str]:
    """
    Flag a roster file whose shape disagrees with the configured league.

    Nothing downstream validates this, so a file with four teams or nine-man
    rosters runs to completion and prints "vs league field" as though it meant
    the same thing. It does not: the field is whatever teams the file happens
    to contain.
    """
    warnings = []
    expected_teams = LEAGUE_CONFIG["num_teams"]
    expected_size = LEAGUE_CONFIG["roster_size"]

    if len(rosters) != expected_teams:
        warnings.append(
            f"roster file has {len(rosters)} teams, config expects {expected_teams} "
            f"-- 'vs league field' means these {len(rosters)} teams only")

    odd = {t: len(p) for t, p in rosters.items() if len(p) != expected_size}
    if odd:
        shown = ", ".join(f"{t}={n}" for t, n in sorted(odd.items()))
        warnings.append(
            f"roster sizes differ from the configured {expected_size}: {shown}")

    return warnings


def warn_data_quality(projections, rosters: dict[str, list[str]]) -> list[str]:
    """
    Surface per-player data caveats the projection pipeline already recorded.

    DATA_AVAILABILITY_NOTE flags players whose stats were blended around a
    missing season. Those notes exist upstream but never reached this report,
    so a verdict could rest on a player projected from stale data with nothing
    said about it.
    """
    if "DATA_AVAILABILITY_NOTE" not in projections.columns:
        return []

    rostered = {p for players in rosters.values() for p in players}
    by_name = projections.set_index("PLAYER_NAME")

    flagged = []
    for player in sorted(rostered):
        note = by_name.loc[player].get("DATA_AVAILABILITY_NOTE", "")
        if isinstance(note, str) and note.strip():
            flagged.append(f"{player}: {note.strip()}")
    return flagged


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

    # Real per-player technical-foul rates, so TECH is not simulated as a
    # fixed multiple of PF (which made fouls decide two categories at once).
    tech_rates = fetch_tech_per_game(
        LEAGUE_CONFIG["game_log_seasons"],
        LEAGUE_CONFIG["tech_cache"],
        LEAGUE_CONFIG["season_weights"],
    )

    banks, games_pool, synthetic = build_all_banks(
        rosters, projections, game_logs, league_tau, TRADE_CONFIG, tech_rates)
    raw_banks_for_donor = build_week_bank(game_logs, tech_rates)
    replacement = build_replacement_bank(
        projections, rosters, league_tau, games_pool, TRADE_CONFIG,
        raw_banks_for_donor)

    for warning in warn_league_shape(rosters):
        print(f"[warn] {warning}")

    if _health and (_health.get("degraded") or _health.get("missing_pair_count")):
        missing = _health.get("missing_pair_count", 0)
        print(f"[warn] game-log fetch is DEGRADED: {missing} player-season log(s) "
              f"missing -- those players are simulated from whatever seasons "
              f"remain, or from a pooled shape if none do")

    flagged = warn_data_quality(projections, rosters)
    if flagged:
        print(f"[note] {len(flagged)} rostered player(s) carry a data-availability "
              f"caveat from the projection pipeline:")
        for line in flagged:
            print(f"         {line}")

    if synthetic:
        print(f"[note] {len(synthetic)} player(s) have no usable game log and are "
              f"simulated from a pooled shape of real league weeks rescaled to "
              f"their projection: {', '.join(sorted(synthetic))}")

    player_values = player_value_percentiles(projections)
    result = evaluate_trade(rosters, banks, args.team, args.partner, give, get,
                            LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                            TRADE_CONFIG, replacement, player_values)
    print(format_report(result, args.team, args.partner, give, get))


if __name__ == "__main__":
    main()
