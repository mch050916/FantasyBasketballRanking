"""
causes.py — Shared per-player-season cause attribution
=========================================================
Reconciles data `main.py` already fetches (confirmed-injury text, per-season
BBR team) into one cause label per player-season: "full_season" (not a
shortfall), "injury_confirmed", "team_change", or "unexplained" (the
existing fail-closed default every current mechanism already falls back
to). Pure functions only -- no file I/O, same convention trade.py already
establishes.

Consumed by model.py's compute_gp_factor (to stop double-discounting a
season injury_factor already penalizes) and validate.py's
classify_miss_bucket (to stop guessing a miss's cause from statistical
shape alone when a real cause is already known).
"""

import pandas as pd

from data import MULTI_TEAM_MARKER_RE, classify_injury_tier
from identity import canonical_player_key

# Same threshold validate.py's classify_miss_bucket already uses to flag a
# real availability shortfall (validate.py:319) -- reused here rather than
# inventing a second "what counts as a shortfall" number.
FULL_SEASON_GP_RATIO = 0.78


def attribute_season_cause(gp: float,
                           full_season_games: int,
                           bbr_team: str,
                           severe_reasons: list[str]) -> str:
    """
    Classify one player-season's GP shortfall by cause, worst-to-most-
    specific, first match wins -- same precedent as classify_injury_tier's
    own tier ordering.

    A near-full season needs no cause at all. Otherwise a confirmed
    severe-injury match (via data.py's classify_injury_tier) wins over a
    team-change match, since it's the more specific, more actionable
    cause. A multi-team season with no injury match is a team change.
    Anything else is unexplained.
    """
    if full_season_games > 0 and gp / full_season_games >= FULL_SEASON_GP_RATIO:
        return "full_season"
    if classify_injury_tier(severe_reasons or []) is not None:
        return "injury_confirmed"
    if MULTI_TEAM_MARKER_RE.match(str(bbr_team)):
        return "team_change"
    return "unexplained"


def build_player_cause_profile(seasons: list[str],
                               gp_by_season: dict[str, dict[str, float]],
                               team_by_season: dict[str, dict[str, str]],
                               severe_reasons_by_season: dict[str, dict[str, list[str]]],
                               full_season_games: int = 82) -> dict[str, dict[str, str]]:
    """
    Build { player_name: { season: cause_label } } for every player with
    real GP data in at least one season.

    `gp_by_season`/`team_by_season` are keyed by raw BBR player name (the
    same name project_stats' own player loop uses) -- main.py builds these
    directly from season_raw_gp/season_raw_team. `severe_reasons_by_season`
    is keyed by canonical_player_key (the nbainjuries source uses a
    different name format) -- this function does the canonical-key bridge
    internally so callers never have to reconcile the two naming sources
    themselves.

    Limitation: a season a player is fully absent from (no BBR row at
    all -- not even a low-GP one) can never be labeled "injury_confirmed"
    here even when the absence itself was injury-caused, since this
    function only labels seasons it has real GP/team data for -- a
    fail-closed choice consistent with this module's conservatism
    elsewhere, but worth stating explicitly rather than leaving implicit.
    """
    profile: dict[str, dict[str, str]] = {}
    for season in seasons:
        gp_map = gp_by_season.get(season, {})
        team_map = team_by_season.get(season, {})
        severe_map = severe_reasons_by_season.get(season, {})
        for player, gp in gp_map.items():
            if pd.isna(gp):
                continue
            severe_reasons = severe_map.get(canonical_player_key(player), [])
            bbr_team = team_map.get(player, "")
            label = attribute_season_cause(gp, full_season_games, bbr_team, severe_reasons)
            profile.setdefault(player, {})[season] = label
    return profile


def summarize_cause_profile(player_causes: dict[str, str],
                            seasons: list[str]) -> str:
    """
    Return a compact human-readable summary of a player's cause profile:
    the most recent season (per `seasons`' own order) carrying a confirmed
    cause, or "" if every season is "full_season"/"unexplained"/absent.
    """
    for season in seasons:
        label = player_causes.get(season)
        if label not in (None, "full_season", "unexplained"):
            return f"{season}: {label}"
    return ""
