"""
trade.py — Trade analyzer engine
=================================
Simulates a fantasy week by resampling each player's real observed weeks from
the cached game logs, rescaled to this season's projection, and counts how
often a roster wins each category against the league field.

Pure functions only: no file I/O, no printing. See scripts/analyze_trade.py.
"""

import zlib

import numpy as np
import pandas as pd

from model import add_week_key


SIM_CATEGORIES = ["FGM", "FTM", "3PTM", "PTS", "REB", "AST",
                  "ST", "BLK", "TO", "PF", "DD", "TD", "TECH"]

# FGA rides along because FG% is aggregated as sum(FGM)/sum(FGA), never as a
# mean of per-player ratios. GAMES is needed to convert weekly totals back to
# a per-game rate for the projection rescale.
BANK_COLUMNS = SIM_CATEGORIES + ["FGA", "GAMES"]

# Same mapping compute_tau uses, so both read the game logs identically.
API_COL_MAP = {"ST": "STL", "TO": "TOV", "3PTM": "FG3M", "DD": "DD2", "TD": "TD3"}

TECH_PER_PF = 0.012

# Used when no game-log banks exist at all (tests, cold cache). Roughly the
# real distribution of games in an NBA fantasy week.
NOMINAL_GAMES_POOL = np.array([2.0, 3.0, 3.0, 4.0])

_WARNED_COLUMNS: set[str] = set()


def _warn_missing_column(column: str) -> None:
    """
    Warn once per absent game-log column, then treat it as zeros.

    Dropping the whole player-season instead would empty every bank on one
    missing column and silently route the entire league to the synthetic
    fallback -- a far worse failure than one category reading zero.
    """
    if column not in _WARNED_COLUMNS:
        _WARNED_COLUMNS.add(column)
        print(f"  [warn] game logs have no '{column}' column; treating it as zero")


def _weekly_totals(logs: pd.DataFrame) -> np.ndarray | None:
    """Collapse one player-season game log into per-ISO-week totals."""
    logs = add_week_key(logs)
    grouped = logs.groupby("WEEK_KEY", sort=True)
    out = np.zeros((grouped.ngroups, len(BANK_COLUMNS)))

    for i, col in enumerate(BANK_COLUMNS):
        if col == "GAMES":
            out[:, i] = grouped.size().values
        elif col == "TECH":
            if "PF" not in logs.columns:
                _warn_missing_column("PF")
                continue
            out[:, i] = grouped["PF"].sum().values * TECH_PER_PF
        else:
            api_col = API_COL_MAP.get(col, col)
            if api_col not in logs.columns:
                _warn_missing_column(api_col)
                continue
            out[:, i] = grouped[api_col].sum().values

    return out


def build_week_bank(game_logs: dict[str, dict[str, pd.DataFrame]]) -> dict[str, np.ndarray]:
    """
    Build each player's bank of real observed weeks across all cached seasons.

    Returns { player_name -> array of shape (n_weeks, len(BANK_COLUMNS)) }.
    Unlike compute_tau, seasons are NOT recency-weighted here: every observed
    week is one equally likely draw. Recency enters through the projection
    rescale in scale_bank_to_projection, which is already recency-weighted.
    """
    frames: dict[str, list[np.ndarray]] = {}

    for season_logs in game_logs.values():
        for player_name, logs in season_logs.items():
            if logs is None or logs.empty:
                continue
            weekly = _weekly_totals(logs)
            if weekly is None or weekly.shape[0] == 0:
                continue
            frames.setdefault(player_name, []).append(weekly)

    return {name: np.vstack(chunks) for name, chunks in frames.items()}


