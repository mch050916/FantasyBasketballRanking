"""
config.py — League configuration
==================================
This is the ONLY file you need to edit each season.

- Update category weights after your first season to tune for your league.
- Update num_teams if your league size changes.
- Update game_log_seasons and bbr_files in main.py to point to new data.
"""

LEAGUE_CONFIG = {
    # ── Categories ─────────────────────────────────────────────────────────
    # direction: 'high' = more is better, 'low' = less is better
    # type: 'counting' or 'percent'
    "categories": {
        "FGM":  {"direction": "high", "type": "counting"},
        "FG%":  {"direction": "high", "type": "percent"},
        "FTM":  {"direction": "high", "type": "counting"},
        "3PTM": {"direction": "high", "type": "counting"},
        "PTS":  {"direction": "high", "type": "counting"},
        "REB":  {"direction": "high", "type": "counting"},
        "AST":  {"direction": "high", "type": "counting"},
        "ST":   {"direction": "high", "type": "counting"},
        "BLK":  {"direction": "high", "type": "counting"},
        "TO":   {"direction": "low",  "type": "counting"},
        "PF":   {"direction": "low",  "type": "counting"},
        "TECH": {"direction": "low",  "type": "counting"},
        # FF removed: no reliable per-player data in NBA API.
        # Giving everyone the same default makes G-score zero — honest omission
        # beats fake precision.
        "DD":   {"direction": "high", "type": "counting"},
        "TD":   {"direction": "high", "type": "counting"},
    },

    # ── Category weights ───────────────────────────────────────────────────
    # These encode H2H-specific intuitions. Key principles:
    #   - FG% is weekly noise → discount (0.5)
    #   - Low-count cats (ST, BLK, 3PTM) are volatile → slight discount (0.8)
    #   - TO: elite players naturally create more → discount the penalty (0.5)
    #   - TECH: real signal but small magnitude → small weight (0.3)
    #   - DD/TD: custom to your league → tune based on how often they decide
    #     a weekly matchup. Current setting: 0.8 treats them like a counting
    #     stat but slightly below PTS/REB/AST in importance.
    #
    # To tune: after each season, check which categories your team won/lost
    # most often and whether the weights reflected those outcomes.
    "category_weights": {
        "PTS":  1.0,
        "REB":  1.0,
        "AST":  1.0,
        "FGM":  1.0,
        "FTM":  1.0,
        "FG%":  0.5,
        "3PTM": 0.8,
        "ST":   0.8,
        "BLK":  0.8,
        "TO":   0.5,
        "PF":   0.5,
        "TECH": 0.3,
        "DD":   0.72,  # Phase 2: trim remaining milestone carry without erasing DD value
        "TD":   0.56,  # stronger trim after repeat exact-league milestone distortion
    },

    # ── Milestone stat calibration ────────────────────────────────────────
    # DD and TD are sparse event-rate categories. Treat them separately:
    #   - DD still matters in this custom league, so calibration stays light.
    #   - TD is rarer and more distortion-prone, so it gets stronger compression.
    #
    # Formula in model.py:
    #   calibrated = scale * (raw / (1 + curvature * raw))
    #
    # This keeps zero at zero, preserves ordering, and compresses high-end
    # outliers more than moderate contributors.
    "milestone_calibration": {
        "DD": {"scale": 0.92, "curvature": 0.28},
        "TD": {"scale": 0.70, "curvature": 2.40},
    },

    # ── League structure ───────────────────────────────────────────────────
    "num_teams":   10,   # active teams this season (was 8 last season)
    "roster_size": 13,   # active roster spots only (IL spots don't score)

    # ── Projection settings ────────────────────────────────────────────────
    # Season weights: most recent season first.
    # With 2 BBR files: [0.5, 0.3] renormalises automatically to [0.625, 0.375].
    # With 3 BBR files: all three weights are used as-is then renormalised.
    "season_weights": [0.5, 0.3, 0.2],

    # ── NBA API fetch settings ─────────────────────────────────────────────
    # Seasons to pull game logs for (most recent first).
    # Must match the BBR CSV files you have — see main.py.
    "game_log_seasons": ["2025-26", "2024-25", "2023-24"],

    # Draft year(s) to check for incoming rookies with no prior NBA history.
    # Update each season to the upcoming/most recent draft class.
    "draft_years": ["2026"],

    # How many players to fetch game logs for.
    # 150 covers the 130-player draft pool with a buffer.
    # Raising this improves tau accuracy at ~1.5 min per extra 100 players.
    "game_log_player_limit": 150,

    # ── Qualification thresholds ───────────────────────────────────────────
    "min_games": 20,     # minimum games played in a season to qualify
    "min_mpg":   10.0,   # minimum minutes per game to qualify

    # ── Cache files ────────────────────────────────────────────────────────
    # Delete these files to force a fresh NBA API fetch.
    "game_log_cache":     "game_log_cache.pkl",
    "tech_cache":         "tech_cache.pkl",
    "draft_history_cache": "draft_history_cache.pkl",
}

# ── Trade analyzer settings ───────────────────────────────────────────────
# Used only by trade.py / scripts/analyze_trade.py. Nothing here affects
# player scoring or durant_rankings_*.csv.
TRADE_CONFIG = {
    # Fixed so a trade verdict is reproducible run to run. Do not randomize:
    # GitHub issue #9 documents this repo's sensitivity to run-to-run drift.
    "seed": 20262027,

    # Simulated weeks per opponent. 10k gives ~+/-0.005 standard error on a
    # single win probability; common random numbers make the before/after
    # delta far tighter than that.
    "weeks_per_opponent": 10_000,

    # Below this many observed weeks a player's bank cannot carry a
    # distribution's shape, so they route to the synthetic normal fallback.
    "min_weeks_for_bootstrap": 8,

    # Rows in a synthetic bank for fallback players.
    "synthetic_bank_rows": 500,

    # Clip on projected/historical rate ratio.
    "scale_bounds": (0.25, 4.0),
}
