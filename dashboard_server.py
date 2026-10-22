"""
dashboard_server.py — Pure logic for the local in-season-tools web dashboard
================================================================================
Argv-building (form fields -> the exact CLI argv each scripts/*.py already
accepts, same flags, same defaults left to argparse itself -- never
duplicated here) and the /api/meta team/player JSON shape. The actual
HTTP server/subprocess-streaming handler lives in scripts/serve_dashboard.py,
which imports ARGV_BUILDERS and build_meta from here.

Every builder omits a flag entirely when its form field is blank/absent --
the CLI script's own argparse default then applies, so a default never has
to be kept in sync between this file and the script it's building a
command line for.
"""

from pathlib import Path

FIXED_DATA_FLAGS = [
    "--rosters", "rosters.csv",
    "--rankings", "durant_rankings_2026_27.csv",
    "--rookies", "durant_rankings_rookies_2026_27.csv",
]

# buy_low_sell_high.py has no --rosters flag at all (it's not team-specific).
RANKINGS_ONLY_FLAGS = [
    "--rankings", "durant_rankings_2026_27.csv",
    "--rookies", "durant_rankings_rookies_2026_27.csv",
]


def _require(fields: dict, name: str, label: str) -> str:
    value = fields.get(name)
    value = "" if value is None else str(value)
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def build_punt_planner_argv(fields: dict) -> list[str]:
    team = _require(fields, "team", "Team")
    argv = ["scripts/punt_planner.py"] + FIXED_DATA_FLAGS + ["--team", team]
    if fields.get("punt"):
        argv += ["--punt", str(fields["punt"])]
    if fields.get("show_players") not in (None, ""):
        argv += ["--show-players", str(fields["show_players"])]
    return argv


def build_find_trades_argv(fields: dict) -> list[str]:
    argv = ["scripts/find_trades.py"] + FIXED_DATA_FLAGS
    if fields.get("team"):
        argv += ["--team", str(fields["team"])]
    if fields.get("max_value_gap") not in (None, ""):
        argv += ["--max-value-gap", str(fields["max_value_gap"])]
    if fields.get("sim_weeks") not in (None, ""):
        argv += ["--sim-weeks", str(fields["sim_weeks"])]
    if fields.get("top") not in (None, ""):
        argv += ["--top", str(fields["top"])]
    return argv


def build_analyze_trade_argv(fields: dict) -> list[str]:
    team = _require(fields, "team", "Your team")
    partner = _require(fields, "partner", "Partner team")
    argv = ["scripts/analyze_trade.py"] + FIXED_DATA_FLAGS + ["--team", team, "--partner", partner]
    if fields.get("give"):
        argv += ["--give", str(fields["give"])]
    if fields.get("get"):
        argv += ["--get", str(fields["get"])]
    return argv


def build_buy_low_sell_high_argv(fields: dict) -> list[str]:
    argv = ["scripts/buy_low_sell_high.py"] + RANKINGS_ONLY_FLAGS
    if fields.get("season"):
        argv += ["--season", str(fields["season"])]
    if fields.get("min_games") not in (None, ""):
        argv += ["--min-games", str(fields["min_games"])]
    if fields.get("top") not in (None, ""):
        argv += ["--top", str(fields["top"])]
    return argv


def build_schedule_strength_argv(fields: dict) -> list[str]:
    argv = ["scripts/schedule_strength.py", "--rosters", "rosters.csv"]
    if fields.get("week"):
        argv += ["--week", str(fields["week"])]
    if fields.get("team"):
        argv += ["--team", str(fields["team"])]
    return argv


ARGV_BUILDERS = {
    "punt_planner": build_punt_planner_argv,
    "find_trades": build_find_trades_argv,
    "analyze_trade": build_analyze_trade_argv,
    "buy_low_sell_high": build_buy_low_sell_high_argv,
    "schedule_strength": build_schedule_strength_argv,
}


def build_meta(rosters_file: str = "rosters.csv",
               rankings_path: str = "durant_rankings_2026_27.csv",
               rookies_path: str = "durant_rankings_rookies_2026_27.csv") -> dict:
    """
    { "teams": [...], "players": [...], "rosters": {team: [player, ...]} }
    for populating web-form dropdowns and autocomplete -- teams/players
    sorted, rosters in each team's real draft order (same as load_rosters);
    all empty (not an error) when the referenced file doesn't exist yet
    (e.g. a fresh checkout pre-draft). `rosters` lets a form scope a
    player-name field to one team's actual roster instead of the whole pool
    (e.g. analyze_trade's "give" field should only suggest your own team's
    players, not every player in the league).
    """
    from rosters import load_rosters, load_projections

    teams: list[str] = []
    rosters: dict[str, list[str]] = {}
    if Path(rosters_file).exists():
        rosters = load_rosters(rosters_file)
        teams = sorted(rosters.keys())

    players: list[str] = []
    if Path(rankings_path).exists():
        rookies = rookies_path if Path(rookies_path).exists() else None
        projections = load_projections(rankings_path, rookies)
        players = sorted(projections["PLAYER_NAME"].tolist())

    return {"teams": teams, "players": players, "rosters": rosters}