def scale_bank_to_projection(bank: np.ndarray,
                             projected: dict | pd.Series,
                             scale_bounds: tuple[float, float] = (0.25, 4.0)) -> np.ndarray:
    """
    Rescale a bank of observed weekly totals to this season's projected rates.

    scale = projected_per_game / historical_per_game, applied per category.

    Two guards:
      - historical rate ~= 0 (TD for most of the pool) leaves scale at 1.0,
        so a player who never recorded one keeps simulating zeros.
      - scale is clipped so a tiny denominator cannot explode a category.

    GP_FACTOR and DECLINE_FACTOR are already baked into the projected rates,
    so availability is inherited here -- including GP_FACTOR's known
    over-discount asymmetry (GitHub issue #7). Inherited deliberately, not
    corrected.
    """
    scaled = bank.copy()
    games_idx = BANK_COLUMNS.index("GAMES")
    total_games = bank[:, games_idx].sum()
    if not np.isfinite(total_games) or total_games <= 0:
        return scaled

    for i, col in enumerate(BANK_COLUMNS):
        if col == "GAMES":
            continue

        historical_per_game = bank[:, i].sum() / total_games
        if historical_per_game < 1e-6:
            continue

        raw = projected.get(col, 0.0)
        projected_per_game = 0.0 if raw is None or pd.isna(raw) else float(raw)

        if projected_per_game <= 0.0:
            # A genuinely zero projection means zero. The clip below guards a
            # tiny DENOMINATOR from exploding a category -- it is not a floor
            # under a legitimate zero numerator.
            scale = 0.0
        else:
            scale = float(np.clip(projected_per_game / historical_per_game, *scale_bounds))

        scaled[:, i] = bank[:, i] * scale

    return scaled


def player_rng(player_name: str, seed: int, purpose: str = "draw") -> np.random.Generator:
    """
    Deterministic per-player generator.

    Keying the stream to the player's NAME rather than their position in a
    roster list is what makes common random numbers work: a player draws the
    same weeks whichever roster they sit on and whichever run this is, so a
    before/after trade delta isolates the traded players instead of drowning
    in Monte Carlo noise.

    crc32, not the builtin hash() -- hash() is salted per process by
    PYTHONHASHSEED and would silently break reproducibility.
    """
    key = zlib.crc32(f"{purpose}:{player_name}".encode("utf-8"))
    return np.random.default_rng(key ^ seed)


def games_per_week_pool(banks: dict[str, np.ndarray]) -> np.ndarray:
    """Every observed week length in the league, as a sampling pool."""
    games_idx = BANK_COLUMNS.index("GAMES")
    observed = [bank[:, games_idx] for bank in banks.values() if bank.shape[0] > 0]
    if not observed:
        return NOMINAL_GAMES_POOL
    return np.concatenate(observed)


def synthesize_bank(player_name: str,
                    projected: dict | pd.Series,
                    league_tau: dict[str, float],
                    games_pool: np.ndarray,
                    seed: int,
                    n_rows: int = 500) -> np.ndarray:
    """
    Build a bank for a player with too few (or no) observed weeks.

    Draws a per-game rate from N(projected_rate, league_tau) and multiplies by
    a games count drawn from the league's empirical week lengths, so the rows
    land in the same weekly-total units as a bootstrapped bank and can be
    summed alongside one.

    league_tau has no entry for FGA, so FGA comes out proportional to its
    projected rate with no week-to-week noise. That makes a fallback player's
    FG% vary only through FGM. Acceptable: this path exists for rookies and
    cache misses, not for the players a trade usually turns on.
    """
    rng = player_rng(player_name, seed, purpose="synth")
    games = rng.choice(games_pool, size=n_rows)

    out = np.zeros((n_rows, len(BANK_COLUMNS)))
    out[:, BANK_COLUMNS.index("GAMES")] = games

    for i, col in enumerate(BANK_COLUMNS):
        if col == "GAMES":
            continue
        raw = projected.get(col, 0.0)
        mean = 0.0 if raw is None or pd.isna(raw) else float(raw)
        tau = float(league_tau.get(col, 0.0) or 0.0)
        per_game = rng.normal(mean, tau, size=n_rows) if tau > 0 else np.full(n_rows, mean)
        out[:, i] = np.maximum(per_game, 0.0) * games

    return out


