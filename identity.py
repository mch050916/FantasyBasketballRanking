"""
identity.py — Shared deterministic player identity helpers
===========================================================
Keeps cross-source player matching explicit and reproducible.
"""

import re
import unicodedata


# ── Deterministic player identity rules ─────────────────────────────────────

SOURCE_NAME_OVERRIDES = {
    "nba_api": {
        "Jimmy Butler": "Jimmy Butler III",
    },
}

CANONICAL_NAME_ALIASES = {
    "jimmybutleriii": "jimmybutler",
}


def normalize_player_name(name: str) -> str:
    """Normalize names so accents/punctuation differences do not break lookups."""
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def canonical_player_key(name: str) -> str:
    """Return the canonical key for a player after alias normalization."""
    key = normalize_player_name(name)
    return CANONICAL_NAME_ALIASES.get(key, key)


def resolve_source_player_name(player_name: str, source: str) -> str:
    """Map a local player name to the external source's known surface form."""
    return SOURCE_NAME_OVERRIDES.get(source, {}).get(player_name, player_name)


def build_nba_player_lookups(all_players: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Create exact and canonical lookup tables for NBA API players."""
    exact = {player["full_name"]: player["id"] for player in all_players}
    canonical: dict[str, int] = {}
    for player in all_players:
        canonical.setdefault(canonical_player_key(player["full_name"]), player["id"])
    return exact, canonical


def resolve_player_id(player_name: str,
                      exact_lookup: dict[str, int],
                      canonical_lookup: dict[str, int],
                      source: str = "nba_api") -> int | None:
    """Resolve a local player name to an external player id using deterministic fallbacks."""
    source_name = resolve_source_player_name(player_name, source)
    player_id = exact_lookup.get(source_name)
    if player_id is not None:
        return player_id
    return canonical_lookup.get(canonical_player_key(player_name))
