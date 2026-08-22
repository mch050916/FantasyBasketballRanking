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


def _weekly_totals(logs: pd.DataFrame,
                   tech_rate: float | None = None) -> np.ndarray | None:
    """
    Collapse one player-season game log into per-ISO-week totals.

    TECH: game logs carry no technical-foul column, so it has to come from
    somewhere else. When `tech_rate` is supplied (the player's real per-game
    rate from the league-wide endpoint) TECH is that rate times the week's
    games. Only when it is missing do we fall back to the PF proxy that
    compute_tau uses.

    That distinction matters more than it looks. The proxy makes TECH a fixed
    multiple of PF, so at team level the two categories correlate at ~0.9999
    and win or lose together -- silently letting fouls decide 2 of the
    league's 14 categories instead of 1.
    """
    logs = add_week_key(logs)
    grouped = logs.groupby("WEEK_KEY", sort=True)
    out = np.zeros((grouped.ngroups, len(BANK_COLUMNS)))
    games_per_week = grouped.size().values

    for i, col in enumerate(BANK_COLUMNS):
        if col == "GAMES":
            out[:, i] = games_per_week
        elif col == "TECH":
            if tech_rate is not None:
                out[:, i] = float(tech_rate) * games_per_week
                continue
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


def build_week_bank(game_logs: dict[str, dict[str, pd.DataFrame]],
                    tech_rates: dict[str, float] | None = None) -> dict[str, np.ndarray]:
    """
    Build each player's bank of real observed weeks across all cached seasons.

    Returns { player_name -> array of shape (n_weeks, len(BANK_COLUMNS)) }.
    Unlike compute_tau, seasons are NOT recency-weighted here: every observed
    week is one equally likely draw. Recency enters through the projection
    rescale in scale_bank_to_projection, which is already recency-weighted.

    `tech_rates` maps player name to a real per-game technical-foul rate; when
    supplied it replaces the PF proxy for that player. See _weekly_totals.
    """
    frames: dict[str, list[np.ndarray]] = {}
    tech_rates = tech_rates or {}

    for season_logs in game_logs.values():
        for player_name, logs in season_logs.items():
            if logs is None or logs.empty:
                continue
            weekly = _weekly_totals(logs, tech_rates.get(player_name))
            if weekly is None or weekly.shape[0] == 0:
                continue
            frames.setdefault(player_name, []).append(weekly)

    return {name: np.vstack(chunks) for name, chunks in frames.items()}


def scale_bank_to_projection(bank: np.ndarray,
                             projected: dict | pd.Series,
                             scale_bounds: tuple[float, float] = (0.25, 4.0),
                             gp_factor: float = 1.0) -> np.ndarray:
    """
    Rescale a bank of observed weekly totals to this season's TRUE per-game rate.

    scale = target_per_game / historical_per_game, applied per category,
    where target_per_game = projected_per_game / gp_factor.

    model.py bakes GP_FACTOR (and DECLINE_FACTOR) into every projected rate
    (model.py:530, 540-544) -- but this bank's GAMES column is empirical and
    already reflects the player's real availability on its own. Rescaling
    straight to the projected rate would apply availability twice, and for
    the low-is-better categories (TO, PF, TECH) it makes a fragile player
    look artificially clean (GP_FACTOR < 1 shrinks a bad number further).
    Dividing by gp_factor here undoes model.py's bake-in and recovers the
    TRUE per-game rate a healthy week actually produces; add_missed_weeks
    (below) is what reintroduces availability afterwards, as whole missed
    weeks rather than a smear across every stat.

    DECLINE_FACTOR is NOT undone here -- it is a genuine change in per-game
    rate (aging/decline), not an availability effect, so it stays baked into
    the target.

    Two guards, preserved exactly as before:
      - historical rate ~= 0 (TD for most of the pool) leaves scale at 1.0,
        so a player who never recorded one keeps simulating zeros.
      - scale is clipped so a tiny denominator cannot explode a category.

    A missing, zero, non-finite, or otherwise unusable gp_factor falls back
    to 1.0 (no correction), so callers that do not pass one reproduce the
    prior behaviour exactly.
    """
    scaled = bank.copy()
    games_idx = BANK_COLUMNS.index("GAMES")
    total_games = bank[:, games_idx].sum()
    if not np.isfinite(total_games) or total_games <= 0:
        return scaled

    if gp_factor is None or not np.isfinite(gp_factor) or gp_factor <= 0:
        gp_factor = 1.0

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
            target_per_game = projected_per_game / gp_factor
            scale = float(np.clip(target_per_game / historical_per_game, *scale_bounds))

        scaled[:, i] = bank[:, i] * scale

    return scaled


