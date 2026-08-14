"""
rookie_baseline.py — Historical rookie production baseline, by draft slot
============================================================================
Precomputed once from the last 3 completed draft classes (2023, 2024, 2025)
via nba_api's DraftHistory + PlayerCareerStats endpoints -- NOT fetched or
computed at pipeline runtime. See
docs/superpowers/specs/2026-08-14-rookie-incorporation-design.md for the
full design rationale.

Methodology (reproduce this to refresh the table after future draft
classes complete a rookie season):
  1. For each draft year, fetch nba_api.stats.endpoints.DraftHistory
     (season_year_nullable=<year>), keep picks 1-60.
  2. For each drafted player, fetch
     nba_api.stats.endpoints.PlayerCareerStats(player_id=..., per_mode36="PerGame"),
     take the first row whose SEASON_ID starts with the draft year.
  3. Skip players with no rookie-season row yet, or GP == 0 (not lookahead
     bias -- these are draftees who haven't played their rookie season).
  4. Bucket by overall pick (1-5, 6-14, 15-30, 31-60) and average each
     category across the bucket.

Sample sizes (2023-2025 draft classes): 1-5 n=15, 6-14 n=26, 15-30 n=46,
31-60 n=75.
"""

TECH_DEFAULT = 0.05   # matches data.py:fetch_tech_per_game's own fallback estimate

ROOKIE_BASELINE_BY_PICK_BUCKET: dict[tuple[int, int], dict[str, float]] = {
    (1, 5): {
        "GP": 70.333, "MIN": 26.313, "PTS": 13.547, "REB": 4.947, "AST": 2.94,
        "ST": 0.92, "BLK": 0.753, "TO": 1.827, "PF": 2.233, "FGM": 5.093,
        "FGA": 11.32, "FG%": 0.45, "3PTM": 1.4, "FTM": 1.98,
        "DD": 0.0, "TD": 0.0, "TECH": TECH_DEFAULT,
    },
    (6, 14): {
        "GP": 57.308, "MIN": 18.723, "PTS": 7.235, "REB": 3.604, "AST": 1.573,
        "ST": 0.585, "BLK": 0.508, "TO": 1.015, "PF": 1.688, "FGM": 2.719,
        "FGA": 6.065, "FG%": 0.434, "3PTM": 0.873, "FTM": 0.942,
        "DD": 0.0, "TD": 0.0, "TECH": TECH_DEFAULT,
    },
    (15, 30): {
        "GP": 50.022, "MIN": 16.672, "PTS": 6.417, "REB": 2.743, "AST": 1.63,
        "ST": 0.48, "BLK": 0.285, "TO": 0.924, "PF": 1.378, "FGM": 2.367,
        "FGA": 5.513, "FG%": 0.424, "3PTM": 0.798, "FTM": 0.885,
        "DD": 0.0, "TD": 0.0, "TECH": TECH_DEFAULT,
    },
    (31, 60): {
        "GP": 34.36, "MIN": 11.423, "PTS": 3.992, "REB": 2.053, "AST": 0.973,
        "ST": 0.393, "BLK": 0.231, "TO": 0.551, "PF": 1.16, "FGM": 1.483,
        "FGA": 3.401, "FG%": 0.429, "3PTM": 0.465, "FTM": 0.561,
        "DD": 0.0, "TD": 0.0, "TECH": TECH_DEFAULT,
    },
}


def get_rookie_baseline(overall_pick: int) -> dict[str, float] | None:
    """
    Return the historical per-game production baseline for a draft-slot
    bucket, or None if the pick is out of range (undrafted, or an
    off-by-error) -- undrafted players are explicitly out of scope for
    this MVP.
    """
    for (lo, hi), baseline in ROOKIE_BASELINE_BY_PICK_BUCKET.items():
        if lo <= overall_pick <= hi:
            return dict(baseline)
    return None
