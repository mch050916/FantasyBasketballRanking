"""
data.py — Data loading and NBA API fetching
=============================================
Handles:
  - Loading Basketball Reference season CSV files
  - Fetching per-player game logs from the NBA API (with caching)
  - Fetching TECH stats (estimated from foul rate)
  - Deriving DD and TD per game from game logs

You should rarely need to edit this file. If the NBA API column names change
or Basketball Reference changes their CSV format, fixes go here.
"""

import pandas as pd
import numpy as np
import os
import re
import time
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from identity import (
    build_nba_player_lookups,
    canonical_player_key,
    normalize_player_name,
    resolve_player_id,
)


# ── Basketball Reference CSV loading ────────────────────────────────────────

BBR_COL_MAP = {
    "Player": "PLAYER_NAME",
    "Team":   "BBR_TEAM",
    "Pos":    "POSITION",
    "Age":    "AGE",
    "G":      "GP",
    "MP":     "MIN_TOTAL",
    "FG":     "FGM_T",
    "FGA":    "FGA_T",
    "FG%":    "FG%",
    "3P":     "3PTM_T",
    "FT":     "FTM_T",
    "TRB":    "REB_T",
    "AST":    "AST_T",
    "STL":    "ST_T",
    "BLK":    "BLK_T",
    "TOV":    "TO_T",
    "PF":     "PF_T",
    "PTS":    "PTS_T",
}

MULTI_TEAM_MARKER_RE = re.compile(r"^(TOT|\d?TM)$")   # BBR's own aggregate-row markers: TOT, 2TM, 3TM, ...

CACHE_SCHEMA_VERSION = 1
NON_ACTIONABLE_SUPPRESSION_REGISTRY_FILE = Path(".planning/non_actionable_suppressions.csv")
SUPPRESSION_REGISTRY_COLUMNS = [
    "Player Name",
    "Season",
    "Reason",
    "Review Status",
    "Review Notes",
]
SUPPRESSION_REVIEW_STATUS_ACTIVE = "active"
SUPPRESSION_REVIEW_STATUS_RETIRED = "retired"
VALID_SUPPRESSION_REVIEW_STATUSES = {
    SUPPRESSION_REVIEW_STATUS_ACTIVE,
    SUPPRESSION_REVIEW_STATUS_RETIRED,
}


