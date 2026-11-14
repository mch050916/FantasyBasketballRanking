"""
Weekly H2H roster simulation for category-balance measurement.

Estimates each player's marginal matchup value by drawing random rosters
from a player pool, playing actual weekly matchups, and attributing the
category-win margin to each player on the roster.

TECH is excluded (only PF proxy exists in game logs).
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import LEAGUE_CONFIG
from model import add_week_key

ROSTER_SIZE = LEAGUE_CONFIG["roster_size"]
CATS = list(LEAGUE_CONFIG["categories"].keys())
CAT_META = LEAGUE_CONFIG["categories"]
SIM_CATS = [c for c in CATS if c != "TECH"]

API_COL = {
    "FGM": "FGM", "FGA": "FGA", "FTM": "FTM", "3PTM": "FG3M",
    "PTS": "PTS", "REB": "REB", "AST": "AST", "ST": "STL",
    "BLK": "BLK", "TO": "TOV", "PF": "PF", "DD": "DD2", "TD": "TD3",
}


def canonical_key(name: str) -> str:
    return name.lower().replace(" ", "").replace(".", "").replace("-", "").replace("'", "")


def load_actuals_logs(target: str) -> dict[str, pd.DataFrame]:
    slug = target.replace("-", "_")
    path = Path(f"game_log_cache_{slug}_actuals.pkl")
    with open(path, "rb") as f:
        d = pickle.load(f)
    payload = d["payload"] if "payload" in d else d
    result = {}
    for pname, df in payload[target].items():
        if df.empty:
            continue
        df = add_week_key(df.copy())
        result[canonical_key(pname)] = df
    return result


def _build_weekly_stat_matrix(logs, player_keys, weeks):
    n_w, n_p = len(weeks), len(player_keys)
    sum_cats = [c for c in SIM_CATS if c != "FG%"]
    wi_map = {w: i for i, w in enumerate(weeks)}
    pi_map = {p: i for i, p in enumerate(player_keys)}
    sums = np.zeros((n_w, n_p, len(sum_cats)))
    fgm = np.zeros((n_w, n_p))
    fga = np.zeros((n_w, n_p))
    for pk in player_keys:
        if pk not in logs:
            continue
        pi = pi_map[pk]
        for _, g in logs[pk].iterrows():
            wk = g.get("WEEK_KEY")
            if wk not in wi_map:
                continue
            wi = wi_map[wk]
            for ci, cat in enumerate(sum_cats):
                v = g.get(API_COL.get(cat, cat), 0)
                if pd.notna(v):
                    sums[wi, pi, ci] += float(v)
            v = g.get("FGM", 0)
            if pd.notna(v):
                fgm[wi, pi] += float(v)
            v = g.get("FGA", 0)
            if pd.notna(v):
                fga[wi, pi] += float(v)
    return sums, fgm, fga, sum_cats


def _score_matchup(ra, rb, ws, fgm, fga, sum_cats):
    aw, bw = 0, 0
    for ci, cat in enumerate(sum_cats):
        at = ws[ra, ci].sum()
        bt = ws[rb, ci].sum()
        if CAT_META[cat]["direction"] == "low":
            at, bt = -at, -bt
        if at > bt:
            aw += 1
        elif bt > at:
            bw += 1
    af, aa = fgm[ra].sum(), fga[ra].sum()
    bf, ba = fgm[rb].sum(), fga[rb].sum()
    ap = af / aa if aa > 0 else 0
    bp = bf / ba if ba > 0 else 0
    if ap > bp:
        aw += 1
    elif bp > ap:
        bw += 1
    return aw, bw


def simulate_player_values(
    logs: dict[str, pd.DataFrame],
    player_keys: list[str],
    n_rosters: int = 2000,
    seed: int = 42,
    roster_size: int | None = None,
) -> np.ndarray:
    """
    Estimate each player's marginal H2H matchup value.

    Returns an array of length len(player_keys) where higher = more
    category wins contributed to rosters the player was on.
    """
    rs = roster_size or ROSTER_SIZE
    rng = np.random.default_rng(seed)
    n = len(player_keys)

    weeks = sorted(
        set(w for pk in player_keys if pk in logs for w in logs[pk]["WEEK_KEY"].unique())
    )
    nw = len(weeks)
    if nw == 0:
        return np.zeros(n)

    sums, fgm, fga, sc = _build_weekly_stat_matrix(logs, player_keys, weeks)

    marg = np.zeros(n)
    cnt = np.zeros(n)
    for _ in range(n_rosters):
        perm = rng.permutation(n)
        ra, rb = perm[:rs], perm[rs : 2 * rs]
        ta, tb = 0, 0
        for wi in range(nw):
            a, b = _score_matchup(ra, rb, sums[wi], fgm[wi], fga[wi], sc)
            ta += a
            tb += b
        m = ta - tb
        for pi in ra:
            marg[pi] += m
            cnt[pi] += 1
        for pi in rb:
            marg[pi] += -m
            cnt[pi] += 1
    return np.where(cnt > 0, marg / cnt, 0.0)


def h2h_target_for_season(
    target: str, player_keys: list[str], n_rosters: int = 2000
) -> np.ndarray:
    """
    Convenience: load actual game logs for `target` season and return the
    averaged-over-two-seeds H2H target values for `player_keys`.
    """
    logs = load_actuals_logs(target)
    v1 = simulate_player_values(logs, player_keys, n_rosters=n_rosters, seed=42)
    v2 = simulate_player_values(logs, player_keys, n_rosters=n_rosters, seed=123)
    return (v1 + v2) / 2
