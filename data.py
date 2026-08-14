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
import time
import pickle
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
    - Traded players: keeps the TOT (full-season aggregate) row only
    - Missing FG%: recomputes from FGM/FGA if needed
    """
    df = pd.read_csv(path, skipinitialspace=True)
    df = df.dropna(subset=["Player"])
    df = df[df["Player"] != "Player"]   # BBR repeats header row mid-file

    # For traded players, BBR has one row per team + a TOT aggregate row.
    # Keep only TOT — it's the accurate full-season picture.
    df["_is_tot"] = (df["Team"] == "TOT").astype(int)
    df = df.sort_values("_is_tot", ascending=False)
    df = df.drop_duplicates(subset="Player", keep="first")
    df = df.drop(columns=["_is_tot"])

    available = {k: v for k, v in BBR_COL_MAP.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    for col in df.columns:
        if col != "PLAYER_NAME":
            df[col] = pd.to_numeric(df[col], errors="coerce")

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


def _draft_history_cache_metadata(draft_years: list[str]) -> dict[str, list[str]]:
    return {"draft_years": list(draft_years)}


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


# ── Derive DD and TD from game logs ──────────────────────────────────────────

def derive_stats_from_logs(game_logs: dict[str, dict[str, pd.DataFrame]]) \
        -> dict[str, dict[str, float]]:
    """
    Compute DD and TD per game from raw game logs.

    The NBA API game log already provides DD2 (double-double) and TD3
    (triple-double) columns — no manual category counting needed.

    For players appearing in multiple seasons, uses the most recent season's
    value rather than averaging, since recency matters most for projection.

    Returns: { player_name -> { 'DD': float, 'TD': float } }
    """
    derived: dict[str, dict[str, float]] = {}

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

            if "TD" not in derived[player_name] and "TD3" in logs.columns:
                derived[player_name]["TD"] = logs["TD3"].sum() / gp

    return derived