# Below this, a stray near-zero availability could blow up the number of
# synthetic missed-week rows appended in add_missed_weeks. Real inputs never
# approach this floor -- GP_FACTOR itself is clipped to [0.50, 1.0]
# (compute_gp_factor, model.py) -- this only guards against a pathological
# caller.
MIN_AVAILABILITY_FOR_MISSED_WEEKS = 0.05


def add_missed_weeks(bank: np.ndarray, availability: float) -> np.ndarray:
    """
    Append all-zero weeks to a bank in proportion to a player's unavailability.

    A fragile player does not produce slightly less every week -- they
    produce nothing at all in the weeks they miss, including the
    low-is-better categories (TO, PF, TECH). That is the point: a missed
    week contributes zero turnovers *and* zero points, which is what
    scale_bank_to_projection's TRUE-rate rescale (above) depends on to avoid
    double-discounting availability.

    `availability` is expected to be a player's GP_FACTOR -- already
    clip(weighted_GP / 82, 0.50, 1.0) in compute_gp_factor (model.py), i.e.
    directly a fraction of the season played. Its 0.50 floor means even the
    most fragile players in the pool are modelled here as missing at most
    half their weeks.

    Given a bank of N real rows, Z = round(N * (1 - availability) /
    availability) all-zero rows are appended, so a uniform draw over the
    resulting bank hits a zero row with probability (1 - availability).

    availability >= 1.0, missing/non-finite, or a bank with no real rows to
    base a proportion on returns the bank unchanged. Otherwise availability
    is clamped to MIN_AVAILABILITY_FOR_MISSED_WEEKS so Z cannot explode.

    Deliberately does not draw a per-week random "was this week missed"
    boolean -- that would add a second random stream on top of
    player_rng's name-keyed draw index and risk breaking the exact-zero
    null-trade guarantee common random numbers relies on. The bank itself
    grows; the existing draw-index stream does the rest.
    """
    if bank.shape[0] == 0:
        return bank
    if availability is None or not np.isfinite(availability) or availability >= 1.0:
        return bank

    availability = max(float(availability), MIN_AVAILABILITY_FOR_MISSED_WEEKS)
    n_rows = bank.shape[0]
    n_zero = round(n_rows * (1.0 - availability) / availability)
    if n_zero <= 0:
        return bank

    zero_rows = np.zeros((n_zero, bank.shape[1]))
    return np.vstack([bank, zero_rows])


# Every category except FG% is a count of something that happened. FG% is
# derived from the FGM and FGA counts, so it needs no entry here.
COUNT_COLUMNS = [c for c in BANK_COLUMNS if c != "GAMES"]