def load_bbr_csv(path: str) -> pd.DataFrame:
    """
    Load a Basketball Reference season totals CSV and convert to per-game stats.

    Handles:
    - Repeated header rows mid-file (BBR quirk)
    - Traded players: keeps the multi-team aggregate row (2TM/3TM/...) only
    - Missing FG%: recomputes from FGM/FGA if needed

    BBR_TEAM carries the raw team abbreviation through (used by
    fetch_current_teams/detect_team_changes for offseason-move flagging).
    For a player traded mid-season, this is the aggregate row marker
    (2TM/3TM/etc. for the number of teams) rather than either real team -- a
    known, accepted imprecision for that specific case; the offseason moves
    this is built to catch (a player's team differs entirely from last season)
    are unaffected.
    """
    df = pd.read_csv(path, skipinitialspace=True)
    df = df.dropna(subset=["Player"])
    df = df[df["Player"] != "Player"]   # BBR repeats header row mid-file

    # For traded players, BBR has one row per team + a multi-team aggregate row.
    # Keep only the multi-team aggregate — it's the accurate full-season picture.
    df["_is_tot"] = df["Team"].astype(str).str.match(MULTI_TEAM_MARKER_RE).astype(int)
    df = df.sort_values("_is_tot", ascending=False)
    df = df.drop_duplicates(subset="Player", keep="first")
    df = df.drop(columns=["_is_tot"])

    available = {k: v for k, v in BBR_COL_MAP.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    for col in df.columns:
        if col not in ("PLAYER_NAME", "BBR_TEAM", "POSITION"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "POSITION" in df.columns:
        # BBR occasionally lists dual eligibility ("PG-SG") -- only the
        # primary (first) position is kept, same convention
        # scripts/build_draft_board.py's own pos_lookup already uses.
        df["POSITION"] = df["POSITION"].astype(str).str.split("-").str[0]

    df = df.dropna(subset=["GP"])
    df["GP"] = df["GP"].astype(int)

    # Convert totals to per-game
    gp = df["GP"].replace(0, np.nan)
    df["MIN"]  = df["MIN_TOTAL"] / gp
    df["FGM"]  = df["FGM_T"] / gp
    df["FGA"]  = df["FGA_T"] / gp
    df["3PTM"] = df["3PTM_T"] / gp
    df["FTM"]  = df["FTM_T"] / gp
    df["REB"]  = df["REB_T"] / gp
    df["AST"]  = df["AST_T"] / gp
    df["ST"]   = df["ST_T"] / gp
    df["BLK"]  = df["BLK_T"] / gp
    df["TO"]   = df["TO_T"] / gp
    df["PF"]   = df["PF_T"] / gp
    df["PTS"]  = df["PTS_T"] / gp

    if "FG%" not in df.columns or df["FG%"].isna().all():
        df["FG%"] = df["FGM"] / df["FGA"].replace(0, np.nan)
    df["FG%"] = pd.to_numeric(df["FG%"], errors="coerce")

    # DD, TD, TECH come from game logs — initialise to 0 as placeholders
    for cat in ["TECH", "DD", "TD"]:
        df[cat] = 0.0

    drop_cols = [c for c in df.columns if c.endswith("_T") or c == "MIN_TOTAL"]
    df = df.drop(columns=drop_cols, errors="ignore")

    return df


def filter_qualified(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Keep only players who meet minimum games and minutes thresholds."""
    mask = (df["GP"] >= config["min_games"]) & (df["MIN"] >= config["min_mpg"])
    return df[mask].reset_index(drop=True)


# ── NBA API: game log fetching ───────────────────────────────────────────────


def _empty_game_log_result(seasons: list[str]) -> dict[str, dict[str, pd.DataFrame]]:
    return {season: {} for season in seasons}


def _normalize_weight_list(season_weights: list[float]) -> list[float]:
    return [round(float(weight), 12) for weight in season_weights]


def _build_cache_envelope(cache_kind: str, payload, metadata: dict) -> dict:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "cache_kind": cache_kind,
        "metadata": metadata,
        "payload": payload,
    }


def _write_cache_envelope(cache_path: Path, cache_kind: str, payload, metadata: dict) -> None:
    with open(cache_path, "wb") as f:
        pickle.dump(_build_cache_envelope(cache_kind, payload, metadata), f)


def _invalid_cache_status(reason: str) -> dict[str, str | bool | None]:
    return {"valid": False, "reason": reason, "metadata": None}


def _valid_cache_status(metadata: dict) -> dict[str, str | bool | dict]:
    return {"valid": True, "reason": None, "metadata": metadata}


def _read_cache_envelope(cache_path: Path, expected_kind: str) -> tuple[object | None, dict[str, str | bool | dict | None]]:
    if not cache_path.exists():
        return None, _invalid_cache_status("cache file missing")

    try:
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
    except Exception as exc:
        return None, _invalid_cache_status(f"unreadable cache payload ({exc.__class__.__name__})")

    if not isinstance(cached, dict):
        return None, _invalid_cache_status("missing cache metadata envelope")
    if cached.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None, _invalid_cache_status("missing or unsupported cache schema version")
    if cached.get("cache_kind") != expected_kind:
        return None, _invalid_cache_status("wrong cache kind metadata")

    metadata = cached.get("metadata")
    if not isinstance(metadata, dict):
        return None, _invalid_cache_status("missing cache metadata")
    if "payload" not in cached:
        return None, _invalid_cache_status("missing cache payload")

    return cached["payload"], _valid_cache_status(metadata)


def _game_log_cache_metadata(seasons: list[str]) -> dict[str, list[str]]:
    return {"seasons": list(seasons)}


def _tech_cache_metadata(seasons: list[str], season_weights: list[float]) -> dict[str, list]:
    return {
        "seasons": list(seasons),
        "season_weights": _normalize_weight_list(season_weights),
    }


def _load_cached_game_logs(cache_path: Path,
                           seasons: list[str]) -> tuple[dict[str, dict[str, pd.DataFrame]], dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "game_logs")
    if not cache_status["valid"]:
        return _empty_game_log_result(seasons), cache_status

    expected_metadata = _game_log_cache_metadata(seasons)
    metadata = cache_status["metadata"]
    if metadata != expected_metadata:
        return _empty_game_log_result(seasons), _invalid_cache_status("game-log cache metadata mismatch")
    if not isinstance(payload, dict):
        return _empty_game_log_result(seasons), _invalid_cache_status("game-log cache payload is not a season map")

    result = _empty_game_log_result(seasons)
    for season in seasons:
        season_logs = payload.get(season, {})
        if not isinstance(season_logs, dict):
            return _empty_game_log_result(seasons), _invalid_cache_status(
                f"game-log cache payload for {season} is not a player map"
            )
        result[season].update(season_logs)
    return result, cache_status


def _load_cached_tech_per_game(cache_path: Path,
                               seasons: list[str],
                               season_weights: list[float]) -> tuple[dict[str, float] | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "tech_per_game")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _tech_cache_metadata(seasons, season_weights)
    metadata = cache_status["metadata"]
    if metadata != expected_metadata:
        return None, _invalid_cache_status("TECH cache metadata mismatch")
    if not isinstance(payload, dict):
        return None, _invalid_cache_status("TECH cache payload is not a player map")

    return payload, cache_status


def _draft_history_cache_metadata(draft_years: list[str]) -> dict[str, object]:
    # "fields" is a self-invalidating marker -- bumping it forces any
    # pre-existing cache (built before person_id/draft_year were added) to
    # rebuild automatically instead of silently returning rows missing
    # those keys.
    return {
        "draft_years": list(draft_years),
        "fields": ["overall_pick", "round_number", "person_id", "draft_year"],
    }


def _load_cached_draft_history(cache_path: Path,
                               draft_years: list[str]) -> tuple[dict[str, dict[str, int]] | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "draft_history")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _draft_history_cache_metadata(draft_years)
    metadata = cache_status["metadata"]
    if metadata != expected_metadata:
        return None, _invalid_cache_status("draft-history cache metadata mismatch")
    if not isinstance(payload, dict):
        return None, _invalid_cache_status("draft-history cache payload is not a player map")

    return payload, cache_status


def _current_teams_cache_metadata(season: str) -> dict[str, str]:
    return {"season": season}


def _load_cached_current_teams(cache_path: Path,
                               season: str) -> tuple[dict[str, str] | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "current_teams")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _current_teams_cache_metadata(season)
    metadata = cache_status["metadata"]
    if metadata != expected_metadata:
        return None, _invalid_cache_status("current-teams cache metadata mismatch")
    if not isinstance(payload, dict):
        return None, _invalid_cache_status("current-teams cache payload is not a player map")

    return payload, cache_status


def _season_schedule_cache_metadata(season: str) -> dict[str, str]:
    return {"season": season}


def _load_cached_season_schedule(cache_path: Path,
                                 season: str) -> tuple[pd.DataFrame | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "season_schedule")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _season_schedule_cache_metadata(season)
    metadata = cache_status["metadata"]
    if metadata != expected_metadata:
        return None, _invalid_cache_status("season-schedule cache metadata mismatch")
    if not isinstance(payload, pd.DataFrame):
        return None, _invalid_cache_status("season-schedule cache payload is not a DataFrame")

    return payload, cache_status


def _missing_game_log_pairs(game_logs: dict[str, dict[str, pd.DataFrame]],
                            player_names: list[str],
                            seasons: list[str]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for player_name in player_names:
        for season in seasons:
            if player_name not in game_logs.get(season, {}):
                missing.append((player_name, season))
    return missing


def _requested_game_log_pairs(player_names: list[str],
                              seasons: list[str]) -> list[tuple[str, str]]:
    return [(player_name, season) for player_name in player_names for season in seasons]


def _build_game_log_fetch_health(player_names: list[str],
                                 seasons: list[str],
                                 missing_pairs: list[tuple[str, str]],
                                 expected_missing_pairs: list[tuple[str, str]] | None = None,
                                 current_season_missing_pairs: list[tuple[str, str]] | None = None,
                                 historical_missing_pairs: list[tuple[str, str]] | None = None,
                                 non_actionable_pairs: list[tuple[str, str]] | None = None,
                                 non_actionable_reasons: dict[tuple[str, str], str] | None = None,
                                 suppression_registry_review: dict[str, Any] | None = None) -> dict[str, object]:
    requested_pairs = _requested_game_log_pairs(player_names, seasons)
    expected_missing_pairs = expected_missing_pairs or []
    current_season_missing_pairs = current_season_missing_pairs or []
    historical_missing_pairs = historical_missing_pairs or []
    non_actionable_pairs = non_actionable_pairs or []
    current_season = seasons[0] if seasons else None
    if not current_season_missing_pairs and current_season is not None:
        current_season_missing_pairs = [
            pair for pair in missing_pairs if pair[1] == current_season
        ]
    if not historical_missing_pairs and current_season is not None:
        historical_missing_pairs = [
            pair for pair in missing_pairs if pair[1] != current_season
        ]
    return {
        "requested_pairs": requested_pairs,
        "requested_pair_count": len(requested_pairs),
        "expected_missing_pairs": expected_missing_pairs,
        "expected_missing_pair_count": len(expected_missing_pairs),
        "missing_pairs": missing_pairs,
        "missing_pair_count": len(missing_pairs),
        "current_season_missing_pairs": current_season_missing_pairs,
        "current_season_missing_pair_count": len(current_season_missing_pairs),
        "historical_missing_pairs": historical_missing_pairs,
        "historical_missing_pair_count": len(historical_missing_pairs),
        "non_actionable_pairs": non_actionable_pairs,
        "non_actionable_pair_count": len(non_actionable_pairs),
        "non_actionable_reasons": non_actionable_reasons or {},
        "suppression_registry_review": suppression_registry_review or {},
        "degraded": bool(missing_pairs),
    }


def _partition_missing_pairs(missing_pairs: list[tuple[str, str]],
                             expected_missing_pairs: set[tuple[str, str]] | None) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    expected_missing_pairs = expected_missing_pairs or set()
    expected: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str]] = []
    for pair in missing_pairs:
        if pair in expected_missing_pairs:
            expected.append(pair)
        else:
            unresolved.append(pair)
    return unresolved, expected


def _coerce_optional_registry_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_non_actionable_suppression_registry(path: str | Path = NON_ACTIONABLE_SUPPRESSION_REGISTRY_FILE) -> pd.DataFrame:
    """Load the season-scoped non-actionable suppression registry from disk."""
    registry_path = Path(path)
    if not registry_path.exists():
        return pd.DataFrame(columns=SUPPRESSION_REGISTRY_COLUMNS)

    registry = pd.read_csv(registry_path)
    for col in SUPPRESSION_REGISTRY_COLUMNS:
        if col not in registry.columns:
            registry[col] = ""
    registry = registry[SUPPRESSION_REGISTRY_COLUMNS].copy()
    for col in SUPPRESSION_REGISTRY_COLUMNS:
        registry[col] = registry[col].map(_coerce_optional_registry_text)
    registry["Review Status"] = registry["Review Status"].str.lower()
    invalid_statuses = set(registry["Review Status"]) - VALID_SUPPRESSION_REVIEW_STATUSES
    if invalid_statuses:
        raise ValueError(
            f"invalid suppression review status(es): {sorted(invalid_statuses)}"
        )
    return registry


def summarize_non_actionable_suppression_registry(
        seasons: list[str],
        path: str | Path = NON_ACTIONABLE_SUPPRESSION_REGISTRY_FILE) -> dict[str, Any]:
    """Summarize active and expired suppression entries for the current run."""
    registry_path = Path(path)
    registry = load_non_actionable_suppression_registry(registry_path)
    current_season = seasons[0] if seasons else ""
    entries = registry.to_dict("records")

    active_entries: list[dict[str, str]] = []
    expired_entries: list[dict[str, str]] = []
    retired_entries: list[dict[str, str]] = []
    active_reason_map: dict[tuple[str, str], str] = {}

    for entry in entries:
        status = entry["Review Status"]
        season = entry["Season"]
        if status != SUPPRESSION_REVIEW_STATUS_ACTIVE:
            retired_entries.append(entry)
            continue
        if season == current_season:
            active_entries.append(entry)
            active_reason_map[(canonical_player_key(entry["Player Name"]), season)] = entry["Reason"]
        else:
            expired_entries.append(entry)

    return {
        "registry_path": str(registry_path),
        "current_season": current_season,
        "total_entries": len(entries),
        "active_entries": active_entries,
        "active_entry_count": len(active_entries),
        "expired_entries": expired_entries,
        "expired_entry_count": len(expired_entries),
        "retired_entries": retired_entries,
        "retired_entry_count": len(retired_entries),
        "active_reason_map": active_reason_map,
    }


def _non_actionable_game_log_reason(player_name: str,
                                    season: str,
                                    active_reason_map: dict[tuple[str, str], str] | None = None) -> str | None:
    """Return a narrow explicit reason when a missing pair is non-actionable."""
    if active_reason_map is None:
        return None
    return active_reason_map.get((canonical_player_key(player_name), season))


def _classify_missing_game_log_pairs(missing_pairs: list[tuple[str, str]],
                                     seasons: list[str],
                                     expected_missing_pairs: set[tuple[str, str]] | None = None,
                                     active_non_actionable_reasons: dict[tuple[str, str], str] | None = None) -> dict[str, object]:
    """Classify missing pairs by severity and explicit non-actionable reasons."""
    expected_missing_pairs = expected_missing_pairs or set()
    current_season = seasons[0] if seasons else None
    actionable: list[tuple[str, str]] = []
    current_season_missing_pairs: list[tuple[str, str]] = []
    historical_missing_pairs: list[tuple[str, str]] = []
    expected: list[tuple[str, str]] = []
    non_actionable: list[tuple[str, str]] = []
    non_actionable_reasons: dict[tuple[str, str], str] = {}

    for pair in missing_pairs:
        player_name, season = pair
        if pair in expected_missing_pairs:
            expected.append(pair)
            continue

        reason = _non_actionable_game_log_reason(
            player_name,
            season,
            active_non_actionable_reasons,
        )
        if reason is not None:
            non_actionable.append(pair)
            non_actionable_reasons[pair] = reason
            continue

        actionable.append(pair)
        if current_season is not None and season == current_season:
            current_season_missing_pairs.append(pair)
        else:
            historical_missing_pairs.append(pair)

    return {
        "actionable_missing_pairs": actionable,
        "current_season_missing_pairs": current_season_missing_pairs,
        "historical_missing_pairs": historical_missing_pairs,
        "expected_missing_pairs": expected,
        "non_actionable_pairs": non_actionable,
        "non_actionable_reasons": non_actionable_reasons,
    }

def fetch_game_logs(player_names: list[str],
                    seasons: list[str],
                    cache_file: str,
                    expected_missing_pairs: set[tuple[str, str]] | None = None,
                    return_health: bool = False,
                    suppression_registry_path: str | Path = NON_ACTIONABLE_SUPPRESSION_REGISTRY_FILE) -> dict[str, dict[str, pd.DataFrame]] | tuple[dict[str, dict[str, pd.DataFrame]], dict[str, object]]:
    """
    Fetch per-game logs for each player for each season from the NBA API.

    Returns: { season -> { player_name -> DataFrame } }

    Caches results to disk — delete the cache file to force a fresh fetch.
    Uses retry logic with exponential backoff to handle NBA API rate limiting.
    """
    cache_path = Path(cache_file)
    suppression_registry_review = summarize_non_actionable_suppression_registry(
        seasons,
        path=suppression_registry_path,
    )
    result, cache_status = _load_cached_game_logs(cache_path, seasons)
    raw_missing_pairs = _missing_game_log_pairs(result, player_names, seasons)
    classified_missing = _classify_missing_game_log_pairs(
        raw_missing_pairs,
        seasons,
        expected_missing_pairs,
        suppression_registry_review["active_reason_map"],
    )
    missing_pairs = classified_missing["actionable_missing_pairs"]
    expected_pairs = classified_missing["expected_missing_pairs"]
    non_actionable_pairs = classified_missing["non_actionable_pairs"]
    non_actionable_reasons = classified_missing["non_actionable_reasons"]
    if cache_path.exists():
        if cache_status["valid"]:
            print(f"   Loading game logs from cache: {cache_file}")
            if not missing_pairs:
                health = _build_game_log_fetch_health(
                    player_names,
                    seasons,
                    missing_pairs,
                    expected_pairs,
                    current_season_missing_pairs=classified_missing["current_season_missing_pairs"],
                    historical_missing_pairs=classified_missing["historical_missing_pairs"],
                    non_actionable_pairs=non_actionable_pairs,
                    non_actionable_reasons=non_actionable_reasons,
                    suppression_registry_review=suppression_registry_review,
                )
                if return_health:
                    return result, health
                return result
            print(f"   Cache missing {len(missing_pairs)} player-season logs — backfilling now...")
        else:
            print(f"   Rebuilding game-log cache: {cache_status['reason']}")
    else:
        print(f"   No cache found — fetching from NBA API (~6-8 min for 150 players)...")
        print(f"   This only runs once. Results saved to {cache_file}")

    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelogs

    all_players = nba_players.get_players()
    exact_lookup, canonical_lookup = build_nba_player_lookups(all_players)

    total  = len(missing_pairs)
    done   = 0

    for player_name, season in missing_pairs:
        player_id = resolve_player_id(player_name, exact_lookup, canonical_lookup)
        done += 1
        pct = done / total * 100 if total else 100

        if player_id is None:
            print(f"\n   [skip] {player_name} {season}: no NBA API player id match")
            continue

        for attempt in range(3):
            try:
                time.sleep(1.5 + attempt * 3)   # 1.5s → 4.5s → 7.5s
                logs = playergamelogs.PlayerGameLogs(
                    player_id_nullable=player_id,
                    season_nullable=season,
                )
                df = logs.get_data_frames()[0]
                if not df.empty:
                    result[season][player_name] = df
                print(f"   [{pct:4.0f}%] {player_name} {season}   ", end="\r")
                break

            except Exception:
                if attempt < 2:
                    wait = 5 + attempt * 5   # 5s → 10s between retries
                    print(f"\n   [retry {attempt+1}] {player_name} {season} — waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"\n   [skip] {player_name} {season}: failed after 3 attempts")

    print()

    _write_cache_envelope(
        cache_path,
        "game_logs",
        result,
        _game_log_cache_metadata(seasons),
    )
    print(f"   Game logs cached to {cache_file}")

    final_raw_missing_pairs = _missing_game_log_pairs(result, player_names, seasons)
    final_classified_missing = _classify_missing_game_log_pairs(
        final_raw_missing_pairs,
        seasons,
        expected_missing_pairs,
        suppression_registry_review["active_reason_map"],
    )
    health = _build_game_log_fetch_health(
        player_names,
        seasons,
        final_classified_missing["actionable_missing_pairs"],
        final_classified_missing["expected_missing_pairs"],
        current_season_missing_pairs=final_classified_missing["current_season_missing_pairs"],
        historical_missing_pairs=final_classified_missing["historical_missing_pairs"],
        non_actionable_pairs=final_classified_missing["non_actionable_pairs"],
        non_actionable_reasons=final_classified_missing["non_actionable_reasons"],
        suppression_registry_review=suppression_registry_review,
    )
    if return_health:
        return result, health
    return result


def build_non_actionable_suppression_report(game_log_health: dict[str, object]) -> str:
    """Render a markdown maintenance report for season-scoped suppressions."""
    review = game_log_health.get("suppression_registry_review") or {}
    current_season = review.get("current_season") or "unknown"
    registry_path = review.get("registry_path") or str(NON_ACTIONABLE_SUPPRESSION_REGISTRY_FILE)
    active_entries = list(review.get("active_entries") or [])
    expired_entries = list(review.get("expired_entries") or [])
    retired_entries = list(review.get("retired_entries") or [])
    used_pairs = set(game_log_health.get("non_actionable_pairs") or [])
    used_reasons = game_log_health.get("non_actionable_reasons") or {}

    lines = [
        "# Non-Actionable Suppression Maintenance",
        "",
        f"- Current season: `{current_season}`",
        f"- Registry: `{registry_path}`",
        f"- Active entries: `{len(active_entries)}`",
        f"- Expired entries: `{len(expired_entries)}`",
        f"- Retired entries: `{len(retired_entries)}`",
        f"- Used this run: `{len(used_pairs)}`",
        "",
    ]

    if active_entries:
        lines.extend(["## Active Entries", ""])
        for entry in active_entries:
            pair = (entry["Player Name"], entry["Season"])
            used_label = "used this run" if pair in used_pairs else "not used this run"
            reason = used_reasons.get(pair, entry["Reason"])
            lines.append(
                f"- {entry['Player Name']} ({entry['Season']}): {reason} [{used_label}]"
            )
        lines.append("")

    if expired_entries:
        lines.extend(["## Expired Entries Requiring Reaffirmation", ""])
        for entry in expired_entries:
            lines.append(
                f"- {entry['Player Name']} ({entry['Season']}): {entry['Reason']}"
            )
        lines.append("")

    if retired_entries:
        lines.extend(["## Retired Entries", ""])
        for entry in retired_entries:
            lines.append(
                f"- {entry['Player Name']} ({entry['Season']}): {entry['Reason']}"
            )
        lines.append("")

    if not active_entries and not expired_entries and not retired_entries:
        lines.extend(["## Registry Status", "", "- No suppression registry entries found.", ""])

    return "\n".join(lines).rstrip() + "\n"


# ── NBA API: TECH stats ──────────────────────────────────────────────────────

def fetch_tech_per_game(seasons: list[str],
                        cache_file: str,
                        season_weights: list[float]) -> dict[str, float]:
    """
    Estimate technical fouls per game for each player.

    The NBA API does not expose per-player technical fouls in any clean
    endpoint. We estimate from PF rate using the base stats endpoint:
        TECH ≈ 0.012 × PF_per_game

    This gives ~0.042 TECH/game for foul-prone players (PF ~3.5) and
    ~0.018 for disciplined players (PF ~1.5) — meaningfully differentiated
    without scraping. The TECH category weight of 0.3 limits error impact.

    Returns: { player_name -> estimated_tech_per_game }
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_tech_per_game(cache_path, seasons, season_weights)
        if cache_status["valid"]:
            print("   Loading TECH from cache...")
            return cached
        print(f"   Rebuilding TECH cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import leaguedashplayerstats

    combined: dict[str, list] = {}

    for i, season in enumerate(seasons):
        try:
            time.sleep(1.5)
            print(f"   Fetching foul stats for {season} (TECH estimation)...")
            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                measure_type_detailed_defense="Base",
            )
            df = stats.get_data_frames()[0]
            df = df[df["GP"] >= 10]

            w = season_weights[i] if i < len(season_weights) else season_weights[-1]
            for _, row in df.iterrows():
                name = row["PLAYER_NAME"]
                pf   = float(row.get("PF", 2.5))
                tech_estimate = max(0.01, 0.012 * pf)
                if name not in combined:
                    combined[name] = []
                combined[name].append((tech_estimate, w))

            print(f"   TECH estimated for {len(df)} players in {season}")

        except Exception as e:
            print(f"   [warn] TECH fetch failed for {season}: {e}")

    result = {}
    for name, vals in combined.items():
        total_w = sum(w for _, w in vals)
        result[name] = sum(v * w for v, w in vals) / total_w if total_w > 0 else 0.05

    _write_cache_envelope(
        cache_path,
        "tech_per_game",
        result,
        _tech_cache_metadata(seasons, season_weights),
    )
    print(f"   TECH data cached for {len(result)} players")

    return result


def fetch_draft_history(draft_years: list[str], cache_file: str) -> dict[str, dict[str, int]]:
    """
    Fetch draft-pick results for the given draft years from the NBA API.

    Returns: { player_name -> {"overall_pick": int, "round_number": int} }

    Caches results to disk -- delete the cache file to force a fresh fetch.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_draft_history(cache_path, draft_years)
        if cache_status["valid"]:
            print("   Loading draft history from cache...")
            return cached
        print(f"   Rebuilding draft-history cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import DraftHistory

    result: dict[str, dict[str, int]] = {}

    for year in draft_years:
        try:
            time.sleep(1.5)
            print(f"   Fetching draft results for {year}...")
            dh = DraftHistory(season_year_nullable=year)
            df = dh.get_data_frames()[0]
            for _, row in df.iterrows():
                name = row["PLAYER_NAME"]
                result[name] = {
                    "overall_pick": int(row["OVERALL_PICK"]),
                    "round_number": int(row["ROUND_NUMBER"]),
                    "person_id": int(row["PERSON_ID"]),
                    "draft_year": year,
                }
            print(f"   Draft history fetched for {len(df)} picks in {year}")
        except Exception as e:
            print(f"   [warn] Draft history fetch failed for {year}: {e}")

    _write_cache_envelope(
        cache_path,
        "draft_history",
        result,
        _draft_history_cache_metadata(draft_years),
    )
    print(f"   Draft history cached for {len(result)} players")

    return result


ROOKIE_SEASON_CATEGORY_MAP = {
    "GP": "GP", "MIN": "MIN", "PTS": "PTS", "REB": "REB", "AST": "AST",
    "STL": "ST", "BLK": "BLK", "TOV": "TO", "PF": "PF", "FGM": "FGM",
    "FGA": "FGA", "FG_PCT": "FG%", "FG3M": "3PTM", "FTM": "FTM",
}


def _rookie_season_stats_cache_metadata(draft_years: list[str]) -> dict[str, list[str]]:
    return {"draft_years": sorted(set(draft_years))}


def _load_cached_rookie_season_stats(cache_path: Path,
                                     draft_years: list[str]) -> tuple[dict[str, dict[str, float]] | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "rookie_season_stats")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _rookie_season_stats_cache_metadata(draft_years)
    if cache_status["metadata"] != expected_metadata:
        return None, _invalid_cache_status("rookie-season-stats cache metadata mismatch")
    if not isinstance(payload, dict):
        return None, _invalid_cache_status("rookie-season-stats cache payload is not a player map")

    return payload, cache_status


def fetch_rookie_season_stats(draft_history: dict[str, dict], cache_file: str) -> dict[str, dict[str, float]]:
    """
    Fetch each drafted player's actual rookie-season per-game production
    (one nba_api.stats.endpoints.PlayerCareerStats call per player,
    per_mode36="PerGame") -- for building the historical training table in
    scripts/build_rookie_baseline.py. `draft_history` entries must carry
    "person_id" and "draft_year" (see fetch_draft_history).

    Skips any player with no SEASON_ID row starting with their own
    draft_year (hasn't played their rookie season yet -- not lookahead
    bias) or whose matching row has GP == 0.

    Returns: { canonical_player_key(name) -> {category -> float} } using
    this pipeline's own category names (ROOKIE_SEASON_CATEGORY_MAP).

    Caches results to disk -- delete the cache file to force a fresh fetch.
    """
    draft_years = [info["draft_year"] for info in draft_history.values()]
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_rookie_season_stats(cache_path, draft_years)
        if cache_status["valid"]:
            print("   Loading rookie-season stats from cache...")
            return cached
        print(f"   Rebuilding rookie-season-stats cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import PlayerCareerStats

    result: dict[str, dict[str, float]] = {}

    for name, info in draft_history.items():
        try:
            time.sleep(0.6)
            pcs = PlayerCareerStats(player_id=info["person_id"], per_mode36="PerGame")
            df = pcs.get_data_frames()[0]
            season_rows = df[df["SEASON_ID"].astype(str).str.startswith(info["draft_year"])]
            if season_rows.empty:
                continue
            # Handle mid-season trades: prefer TOT (season total) row if multiple rows exist
            if len(season_rows) > 1:
                tot_rows = season_rows[season_rows["TEAM_ABBREVIATION"] == "TOT"]
                row = tot_rows.iloc[0] if not tot_rows.empty else season_rows.iloc[0]
            else:
                row = season_rows.iloc[0]
            if pd.isna(row["GP"]) or float(row["GP"]) == 0:
                continue
            result[canonical_player_key(name)] = {
                internal: float(row[nba_col])
                for nba_col, internal in ROOKIE_SEASON_CATEGORY_MAP.items()
            }
        except Exception as e:
            print(f"   [warn] Rookie-season fetch failed for {name}: {e}")

    _write_cache_envelope(
        cache_path, "rookie_season_stats", result,
        _rookie_season_stats_cache_metadata(draft_years),
    )
    print(f"   Rookie-season stats cached for {len(result)} players")

    return result


COMBINE_RAW_COLUMNS = [
    "WINGSPAN", "WEIGHT", "MAX_VERTICAL_LEAP", "LANE_AGILITY_TIME",
    "THREE_QUARTER_SPRINT",
]


def _combine_stats_cache_metadata() -> dict[str, str]:
    return {"season_all_time": "All Time"}


def _load_cached_combine_stats(cache_path: Path) -> tuple[dict[str, dict[str, float]] | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "combine_stats")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _combine_stats_cache_metadata()
    if cache_status["metadata"] != expected_metadata:
        return None, _invalid_cache_status("combine-stats cache metadata mismatch")
    if not isinstance(payload, dict):
        return None, _invalid_cache_status("combine-stats cache payload is not a player map")

    return payload, cache_status


def fetch_combine_stats(cache_file: str) -> dict[str, dict[str, float]]:
    """
    Fetch every historical NBA Draft Combine measurement on record
    (nba_api.stats.endpoints.DraftCombineStats, SeasonYear="All Time"),
    keyed by canonical_player_key -- not scoped to any particular draft
    year, so one cached fetch serves both the historical training classes
    (scripts/build_rookie_baseline.py) and whichever class is currently
    being drafted (main.py), without needing to guess which SeasonYear
    value a given draft year's combine falls under.

    Returns: { canonical_player_key(name) -> {raw column -> float, NaN if
    missing/non-numeric} }, for the columns in COMBINE_RAW_COLUMNS.

    Caches results to disk -- delete the cache file to force a fresh fetch.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_combine_stats(cache_path)
        if cache_status["valid"]:
            print("   Loading combine stats from cache...")
            return cached
        print(f"   Rebuilding combine-stats cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import DraftCombineStats

    result: dict[str, dict[str, float]] = {}

    try:
        print("   Fetching NBA Draft Combine measurements (all draft classes)...")
        dcs = DraftCombineStats(league_id="00", season_all_time="All Time")
        df = dcs.get_data_frames()[0]
        for _, row in df.iterrows():
            key = canonical_player_key(row["PLAYER_NAME"])
            result[key] = {}
            for col in COMBINE_RAW_COLUMNS:
                if col in df.columns and pd.notna(row[col]):
                    try:
                        result[key][col] = float(row[col])
                    except (ValueError, TypeError):
                        result[key][col] = float("nan")
                else:
                    result[key][col] = float("nan")
        print(f"   Combine measurements fetched for {len(df)} players")
    except Exception as e:
        print(f"   [warn] Combine-stats fetch failed: {e}")

    if result:
        _write_cache_envelope(cache_path, "combine_stats", result, _combine_stats_cache_metadata())
        print(f"   Combine stats cached for {len(result)} players")
    else:
        print("   [warn] Combine-stats fetch returned no data -- not caching empty result, will retry next run")

    return result


def fetch_current_teams(season: str, cache_file: str) -> dict[str, str]:
    """
    Fetch every current-roster player's team abbreviation for `season`.

    Returns: { player_name -> team_abbreviation }

    One bulk API call (nba_api's CommonAllPlayers), not one per player --
    the `season` parameter must be passed explicitly, since the endpoint's
    own default silently returns an earlier season's rosters rather than
    erroring. Caches results to disk -- delete the cache file to force a
    fresh fetch.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_current_teams(cache_path, season)
        if cache_status["valid"]:
            print("   Loading current teams from cache...")
            return cached
        print(f"   Rebuilding current-teams cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import CommonAllPlayers

    result: dict[str, str] = {}

    try:
        print(f"   Fetching current team assignments for {season}...")
        cap = CommonAllPlayers(is_only_current_season=1, season=season)
        df = cap.get_data_frames()[0]
        for _, row in df.iterrows():
            result[row["DISPLAY_FIRST_LAST"]] = row["TEAM_ABBREVIATION"]
        print(f"   Current teams fetched for {len(df)} players")
    except Exception as e:
        print(f"   [warn] Current-teams fetch failed for {season}: {e}")

    _write_cache_envelope(
        cache_path,
        "current_teams",
        result,
        _current_teams_cache_metadata(season),
    )
    print(f"   Current teams cached for {len(result)} players")

    return result


def fetch_season_schedule(season: str, cache_file: str) -> pd.DataFrame:
    """
    Fetch every real game date for every team in `season`.

    Returns a DataFrame with one row per (team, game) -- GAME_DATE, TEAM
    (nba_api tricode) -- both home and away sides of each game unpacked
    into their own row, so counting rows per team per week gives that
    team's real games-per-week.

    One bulk API call (nba_api's ScheduleLeagueV2, the full season in one
    request, confirmed live -- not one call per team/game). Caches results
    to disk -- delete the cache file to force a fresh fetch.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_season_schedule(cache_path, season)
        if cache_status["valid"]:
            print("   Loading season schedule from cache...")
            return cached

        print(f"   Rebuilding season-schedule cache: {cache_status['reason']}")

    from nba_api.stats.endpoints import scheduleleaguev2

    result = pd.DataFrame(columns=["GAME_DATE", "TEAM"])

    try:
        print(f"   Fetching full season schedule for {season}...")
        games = scheduleleaguev2.ScheduleLeagueV2(season=season).get_data_frames()[0]
        result = pd.concat([
            games[["gameDate", "homeTeam_teamTricode"]].rename(
                columns={"gameDate": "GAME_DATE", "homeTeam_teamTricode": "TEAM"}),
            games[["gameDate", "awayTeam_teamTricode"]].rename(
                columns={"gameDate": "GAME_DATE", "awayTeam_teamTricode": "TEAM"}),
        ], ignore_index=True)
        print(f"   Season schedule fetched: {len(games)} games, {len(result)} team-game rows")
    except Exception as e:
        print(f"   [warn] Season-schedule fetch failed for {season}: {e}")

    _write_cache_envelope(
        cache_path,
        "season_schedule",
        result,
        _season_schedule_cache_metadata(season),
    )

    return result


def games_per_team_for_week(schedule: pd.DataFrame, week_of: str | pd.Timestamp) -> pd.Series:
    """
    Count each team's real games within the ISO calendar week containing
    `week_of` (any date in that Monday-Sunday week).

    Same "a week" definition model.py's add_week_key uses for compute_tau
    (ISO calendar week) -- not nba_api's own `weekNumber`, which doesn't
    reliably align to a Monday-Sunday boundary.
    """
    dates = pd.to_datetime(schedule["GAME_DATE"])
    iso = dates.dt.isocalendar()
    week_key = iso["year"].astype(str) + "_" + iso["week"].astype(str)

    target = pd.to_datetime(week_of).isocalendar()
    target_key = f"{target.year}_{target.week}"

    return schedule.loc[week_key == target_key, "TEAM"].value_counts()


MULTI_TEAM_LABEL = "Multiple Teams"

# BBR's abbreviation differs from nba_api's for exactly these 3 teams --
# verified directly against nba_api.stats.static.teams.get_teams() (all 30
# codes diffed against every distinct BBR "Team" value in a real BBR totals
# CSV; every other team's code already matches). Without this, a player who
# never left one of these three teams reads as a false "team change" purely
# from the two sources spelling the same team differently (caught live:
# Devin Booker "PHO -> PHX", Kon Knueppel "CHO -> CHA", both false positives
# for players who stayed put).
BBR_TEAM_ABBREVIATION_ALIASES = {
    "BRK": "BKN",   # Brooklyn Nets
    "CHO": "CHA",   # Charlotte Hornets
    "PHO": "PHX",   # Phoenix Suns
}


def _normalize_bbr_team(team: str) -> str:
    """
    Map a raw BBR team value onto a comparable form: multi-team-aggregate
    markers (TOT, 2TM, 3TM, ...) become one readable label, and BBR's three
    abbreviation spellings that differ from nba_api's become nba_api's
    spelling. Safe to apply to an nba_api-sourced value too -- none of its
    codes match either substitution, so it passes through unchanged.
    """
    if MULTI_TEAM_MARKER_RE.match(team):
        return MULTI_TEAM_LABEL
    return BBR_TEAM_ABBREVIATION_ALIASES.get(team, team)


def detect_team_changes(previous_team_by_player: dict[str, str],
                        current_team_by_player: dict[str, str]) -> dict[str, str]:
    """
    Compare each player's most-recent-loaded-season team against their
    current team, keyed by canonical identity (accent/punctuation-
    insensitive, same matching every other cross-source join in this
    pipeline uses).

    Returns: { player_name (as it appears in current_team_by_player) ->
               "PREV -> NEW" } for every player whose team differs.
    Players missing from either side, or whose two team strings are
    identical, are omitted -- this function only reports a real,
    informative difference. A player whose loaded season was a multi-team
    stint (BBR aggregates these under "TOT", "2TM", "3TM", ... -- the
    combined-season row load_bbr_csv keeps, not a single real team) reads
    as "Multiple Teams" rather than the raw code, since neither of those
    markers names a real team on their own.
    """
    previous_by_key = {
        canonical_player_key(name): _normalize_bbr_team(team)
        for name, team in previous_team_by_player.items()
    }

    changes: dict[str, str] = {}
    for name, current_team in current_team_by_player.items():
        current_team = _normalize_bbr_team(current_team)
        previous_team = previous_by_key.get(canonical_player_key(name))
        if previous_team is None or previous_team == current_team:
            continue
        changes[name] = f"{previous_team} -> {current_team}"

    return changes


# ── Derive DD and TD from game logs ──────────────────────────────────────────

def derive_stats_from_logs(game_logs: dict[str, dict[str, pd.DataFrame]]) \
        -> dict[str, dict[str, float]]:
    """
    Compute DD and TD per game from raw game logs.

    The NBA API game log already provides DD2 (double-double) and TD3
    (triple-double) columns — no manual category counting needed.

    For players appearing in multiple seasons, uses the most recent season's
    value rather than averaging, since recency matters most for projection.
    If a player has no game log for the most recent season (e.g. an NBA API
    fetch gap), silently falls through to their next available season and
    prints a line naming the player, the field (DD/TD), and which season got
    substituted — this doesn't change the fallback behavior, just surfaces it.

    Returns: { player_name -> { 'DD': float, 'TD': float } }
    """
    derived: dict[str, dict[str, float]] = {}
    most_recent_season = next(iter(game_logs), None)

    # Iterate seasons in order (most recent first, as game_logs is ordered)
    for season, season_logs in game_logs.items():
        for player_name, logs in season_logs.items():
            if logs.empty:
                continue

            gp = len(logs)
            if gp == 0:
                continue

            # Only set if not already set by a more recent season
            if player_name not in derived:
                derived[player_name] = {}

            if "DD" not in derived[player_name] and "DD2" in logs.columns:
                derived[player_name]["DD"] = logs["DD2"].sum() / gp
                if season != most_recent_season:
                    print(f"   DD fallback: {player_name} has no {most_recent_season} "
                          f"game log — DD sourced from {season} instead")

            if "TD" not in derived[player_name] and "TD3" in logs.columns:
                derived[player_name]["TD"] = logs["TD3"].sum() / gp
                if season != most_recent_season:
                    print(f"   TD fallback: {player_name} has no {most_recent_season} "
                          f"game log — TD sourced from {season} instead")

    return derived


# ── Injury reports (real injury-type data, not just games-missed counts) ────
# Addresses the healthy-worker survivorship bias flagged in GitHub issue #11's
# surrounding research: GP_FACTOR's multi-season blend can only ever see that
# a player missed games, never why -- a season-ending ACL tear and three
# unrelated minor ailments look identical to it. The NBA's own official
# injury reports carry real injury-type text (body part + mechanism, e.g.
# "Right Knee; ACL Tear") via the nbainjuries package, which PDF-parses them
# from the league's own servers (requires a local Java runtime -- see
# requirements.txt). Only covers 2021-22 onward, which already covers every
# season this pipeline loads (game_log_seasons).

# Approximate regular-season window per season this pipeline actually uses
# (game_log_seasons in config.py) -- precision doesn't matter here, these
# only seed a weekly sampling grid, not an exact game calendar.
INJURY_REPORT_SEASON_WINDOWS = {
    "2025-26": ("2025-10-20", "2026-04-13"),
    "2024-25": ("2024-10-21", "2025-04-14"),
    "2023-24": ("2023-10-23", "2024-04-15"),
}

INJURY_SEVERE_KEYWORDS = [
    "surgery", "fracture", "tear", "rupture", "acl", "achilles", "mcl",
    "meniscus", "labrum", "dislocat",
]
INJURY_NON_INJURY_REASONS = {"g league - two-way", "rest", "load management",
                             "personal", "suspension", "not with team"}


def _injury_reports_cache_metadata(seasons: list[str]) -> dict[str, object]:
    return {"seasons": sorted(seasons)}


def _load_cached_injury_reports(cache_path: Path,
                                seasons: list[str]) -> tuple[pd.DataFrame | None, dict[str, str | bool | dict | None]]:
    payload, cache_status = _read_cache_envelope(cache_path, "injury_reports")
    if not cache_status["valid"]:
        return None, cache_status

    expected_metadata = _injury_reports_cache_metadata(seasons)
    if cache_status["metadata"] != expected_metadata:
        return None, _invalid_cache_status("injury-reports cache metadata mismatch")
    if not isinstance(payload, pd.DataFrame):
        return None, _invalid_cache_status("injury-reports cache payload is not a DataFrame")

    return payload, cache_status


def fetch_injury_reports(seasons: list[str], cache_file: str) -> pd.DataFrame:
    """
    Fetch real NBA injury-report snapshots for the given seasons.

    No bulk/season endpoint exists in nbainjuries -- one call per snapshot
    datetime, each downloading and PDF-parsing one report (~1s). Sampled
    weekly (Mondays, 5:30pm ET, a standard report release time) across each
    season's rough game window instead of every report of every game day:
    dense enough that a real multi-week injury absence shows up in at least
    one snapshot, without needing hundreds of queries per season. A
    snapshot date with no report published (all-star break, a date just
    outside the real season) fails individually and is skipped, not fatal
    to the rest of the fetch.

    Returns one row per (snapshot, player, team): Game Date, Game Time,
    Matchup, Team, Player Name, Current Status, Reason, Season, Snapshot.
    Empty DataFrame (same columns) if every snapshot fails. Caller
    aggregates this into whatever per-player-season summary it needs (see
    classify_injury_reason / summarize_season_injuries).
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        cached, cache_status = _load_cached_injury_reports(cache_path, seasons)
        if cache_status["valid"]:
            print("   Loading injury reports from cache...")
            return cached
        print(f"   Rebuilding injury-reports cache: {cache_status['reason']}")

    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    from nbainjuries import injury

    columns = ["Game Date", "Game Time", "Matchup", "Team", "Player Name",
               "Current Status", "Reason", "Season", "Snapshot"]

    snapshots: list[tuple[str, datetime]] = []
    for season in seasons:
        window = INJURY_REPORT_SEASON_WINDOWS.get(season)
        if window is None:
            print(f"   [warn] No injury-report date window configured for {season}, skipping")
            continue
        d = datetime.fromisoformat(window[0])
        end_d = datetime.fromisoformat(window[1])
        while d <= end_d:
            snapshots.append((season, d.replace(hour=17, minute=30)))
            d += timedelta(days=7)

    print(f"   Fetching {len(snapshots)} weekly injury-report snapshots "
          f"across {len(seasons)} season(s)...")
    frames = []
    ok = failed = 0
    for i, (season, ts) in enumerate(snapshots):
        try:
            df = injury.get_reportdata(ts, return_df=True)
            if len(df):
                df = df.copy()
                df["Season"] = season
                df["Snapshot"] = ts
                frames.append(df)
            ok += 1
        except Exception:
            failed += 1
        if (i + 1) % 20 == 0 or i + 1 == len(snapshots):
            print(f"      [{i + 1}/{len(snapshots)}] {ok} ok, {failed} no report")

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)

    _write_cache_envelope(cache_path, "injury_reports", result, _injury_reports_cache_metadata(seasons))
    print(f"   Injury reports cached: {len(result)} rows from {ok}/{len(snapshots)} snapshots")
    return result


def classify_injury_reason(reason: str) -> tuple[str, bool]:
    """
    Classify one injury-report "Reason" string into (category, is_severe).

    Format is semi-structured: "Injury/Illness - {body part}; {mechanism}"
    for real injuries, or a short non-injury reason ("G League - Two-Way",
    "Rest", "Personal", ...) for roster/scheduling entries that aren't
    durability signal at all. `is_severe` is a conservative keyword match
    (surgery, fracture, tear, ACL, Achilles, ...) against the mechanism --
    real long-recovery injuries, not every day-to-day soreness/illness
    entry. Unclassifiable or missing text returns ("unknown", False) rather
    than guessing.
    """
    if not isinstance(reason, str) or not reason.strip():
        return "unknown", False

    lower = reason.strip().lower()
    if any(lower.startswith(r) for r in INJURY_NON_INJURY_REASONS):
        return "non_injury", False
    if not lower.startswith("injury/illness"):
        return "other", False

    is_severe = any(keyword in lower for keyword in INJURY_SEVERE_KEYWORDS)
    return "injury", is_severe


# ── Injury-type-specific "year 1 back" discount ──────────────────────────────
# A confirmed severe injury found in the newest loaded season is treated as
# "this player is entering their first season back" for the season being
# projected -- the common real pattern (injury costs most/all of the season
# it happens in, player returns the following season). No multi-year injury
# timeline is tracked; this is a one-season-deep signal, same depth as
# RECENT_SEVERE_INJURY itself.
#
# Multipliers below come from NBA-specific peer-reviewed return-to-play
# outcome studies, not a guess:
#   - ACL reconstruction: PER -19.3% in year 1, back to no significant
#     difference from pre-injury by year 2 (DeFroda et al., Orthop J Sports
#     Med 2021, https://doi.org/10.1177/2325967120981649)
#   - Achilles rupture/repair: PER -4.57 in year 1 *and* -4.38 in year 2,
#     not a significant improvement between the two -- doesn't recover the
#     way ACL does (Maman et al. 2026, https://doi.org/10.1177/23259671261461403;
#     Amin et al., Am J Sports Med 2013, https://doi.org/10.1177/0363546513490659).
#     -4.57 PER on a ~22-25 PER-range player (the typical player this flag
#     actually hits) works out close to the same ~19-20% as ACL's own
#     percentage, which is why the two multipliers below are close despite
#     being independently sourced.
#   - Meniscus surgery: MPG/PER decline at year 1, recover by year 2 (JSSM
#     2024, https://www.jssm.org/researchjssm-24-363.xml.xml) -- no exact
#     PER delta was available from what was checked, so this discount is
#     set more conservatively (smaller) than the other two, not derived
#     from the same precision of number.
#
# No other injury type gets a multiplier. Fractures, MCL/labrum tears,
# dislocations, and anything else classify_injury_reason marks severe but
# that doesn't match one of these three keywords stay flagged
# (RECENT_SEVERE_INJURY) but undiscounted -- no NBA-specific outcome study
# was found for them in the research behind this feature, and guessing a
# number would be exactly the kind of fake precision this pipeline's
# DATA_AVAILABILITY_NOTE convention avoids everywhere else.
INJURY_TIER_KEYWORDS = {
    "achilles": ["achilles"],
    "acl": ["acl"],
    "meniscus": ["meniscus"],
}
INJURY_TIER_YEAR1_DISCOUNT = {
    "achilles": 0.80,
    "acl": 0.81,
    "meniscus": 0.90,
}


def classify_injury_tier(severe_reasons: list[str]) -> str | None:
    """
    Bucket a player's severe-injury reasons (summarize_season_injuries'
    `severe_reasons`) into one of INJURY_TIER_YEAR1_DISCOUNT's three
    study-backed tiers, or None if none match. First matching tier wins if
    a player has reasons spanning more than one -- not just a tie-break of
    convenience: INJURY_TIER_KEYWORDS is deliberately ordered
    achilles/acl/meniscus, worst-to-mildest by the research behind the
    discounts, so a player with both an ACL and an Achilles entry (Tyrese
    Haliburton does, in the current pool) lands on the more cautious
    classification rather than whichever happened to sort first.
    """
    combined = " ".join(severe_reasons).lower()
    for tier, keywords in INJURY_TIER_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            return tier
    return None


def _injury_location(reason: str) -> str:
    """Body-part token from a reason string, e.g. "Injury/Illness - Left
    Knee; Surgery" -> "left knee"."""
    body = reason.split(" - ", 1)[-1]
    return body.split(";", 1)[0].strip().lower()


def classify_injury_tier_with_carryover(current_reasons: list[str],
                                         prior_reasons: list[str]) -> str | None:
    """
    Same as classify_injury_tier, but falls back to the immediately-prior
    season's severe reasons when the current season's own text doesn't name
    a tier. Real NBA injury reports sometimes genericize an ongoing injury
    ("Surgery") in later updates after the original diagnosis report named
    the specific structure (e.g. Kyrie Irving: 2024-25 reports say "Left
    Knee; Sprain/ACL tear", 2025-26 reports for the same continuing absence
    just say "Left Knee; Surgery" -- the ACL tear never resolved, the report
    wording just changed). Only trusts the carry-over when a prior-season
    reason shares the current season's body-part location -- a different
    location is a separate, unrelated injury, not a genericized version of
    this one (verified against Trae Young, whose current-season knee injury
    is unrelated to a resolved prior-season Achilles tendinitis -- different
    location, correctly excluded).
    """
    tier = classify_injury_tier(current_reasons)
    if tier is not None or not prior_reasons:
        return tier
    current_locations = {_injury_location(r) for r in current_reasons}
    matching_prior = [r for r in prior_reasons if _injury_location(r) in current_locations]
    return classify_injury_tier(matching_prior) if matching_prior else None


def reformat_lastfirst_name(name: str) -> str:
    """
    nbainjuries reports names as "Last, First" (suffixes stay with the last
    name, e.g. "Porter Jr., Kevin") -- this pipeline's PLAYER_NAME is
    "First Last" everywhere else. Splits on the first ", " only, so a
    hyphenated or multi-word last name ("Gilgeous-Alexander, Shai") still
    reformats correctly. Caller should still match on canonical_player_key
    (identity.py), not this string directly -- reformatting fixes word
    order, not accent/punctuation differences between the two sources.
    """
    if ", " not in name:
        return name
    last, first = name.split(", ", 1)
    return f"{first} {last}"


def _dedupe_similar_reasons(reasons: list[str]) -> list[str]:
    """
    Collapse near-duplicate reason strings describing the same body part and
    mechanism but worded differently across snapshots (weekly sampling
    often catches one real injury episode at several report dates, e.g.
    "Right Achilles Repair; Management" and "Right Achilles; Repair" are
    the same episode, not two, with the second just a shorter tag of the
    same thing). Normalizes each reason to a bag-of-words set (lowercase,
    punctuation stripped, word order ignored), then drops any reason whose
    word set is a *subset* of another's -- not just exact-set duplicates --
    keeping the longer, more specific original string. Ties (equal-length
    or incomparable sets) keep first-seen.
    """
    keyed: list[tuple[frozenset[str], str]] = []
    seen_keys: list[frozenset[str]] = []
    for r in reasons:
        key = frozenset(re.findall(r"[a-z0-9]+", r.lower()))
        if key not in seen_keys:
            seen_keys.append(key)
            keyed.append((key, r))

    return [
        r for key, r in keyed
        if not any(key < other_key for other_key, _ in keyed if other_key != key)
    ]


def summarize_season_injuries(injury_reports: pd.DataFrame) -> dict[str, dict[str, dict[str, object]]]:
    """
    Reduce raw injury-report rows to one severity summary per player per
    season: { season -> { player_name -> {"had_severe_injury": bool,
    "reasons": [distinct reason strings seen, near-duplicates collapsed]} } }.

    Player names here are nbainjuries' own "Last, First" format -- callers
    matching against this pipeline's "First Last" BBR names need
    canonical_player_key (identity.py) or an explicit reformat; left to the
    caller rather than guessed here, since the two sources' suffix/accent
    handling isn't necessarily identical.
    """
    summary: dict[str, dict[str, dict[str, object]]] = {}
    if injury_reports.empty:
        return summary

    for season, season_df in injury_reports.groupby("Season"):
        season_summary: dict[str, dict[str, object]] = {}
        for player, player_df in season_df.groupby("Player Name"):
            reasons = _dedupe_similar_reasons(sorted(set(player_df["Reason"].dropna())))
            severe_reasons = [r for r in reasons if classify_injury_reason(r)[1]]
            season_summary[player] = {
                "had_severe_injury": bool(severe_reasons),
                "reasons": reasons,
                "severe_reasons": severe_reasons,
            }
        summary[str(season)] = season_summary

    return summary
