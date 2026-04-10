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
import re
import unicodedata
from pathlib import Path


# ── Basketball Reference CSV loading ────────────────────────────────────────

BBR_COL_MAP = {
    "Player": "PLAYER_NAME",
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

def normalize_player_name(name: str) -> str:
    """Normalize names so accents/punctuation differences do not break lookups."""
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def build_nba_player_lookups(all_players: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Create exact and normalized name lookup tables for NBA API players."""
    exact = {p["full_name"]: p["id"] for p in all_players}
    normalized: dict[str, int] = {}
    for player in all_players:
        normalized.setdefault(normalize_player_name(player["full_name"]), player["id"])
    return exact, normalized


def resolve_player_id(player_name: str,
                      exact_lookup: dict[str, int],
                      normalized_lookup: dict[str, int]) -> int | None:
    """Resolve a Basketball Reference-style player name to an NBA API player id."""
    player_id = exact_lookup.get(player_name)
    if player_id is not None:
        return player_id
    return normalized_lookup.get(normalize_player_name(player_name))


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
                                 missing_pairs: list[tuple[str, str]]) -> dict[str, object]:
    requested_pairs = _requested_game_log_pairs(player_names, seasons)
    return {
        "requested_pairs": requested_pairs,
        "requested_pair_count": len(requested_pairs),
        "missing_pairs": missing_pairs,
        "missing_pair_count": len(missing_pairs),
        "degraded": bool(missing_pairs),
    }

def fetch_game_logs(player_names: list[str],
                    seasons: list[str],
                    cache_file: str,
                    return_health: bool = False) -> dict[str, dict[str, pd.DataFrame]] | tuple[dict[str, dict[str, pd.DataFrame]], dict[str, object]]:
    """
    Fetch per-game logs for each player for each season from the NBA API.

    Returns: { season -> { player_name -> DataFrame } }

    Caches results to disk — delete the cache file to force a fresh fetch.
    Uses retry logic with exponential backoff to handle NBA API rate limiting.
    """
    cache_path = Path(cache_file)
    result, cache_status = _load_cached_game_logs(cache_path, seasons)
    missing_pairs = _missing_game_log_pairs(result, player_names, seasons)
    if cache_path.exists():
        if cache_status["valid"]:
            print(f"   Loading game logs from cache: {cache_file}")
            if not missing_pairs:
                health = _build_game_log_fetch_health(player_names, seasons, missing_pairs)
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
    exact_lookup, normalized_lookup = build_nba_player_lookups(all_players)

    total  = len(missing_pairs)
    done   = 0

    for player_name, season in missing_pairs:
        player_id = resolve_player_id(player_name, exact_lookup, normalized_lookup)
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

    final_missing_pairs = _missing_game_log_pairs(result, player_names, seasons)
    health = _build_game_log_fetch_health(player_names, seasons, final_missing_pairs)
    if return_health:
        return result, health
    return result


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