def quantize_bank_counts(bank: np.ndarray, player_name: str, seed: int) -> np.ndarray:
    """
    Round a rescaled bank's count columns back to whole numbers.

    Why this exists: a real weekly total is an integer -- you cannot record
    3.7 double-doubles or 0.4 technical fouls. The projection rescale turns
    those integers into continuous values, and two continuous team totals are
    essentially never exactly equal, so ties disappear. That silently guts the
    reason this simulator resamples real weeks instead of assuming normal
    marginals: the sparse categories (DD, TD, TECH) are precisely the ones
    where both teams realistically finish level, and a tie is not a win.

    Rounding is *stochastic* -- 3.7 becomes 4 with probability 0.7 and 3 with
    probability 0.3 -- so the mean survives. Plain rounding would bias every
    low-rate category toward zero.

    The draw is keyed to the player's name and applied ONCE at bank-build
    time, so the result is baked into a fixed bank. That is deliberate: adding
    randomness at draw time would introduce a second stream and put the
    exact-zero null-trade guarantee at risk.
    """
    rng = player_rng(player_name, seed, purpose="quantize")
    out = bank.astype(float).copy()

    for col in COUNT_COLUMNS:
        i = BANK_COLUMNS.index(col)
        values = out[:, i]
        floor = np.floor(values)
        out[:, i] = floor + (rng.random(values.shape[0]) < (values - floor))

    return out


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


def pooled_donor_bank(banks: dict[str, np.ndarray],
                      player_name: str,
                      seed: int,
                      n_rows: int = 500) -> np.ndarray | None:
    """
    Borrow the SHAPE of real weeks for a player who has none of their own.

    Rookies have no game logs at all, so something has to stand in. Drawing
    each category from an independent normal -- the previous approach -- has
    two faults: clipping the draw at zero manufactures production out of a
    zero projection, and independent draws destroy the within-week
    cross-category correlation that resampling real weeks exists to preserve.

    Sampling real weeks from the pool instead keeps that correlation (a big
    scoring week is still a big FGM week), and the caller rescales the result
    to the player's own projection, which sets the level and makes a zero
    projection come out exactly zero.

    The shape is pooled across the whole league rather than matched to a
    similar player -- an average of real shapes, not a bespoke one. Returns
    None when no real banks exist to borrow from.
    """
    real = [b for b in banks.values() if b.shape[0] > 0]
    if not real:
        return None

    pool = np.vstack(real)
    rng = player_rng(player_name, seed, purpose="donor")
    return pool[rng.integers(0, pool.shape[0], size=n_rows)].copy()


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


REPLACEMENT_PREFIX = "__replacement__"


def apply_trade(rosters: dict[str, list[str]],
                team: str,
                partner: str,
                give: list[str],
                get: list[str]) -> dict[str, list[str]]:
    """Return a new roster mapping with the trade applied. Input untouched."""
    for name in (team, partner):
        if name not in rosters:
            raise KeyError(f"'{name}' is not one of the league rosters: {sorted(rosters)}")

    missing_give = [p for p in give if p not in rosters[team]]
    if missing_give:
        raise ValueError(f"{team} cannot give players they do not roster: {missing_give}")

    missing_get = [p for p in get if p not in rosters[partner]]
    if missing_get:
        raise ValueError(f"{partner} cannot give players they do not roster: {missing_get}")

    updated = {name: list(players) for name, players in rosters.items()}
    updated[team] = [p for p in updated[team] if p not in give] + list(get)
    updated[partner] = [p for p in updated[partner] if p not in get] + list(give)
    return updated


def pad_to_roster_size(rosters: dict[str, list[str]],
                       banks: dict[str, np.ndarray],
                       roster_size: int,
                       replacement_bank: np.ndarray) -> tuple[dict, dict]:
    """
    Fill short rosters with replacement-level players.

    Without this a 2-for-1 looks artificially bad: a 12-man roster would be
    simulated against 13-man ones, and the missing slot would read as a
    deficit in every category.

    Replacement slots are named per team and index so their random streams
    stay stable across runs.
    """
    padded_rosters = {name: list(players) for name, players in rosters.items()}
    padded_banks = dict(banks)

    for team, players in padded_rosters.items():
        for i in range(len(players), roster_size):
            slot = f"{REPLACEMENT_PREFIX}{team}_{i}"
            padded_banks[slot] = replacement_bank
            players.append(slot)

    return padded_rosters, padded_banks


