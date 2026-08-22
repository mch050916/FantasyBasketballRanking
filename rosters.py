"""
rosters.py — League roster loading for the trade analyzer
==========================================================
Reads rosters.csv (TEAM,PLAYER_NAME) and resolves every name against the
projection files, so a typo fails loudly instead of silently dropping a
player out of a simulated roster.
"""

import difflib
from pathlib import Path

import pandas as pd

from identity import canonical_player_key


def load_rosters(path: str | Path) -> dict[str, list[str]]:
    """Load rosters.csv into { team -> [player names in file order] }."""
    df = pd.read_csv(path)

    missing = [c for c in ("TEAM", "PLAYER_NAME") if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s): {missing}. "
            f"Expected a CSV with headers TEAM,PLAYER_NAME"
        )

    df["TEAM"] = df["TEAM"].astype(str).str.strip()
    df["PLAYER_NAME"] = df["PLAYER_NAME"].astype(str).str.strip()

    # Check for duplicate players (same player on multiple teams, accounting for accents).
    canonical_to_entries = {}
    for team, player in zip(df["TEAM"], df["PLAYER_NAME"]):
        key = canonical_player_key(player)
        if key not in canonical_to_entries:
            canonical_to_entries[key] = []
        canonical_to_entries[key].append((team, player))

    duplicates = {key: entries for key, entries in canonical_to_entries.items() if len(entries) > 1}
    if duplicates:
        collision_strs = []
        for key, entries in duplicates.items():
            team_spellings = [f"Team {team}: '{player}'" for team, player in entries]
            collision_strs.append(f"{', '.join(team_spellings)}")
        raise ValueError(f"Player(s) rostered by more than one team: {'; '.join(collision_strs)}")

    rosters: dict[str, list[str]] = {}
    for team, player in zip(df["TEAM"], df["PLAYER_NAME"]):
        rosters.setdefault(team, []).append(player)
    return rosters


def load_projections(rankings_path: str | Path,
                     rookie_path: str | Path | None = None) -> pd.DataFrame:
    """
    Load projected per-game stats, veterans plus rookies.

    Rookies live in a separate file because they are ranked against their own
    population rather than the veteran pool (see the 2026-08-14 rookie
    incorporation spec). For trade purposes they are just more players.

    Adds a SOURCE column ("veteran" or "rookie") so downstream code (replacement-
    level selection, within-source percentile ranking for roster trimming) can
    tell the two incomparable TOTAL_VALUE scales apart.
    """
    veterans = pd.read_csv(rankings_path)
    veterans["SOURCE"] = "veteran"
    frames = [veterans]
    if rookie_path is not None and Path(rookie_path).exists():
        rookies = pd.read_csv(rookie_path)
        rookies["SOURCE"] = "rookie"
        frames.append(rookies)
    return pd.concat(frames, ignore_index=True)


def player_value_percentiles(projections: pd.DataFrame) -> dict[str, float]:
    """
    Within-source percentile rank of TOTAL_VALUE, keyed by PLAYER_NAME.

    Veteran and rookie TOTAL_VALUE are not on the same scale -- rookies are
    scored against the rookie population, veterans against the veteran pool
    (see load_projections' SOURCE column) -- so ranking the concatenated
    frame directly would put every rookie below the worst veteran. Ranking
    within each SOURCE group first, then converting to a 0-1 percentile,
    makes a top rookie and a top veteran read as comparably "good relative
    to their own population," which is what a manager's drop decision
    approximates (see trade.trim_to_roster_size, the consumer of this).
    """
    out: dict[str, float] = {}
    for _, group in projections.groupby("SOURCE"):
        percentiles = group["TOTAL_VALUE"].rank(pct=True)
        out.update(zip(group["PLAYER_NAME"], percentiles))
    return out


def resolve_roster_players(rosters: dict[str, list[str]],
                           projections: pd.DataFrame) -> dict[str, list[str]]:
    """
    Map every rostered name onto its exact PLAYER_NAME in the projections.

    Matching goes through identity.canonical_player_key, so accents and
    punctuation differences resolve. Anything left unmatched raises with
    difflib near-misses attached -- a silently dropped player would quietly
    shrink a simulated roster and bias every category.
    """
    by_key = {}
    for name in projections["PLAYER_NAME"]:
        by_key.setdefault(canonical_player_key(name), name)

    resolved: dict[str, list[str]] = {}
    problems: list[str] = []

    for team, players in rosters.items():
        resolved[team] = []
        for player in players:
            match = by_key.get(canonical_player_key(player))
            if match is None:
                close = difflib.get_close_matches(
                    player, list(projections["PLAYER_NAME"]), n=3, cutoff=0.7)
                hint = f" Did you mean: {', '.join(close)}?" if close else \
                       " No similar name found in the projections."
                problems.append(f"  {team}: '{player}' not in projections.{hint}")
                continue
            resolved[team].append(match)

    if problems:
        raise ValueError("Could not resolve these rostered players:\n"
                         + "\n".join(problems))

    return resolved
