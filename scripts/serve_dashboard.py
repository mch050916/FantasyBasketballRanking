"""
scripts/serve_dashboard.py — Local web dashboard for the in-season tools
============================================================================
Starts a local server so every in-season tool (punt planner, trade finder,
trade analyzer, buy low/sell high, schedule strength) is a form on a page
instead of a typed command -- one-time startup, then everything after that
is clicking. See dashboard_server.py for the actual request handling and
docs/superpowers/specs/2026-10-21-dashboard-web-tools-design.md for the
full design.

Usage:
    python scripts/serve_dashboard.py
    python scripts/serve_dashboard.py --port 8900
"""

import argparse
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_server import DashboardRequestHandler  # noqa: E402

DEFAULT_PORT = 8731


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the in-season tools web dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    import os
    os.chdir(project_root)

    server = ThreadingHTTPServer(("localhost", args.port), DashboardRequestHandler)
    print(f"Dashboard running at http://localhost:{args.port}/index.html")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
