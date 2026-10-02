"""
live_draft_sync.py -- Poll Yahoo's live draft room and auto-mark picks
=======================================================================
Reads credentials from .yahoo_oauth.env (produced by
scripts/setup_yahoo_oauth.sh), polls the league's draft results while a
Yahoo draft is live, matches each pick's player name against the board's
own player list, and writes drafted_live.json -- a small file the running
draft_board_2026_27.html polls and uses to auto-mark rows drafted.

Requires the board to be served over http (not opened as a file:// URL),
since browsers block fetch() of local files from file:// pages:

    python3 -m http.server 8000
    # then open http://localhost:8000/draft_board_2026_27.html

Run this alongside it, from the project root:

    python3 scripts/live_draft_sync.py

Ctrl-C stops it; drafted_live.json is left in place with whatever was
synced so far.
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".yahoo_oauth.env"
OUTPUT_PATH = REPO_ROOT / "drafted_live.json"

API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

POLL_SECONDS = 8
PLAYER_BATCH_SIZE = 25


def load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(
            f"{ENV_PATH} not found -- run scripts/setup_yahoo_oauth.sh first "
            "to authorize this script against your Yahoo account."
        )
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    required = ["CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI", "LEAGUE_URL",
                "YAHOO_ACCESS_TOKEN", "YAHOO_REFRESH_TOKEN"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        sys.exit(f"{ENV_PATH} is missing {missing} -- re-run scripts/setup_yahoo_oauth.sh.")
    return env


def save_env(env: dict) -> None:
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def league_id_from_url(url: str) -> str:
    # https://basketball.fantasysports.yahoo.com/nba/6176 -> "6176"
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1]


class YahooSession:
    """Thin wrapper: authenticated GETs against the Fantasy Sports API,
    refreshing the access token once on a 401 rather than failing the poll."""

    def __init__(self, env: dict):
        self.env = env

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.env['YAHOO_ACCESS_TOKEN']}"}

    def _refresh(self) -> None:
        resp = requests.post(
            TOKEN_URL,
            auth=(self.env["CLIENT_ID"], self.env["CLIENT_SECRET"]),
            data={
                "grant_type": "refresh_token",
                "redirect_uri": self.env["REDIRECT_URI"],
                "refresh_token": self.env["YAHOO_REFRESH_TOKEN"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.env["YAHOO_ACCESS_TOKEN"] = payload["access_token"]
        if payload.get("refresh_token"):
            self.env["YAHOO_REFRESH_TOKEN"] = payload["refresh_token"]
        self.env["YAHOO_TOKEN_ISSUED_AT"] = str(int(time.time()))
        save_env(self.env)

    def get_json(self, path: str) -> dict:
        url = f"{API_BASE}/{path}?format=json"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        if resp.status_code == 401:
            self._refresh()
            resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()


def find_all(obj, key: str) -> list:
    """Yahoo's JSON responses nest collections inconsistently depending on
    which subresources were requested -- walk the whole structure for every
    occurrence of `key` rather than assuming a fixed shape/index."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            else:
                found.extend(find_all(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(find_all(item, key))
    return found


def resolve_league_key(session: YahooSession, league_id: str) -> str:
    game = session.get_json("game/nba")
    game_keys = find_all(game, "game_key")
    if not game_keys:
        sys.exit("Couldn't resolve the current NBA game_key from Yahoo -- API response shape may have changed.")
    return f"{game_keys[0]}.l.{league_id}"


def fetch_draft_picks(session: YahooSession, league_key: str) -> list[dict]:
    data = session.get_json(f"league/{league_key}/draftresults")
    results = find_all(data, "draft_result")
    picks = []
    for r in results:
        # each draft_result is itself a list of single-key dicts in Yahoo's
        # JSON flattening (a quirk of their format, not a real list of picks)
        merged = {}
        items = r if isinstance(r, list) else [r]
        for item in items:
            if isinstance(item, dict):
                merged.update(item)
        if merged.get("player_key"):
            picks.append(merged)
    return picks


def resolve_player_names(session: YahooSession, league_key: str, player_keys: list[str]) -> dict[str, str]:
    """player_key -> player name, batched (Yahoo API limits keys per request)."""
    names = {}
    for i in range(0, len(player_keys), PLAYER_BATCH_SIZE):
        batch = player_keys[i:i + PLAYER_BATCH_SIZE]
        data = session.get_json(f"league/{league_key}/players;player_keys=" + ",".join(batch))
        for pk, full in zip(find_all(data, "player_key"), find_all(data, "name")):
            if isinstance(full, dict) and full.get("full"):
                names[pk] = full["full"]
    return names


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = stripped.lower()
    no_punct = re.sub(r"[^a-z\s]", " ", lowered)
    no_suffix = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", no_punct)
    return re.sub(r"\s+", " ", no_suffix).strip()


def load_board_names() -> dict[str, str]:
    """normalized name -> the exact name string draft_board_2026_27.html uses."""
    lookup = {}
    for filename in ["durant_rankings_2026_27.csv", "durant_rankings_rookies_2026_27.csv"]:
        path = REPO_ROOT / filename
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for name in df["PLAYER_NAME"]:
            lookup[normalize_name(name)] = name
    return lookup


def write_output(drafted: set[str], unmatched: set[str]) -> None:
    payload = {
        "drafted": sorted(drafted),
        "unmatched": sorted(unmatched),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(OUTPUT_PATH)  # atomic -- the board's fetch never sees a half-written file


def main() -> None:
    env = load_env()
    session = YahooSession(env)
    league_id = league_id_from_url(env["LEAGUE_URL"])

    print(f"Resolving league key for league {league_id}...")
    league_key = resolve_league_key(session, league_id)
    print(f"League key: {league_key}")

    board_names = load_board_names()
    print(f"Loaded {len(board_names)} player names from the board's data.")

    player_key_to_name: dict[str, str] = {}
    drafted: set[str] = set()
    unmatched: set[str] = set()

    print(f"Polling every {POLL_SECONDS}s. Ctrl-C to stop.")
    try:
        while True:
            try:
                picks = fetch_draft_picks(session, league_key)
                unresolved_keys = [
                    p["player_key"] for p in picks if p["player_key"] not in player_key_to_name
                ]
                if unresolved_keys:
                    player_key_to_name.update(resolve_player_names(session, league_key, unresolved_keys))

                new_this_poll = []
                for p in picks:
                    yahoo_name = player_key_to_name.get(p["player_key"])
                    if not yahoo_name:
                        continue
                    board_name = board_names.get(normalize_name(yahoo_name))
                    if board_name:
                        if board_name not in drafted:
                            new_this_poll.append(board_name)
                        drafted.add(board_name)
                    else:
                        unmatched.add(yahoo_name)

                if new_this_poll:
                    print(f"  +{len(new_this_poll)} new pick(s): {', '.join(new_this_poll)}")
                if unmatched:
                    print(f"  ! {len(unmatched)} pick(s) couldn't be matched to the board: "
                          f"{', '.join(sorted(unmatched))}")

                write_output(drafted, unmatched)
                print(f"[{time.strftime('%H:%M:%S')}] {len(drafted)} drafted total, "
                      f"{len(picks)} pick(s) on Yahoo's board.")
            except requests.RequestException as e:
                print(f"  ! network/API error this poll, will retry: {e}")

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print(f"\nStopped. {len(drafted)} drafted pick(s) saved to {OUTPUT_PATH}.")


if __name__ == "__main__":
    main()