def simulate_team_totals(roster_banks: dict[str, np.ndarray],
                         n_weeks: int,
                         seed: int) -> np.ndarray:
    """
    Draw n_weeks simulated weeks and sum every rostered player's line.

    Each player's draws come from their own name-keyed stream, so roster order
    does not affect the result and an untraded player contributes identical
    numbers across a before/after pair.
    """
    totals = np.zeros((n_weeks, len(BANK_COLUMNS)))
    # sorted(), not dict order: float addition is not associative, so summing
    # the same roster in a different order can give bitwise-different totals.
    # That would break the exact-zero null-trade guarantee the whole
    # common-random-numbers design rests on (see also GitHub issue #9).
    for player_name in sorted(roster_banks):
        bank = roster_banks[player_name]
        if bank.shape[0] == 0:
            continue
        rng = player_rng(player_name, seed)
        idx = rng.integers(0, bank.shape[0], size=n_weeks)
        totals += bank[idx]
    return totals


def _fg_pct(totals: np.ndarray) -> np.ndarray:
    """Team FG% as sum(FGM)/sum(FGA) -- never a mean of per-player ratios."""
    fgm = totals[:, BANK_COLUMNS.index("FGM")]
    fga = totals[:, BANK_COLUMNS.index("FGA")]
    return np.divide(fgm, fga, out=np.zeros_like(fgm), where=fga > 0)


def category_win_rates(a_totals: np.ndarray,
                       b_totals: np.ndarray,
                       categories: dict) -> dict[str, dict[str, float]]:
    """Per-category win / tie / loss rates for team A against team B."""
    rates: dict[str, dict[str, float]] = {}

    for cat, meta in categories.items():
        if cat == "FG%":
            a, b = _fg_pct(a_totals), _fg_pct(b_totals)
        elif cat in BANK_COLUMNS:
            i = BANK_COLUMNS.index(cat)
            a, b = a_totals[:, i], b_totals[:, i]
        else:
            continue

        if meta["direction"] == "high":
            wins, losses = a > b, a < b
        else:
            wins, losses = a < b, a > b

        rates[cat] = {"win": float(wins.mean()),
                      "loss": float(losses.mean()),
                      "tie": float((~(wins | losses)).mean())}

    return rates


def expected_categories_won(rates: dict[str, dict[str, float]]) -> float:
    """
    E[categories won] = sum P(win) + 0.5 * sum P(tie).

    Exact under linearity of expectation even though categories correlate --
    correlation moves the variance of a week's outcome, not this mean.
    """
    return sum(r["win"] + 0.5 * r["tie"] for r in rates.values())


def evaluate_roster_vs_field(team: str,
                             rosters: dict[str, list[str]],
                             banks: dict[str, np.ndarray],
                             categories: dict,
                             n_weeks: int,
                             seed: int) -> tuple[float, dict[str, dict[str, float]]]:
    """
    Average this roster's per-category rates over every other team.

    Returns (expected categories won per week, per-category rates).
    """
    if team not in rosters:
        raise KeyError(f"'{team}' is not one of the league rosters: {sorted(rosters)}")

    own = simulate_team_totals({p: banks[p] for p in rosters[team]}, n_weeks, seed)

    opponents = [t for t in rosters if t != team]
    if not opponents:
        raise KeyError("Need at least two rosters to evaluate against a field")

    summed: dict[str, dict[str, float]] = {}
    for opponent in opponents:
        their = simulate_team_totals({p: banks[p] for p in rosters[opponent]},
                                     n_weeks, seed)
        for cat, rate in category_win_rates(own, their, categories).items():
            bucket = summed.setdefault(cat, {"win": 0.0, "tie": 0.0, "loss": 0.0})
            for outcome in bucket:
                bucket[outcome] += rate[outcome]

    averaged = {cat: {k: v / len(opponents) for k, v in bucket.items()}
                for cat, bucket in summed.items()}

    return expected_categories_won(averaged), averaged