import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler

# One lock per tool, not a single global one -- prevents the same tool
# running twice at once (a double-click, or a second tab left open) without
# blocking unrelated tools from running concurrently. This doesn't fully
# close the shared-NBA-API-cache race between DIFFERENT tools that happen to
# touch the same cache file (e.g. punt_planner and find_trades both read/write
# game_log_cache.pkl) -- that risk is accepted as already-bounded (a
# corrupted cache degrades to a refetch, not silent wrong data, per the
# 2026-10-21 final whole-branch review) in exchange for tools genuinely not
# blocking each other.
_run_locks = {name: threading.Lock() for name in ARGV_BUILDERS}


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """
    Serves the project's static files as-is (index.html, draft_board_*.html,
    tools/*) via the inherited SimpleHTTPRequestHandler behavior, plus two
    API routes layered on top:

      GET  /api/meta       -> build_meta() as JSON
      POST /api/run/<tool> -> runs the real CLI script as a subprocess and
                               streams its combined stdout+stderr back live,
                               one HTTP chunk per raw read -- no server-side
                               line buffering or \\r/\\n interpretation; the
                               frontend owns that (see tools/run.js).
    """

    # BaseHTTPRequestHandler defaults to HTTP/1.0, under which chunked
    # Transfer-Encoding (used by _run_tool's streaming response below) isn't
    # a defined wire format -- a strict client can leak the raw chunk-framing
    # bytes (the "<hex-length>\r\n...\r\n" wrapper _write_chunk adds) into
    # the body as literal text once a response spans more than one chunk.
    # Confirmed live: a long analyze_trade result split a word mid-stream
    # exactly at a chunk boundary. HTTP/1.1 makes chunked encoding legal;
    # every response path here already sets Content-Length or uses
    # Transfer-Encoding correctly, so this has no other effect.
    protocol_version = "HTTP/1.1"

    def _host_is_local(self) -> bool:
        host = self.headers.get("Host", "").split(":")[0]
        return host in ("localhost", "127.0.0.1")

    def end_headers(self):
        # These static files (index.html, tools/run.js, ...) change whenever
        # the user pulls an update mid-season -- the browser must never serve
        # a stale cached copy instead of re-fetching. A real single-user
        # local tool, not a CDN-fronted site; there's no caching benefit
        # worth the staleness risk.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if not self._host_is_local():
            self.send_error(403, "Forbidden")
            return
        if self.path == "/api/meta":
            self._serve_meta()
            return
        super().do_GET()

    def do_POST(self):
        if not self._host_is_local():
            self.send_error(403, "Forbidden")
            return
        if self.path.startswith("/api/run/"):
            self._run_tool(self.path[len("/api/run/"):])
            return
        self.send_error(404, "Not found")

    def _serve_meta(self):
        try:
            body = json.dumps(build_meta()).encode("utf-8")
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Failed to load team/player data: {exc}".encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _run_tool(self, tool: str):
        builder = ARGV_BUILDERS.get(tool)
        if builder is None:
            self.send_error(404, f"Unknown tool: {tool}")
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            fields = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Malformed request body")
            return

        try:
            script_argv = builder(fields)
        except ValueError as exc:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))
            return

        lock = _run_locks[tool]
        if not lock.acquire(blocking=False):
            self.send_response(409)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"This tool is already running in another tab -- wait for it to finish.")
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            # DASHBOARD_JSON_SUMMARY: opt-in per script (currently only
            # analyze_trade.py reads it) -- harmless for scripts that don't
            # check for it, so set unconditionally rather than per-tool.
            env = dict(os.environ, PYTHONUNBUFFERED="1", DASHBOARD_JSON_SUMMARY="1")
            process = subprocess.Popen(
                [sys.executable, "-u"] + script_argv,
                cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            try:
                while True:
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    self._write_chunk(chunk)
                returncode = process.wait()
                self._write_chunk(f"\n[exit code: {returncode}]\n".encode("utf-8"))
            finally:
                if process.poll() is None:
                    process.kill()
                process.stdout.close()
                try:
                    self.wfile.write(b"0\r\n\r\n")
                except OSError:
                    pass
        finally:
            lock.release()

    def _write_chunk(self, data: bytes):
        self.wfile.write(f"{len(data):x}\r\n".encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