def trim_to_roster_size(rosters: dict[str, list[str]],
                        banks: dict[str, np.ndarray],
                        roster_size: int,
                        player_values: dict[str, float]) -> tuple[dict, dict]:
    """
    Drop the lowest-valued players off any roster longer than roster_size.

    An uneven trade (e.g. 2-for-1) can leave the receiving side with more
    players than a legal roster -- real fantasy forces a drop in that
    situation, and the simulation must too, or that side plays every
    opponent a player up. This is an approximation of a manager's drop
    decision, not a claim about true relative value: a real manager weighs
    positional need and category fit that a single scalar cannot capture.

    player_values maps player name -> a comparable float, higher is better.
    It is expected to be a within-source percentile rank of TOTAL_VALUE (see
    rosters.player_value_percentiles) rather than raw TOTAL_VALUE -- raw
    veteran and rookie TOTAL_VALUE are not on the same scale (see
    rosters.load_projections' SOURCE column), so raw values here would bias
    every trim toward dropping rookies regardless of who is actually worse.
    Players absent from player_values sort last (dropped first) -- a name
    with no known value is not one to keep over a ranked player.

    Rosters at or under roster_size are left untouched, in their original
    order. Does not mutate its inputs.
    """
    trimmed_rosters = {name: list(players) for name, players in rosters.items()}
    trimmed_banks = dict(banks)

    for team, players in trimmed_rosters.items():
        if len(players) <= roster_size:
            continue
        ranked = sorted(players,
                        key=lambda p: player_values.get(p, float("-inf")),
                        reverse=True)
        trimmed_rosters[team] = ranked[:roster_size]

    return trimmed_rosters, trimmed_banks


def evaluate_trade(rosters: dict[str, list[str]],
                   banks: dict[str, np.ndarray],
                   team: str,
                   partner: str,
                   give: list[str],
                   get: list[str],
                   categories: dict,
                   config: dict,
                   trade_config: dict,
                   replacement_bank: np.ndarray,
                   player_values: dict[str, float] | None = None) -> dict:
    """
    Evaluate a two-team trade against the league field, before and after.

    Both runs share one seed, and every player's draws are keyed to their own
    name, so untraded players contribute identical weeks on both sides and the
    delta isolates the traded players rather than Monte Carlo noise.

    An uneven trade (e.g. 2-for-1) leaves one side short and the other over
    the legal roster size. When player_values is supplied, any post-trade
    roster longer than roster_size is trimmed down (trim_to_roster_size)
    before short rosters are padded up (pad_to_roster_size), so both sides of
    an uneven trade simulate a legal roster. When player_values is None,
    trimming is skipped entirely -- existing callers that only ever pad keep
    their prior behaviour exactly.
    """
    seed = trade_config["seed"]
    n_weeks = trade_config["weeks_per_opponent"]
    roster_size = max([config["roster_size"]] + [len(p) for p in rosters.values()])

    after_rosters = apply_trade(rosters, team, partner, give, get)

    def evaluate_all(source: dict[str, list[str]]) -> dict:
        if player_values is not None:
            source, source_banks = trim_to_roster_size(
                source, banks, roster_size, player_values)
        else:
            source_banks = banks
        padded_rosters, padded_banks = pad_to_roster_size(
            source, source_banks, roster_size, replacement_bank)
        out = {}
        for name in padded_rosters:
            expected, rates = evaluate_roster_vs_field(
                name, padded_rosters, padded_banks, categories, n_weeks, seed)
            out[name] = {"expected": expected, "rates": rates}
        return out

    before = evaluate_all(rosters)
    after = evaluate_all(after_rosters)

    delta = {
        name: {
            "expected": after[name]["expected"] - before[name]["expected"],
            "rates": {
                cat: after[name]["rates"][cat]["win"] - before[name]["rates"][cat]["win"]
                for cat in before[name]["rates"]
            },
        }
        for name in before
    }

    return {"before": before, "after": after, "delta": delta,
            "roster_sizes_after": {n: len(p) for n, p in after_rosters.items()}}
