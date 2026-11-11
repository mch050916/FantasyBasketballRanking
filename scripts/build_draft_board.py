"""
build_draft_board.py — Generate the standalone draft-board HTML tool
=======================================================================
Reads durant_rankings_2026_27.csv / durant_rankings_rookies_2026_27.csv
plus the raw BBR season files (for position/team), and writes a single
self-contained HTML file with the data embedded -- no server, no network,
works offline. Re-run this after any pipeline rerun to refresh the board.
"""

import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data import fetch_current_teams      # noqa: E402
from identity import canonical_player_key  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "draft_board_2026_27.html"

Z_COLS = ["PTS_G", "REB_G", "AST_G", "ST_G", "BLK_G", "TO_G",
          "FG%_G", "FTM_G", "3PTM_G", "DD_G", "TD_G", "TECH_G"]
Z_LABELS = ["PTS", "REB", "AST", "ST", "BLK", "TO", "FG%", "FTM", "3PM", "DD", "TD", "TECH"]
# Categories excluded from tag generation (not from the expanded chart, which
# always shows all 12): TD is bimodal -- 105/130 players share its exact floor
# value -- so anyone above it reads as an extreme outlier and it dominates
# every strength tag. TO correlates with usage, so nearly every good player
# reads as weak at it -- true but not distinctive. TECH rides along with TD
# as part of the same low-signal "milestone" group (smallest pool stdev of
# any category, 0.148 post-fix -- barely any real variance to tag on).
#
# DD was excluded here too until 2026-10, on the reasoning that it had the
# same "dominates by variance" effect as TD (then the largest post-weight
# pool stdev of any category, 0.71). That was a real effect at the time, but
# it was a symptom of a sigma/tau unit-mismatch bug in compute_g_scores
# (fixed 2026-10) that had been inflating DD's G-score scale across the
# board -- not something true about DD itself. Post-fix, DD's pool stdev
# (0.464) sits solidly mid-pack, smaller than PTS/REB/AST/FGM/FTM/3PTM, so
# it no longer dominates and is no longer excluded.
TAG_EXCLUDE = {"TO", "TD", "TECH"}
TAG_THRESHOLD = 0.75


def build_data() -> dict:
    rankings = pd.read_csv(REPO_ROOT / "durant_rankings_2026_27.csv")
    rookies = pd.read_csv(REPO_ROOT / "durant_rankings_rookies_2026_27.csv")

    # Display-only rescale: TOTAL_VALUE is centered on the pool mean by
    # construction (model.py), so roughly half the rostered pool is
    # negative -- meaningful for the model and for validate.py's sign-aware
    # diagnostics, confusing on a draft-day board. Shift both pools by the
    # same constant (the worst raw value across either pool) so the board
    # never prints a negative, without touching the underlying model output,
    # the CSVs, or anything validate.py/diagnostics reads.
    VAL_DISPLAY_SHIFT = -min(rankings["TOTAL_VALUE"].min(), rookies["TOTAL_VALUE"].min())

    # Current-roster team, not last-recorded-season team: pos_lookup below is
    # built from BBR's per-season totals files, which name whichever team a
    # player finished the *previous* season on -- stale the moment someone
    # changes teams in the offseason (30/130 veterans this build, see
    # TEAM_CHANGED in durant_rankings_2026_27.csv). fetch_current_teams
    # already exists for exactly this (GitHub issue #13's diagnostic flag) --
    # reused here as the board's actual display source instead of leaving it
    # BBR-only. Canonical-key matched (accents, "Jr."/suffix spelling) the
    # same way every other cross-source player join in this pipeline is.
    # Players absent from the live fetch (unsigned free agents as of the
    # fetch date) fall back to pos_lookup's BBR team below -- no current data
    # beats guessing, same principle as DATA_AVAILABILITY_NOTE elsewhere.
    current_teams = {
        canonical_player_key(name): team
        for name, team in fetch_current_teams(
            season="2026-27", cache_file=str(REPO_ROOT / "current_teams_cache.pkl")
        ).items()
    }

    pos_lookup: dict[str, tuple[str, str]] = {}
    # Actual 2025-26 per-game lines, joined only from that season's BBR totals
    # file (not the 2024-25/2023-24 fallback files pos_lookup also reads --
    # this is "what actually happened last season," not a projection source).
    # drop_duplicates(keep="first") -- same as pos_lookup above -- means a
    # traded player's combined "2TM"/"3TM" row wins over the per-team split
    # rows, since BBR lists the combined row first (verified against Trae
    # Young's 2025-26 rows: 2TM, then ATL, then WAS, in that order).
    # No DD/TD here -- this file has no double-double column (only
    # "Trp-Dbl", a triple-double count), and DD/TD in the pipeline's own
    # projections come from NBA API game logs, a different source entirely.
    actual_2025_26: dict[str, dict] = {}
    for filename in [
        "basketball_reference_2025_26_total_stats.csv",
        "basketball_reference_2024_25_total_stats.csv",
        "basketball_reference_2023_24_total_stats.csv",
    ]:
        raw = pd.read_csv(REPO_ROOT / filename)
        raw = raw[raw["Player"] != "Player"]
        raw = raw.drop_duplicates(subset="Player", keep="first")
        for _, r in raw.iterrows():
            if r["Player"] not in pos_lookup:
                pos_lookup[r["Player"]] = (str(r["Pos"]).split("-")[0], str(r["Team"]))

        if filename == "basketball_reference_2025_26_total_stats.csv":
            for _, r in raw.iterrows():
                if pd.isna(r["G"]):
                    continue
                g = float(r["G"])
                if g <= 0:
                    continue
                actual_2025_26[r["Player"]] = {
                    "gp": int(round(g)),
                    "min": round(float(r["MP"]) / g, 1),
                    "pts": round(float(r["PTS"]) / g, 1),
                    "reb": round(float(r["TRB"]) / g, 1),
                    "ast": round(float(r["AST"]) / g, 1),
                    "st": round(float(r["STL"]) / g, 1),
                    "blk": round(float(r["BLK"]) / g, 1),
                    "to": round(float(r["TOV"]) / g, 1),
                    "fgPct": round(float(r["FG%"]), 3) if pd.notna(r["FG%"]) else 0.0,
                    "threep": round(float(r["3P"]) / g, 1),
                    "ftm": round(float(r["FT"]) / g, 1),
                }

    # Proper per-column z-score: center by the pool mean, then divide by the
    # pool stdev. G-scores are only APPROXIMATELY mean-0 by construction --
    # the ±3.5 clip and FG%'s volume-weighting in model.py's
    # compute_g_scores both nudge the true pool mean off zero -- so centering
    # explicitly (rather than assuming mean≈0, as an earlier version of this
    # chart did) matters for both the tag threshold and the bar heights.
    # ddof=0 on stdev to match model.py's own `transformed.std()` convention
    # (numpy default).
    col_mean = {c: float(rankings[c].mean()) for c in Z_COLS}
    col_stdev = {c: float(rankings[c].std(ddof=0)) for c in Z_COLS}
    # Rookies are scored against their own population, never the veteran
    # pool (same convention as TOTAL_VALUE -- see rosters.player_value_percentiles)
    # -- a separate mean/stdev from the rookie CSV's own _G columns.
    roo_col_mean = {c: float(rookies[c].mean()) for c in Z_COLS}
    roo_col_stdev = {c: float(rookies[c].std(ddof=0)) for c in Z_COLS}

    def player_z(r, mean=col_mean, stdev=col_stdev) -> list[float]:
        return [round((float(r[c]) - mean[c]) / stdev[c], 3) if pd.notna(r[c]) and stdev[c] else 0.0
                for c in Z_COLS]

    def player_projected(r) -> dict:
        return {
            "gp": int(round(float(r["GP"]))),
            "min": round(float(r["MIN"]), 1),
            "pts": round(float(r["PTS"]), 1),
            "reb": round(float(r["REB"]), 1),
            "ast": round(float(r["AST"]), 1),
            "st": round(float(r["ST"]), 1),
            "blk": round(float(r["BLK"]), 1),
            "to": round(float(r["TO"]), 1),
            "fgPct": round(float(r["FG%"]), 3),
            "threep": round(float(r["3PTM"]), 1),
            "ftm": round(float(r["FTM"]), 1),
            "dd": round(float(r["DD"]), 2),
            "td": round(float(r["TD"]), 2),
        }

    # Pure skill-rate projection -- the same season-blended per-game number
    # above, but BEFORE GP_FACTOR/DECLINE_FACTOR's multiply (model.py's
    # `{cat}_RATE` columns). "projected" already has availability/aging
    # priced in for valuation purposes (TOTAL_VALUE depends on it, untouched
    # here); this exists purely so the board can show *why* a player's
    # headline number sits below what their rate alone would suggest,
    # instead of that gap being invisible. No FG% rate: FG% was never
    # GP/decline-adjusted to begin with (see model.py), so there's no gap to
    # explain and showing the same number twice would be noise, not signal.
    def player_rate(r) -> dict:
        return {
            "pts": round(float(r["PTS_RATE"]), 1),
            "reb": round(float(r["REB_RATE"]), 1),
            "ast": round(float(r["AST_RATE"]), 1),
            "st": round(float(r["ST_RATE"]), 1),
            "blk": round(float(r["BLK_RATE"]), 1),
            "to": round(float(r["TO_RATE"]), 1),
            "threep": round(float(r["3PTM_RATE"]), 1),
            "ftm": round(float(r["FTM_RATE"]), 1),
            "dd": round(float(r["DD_RATE"]), 2),
            "td": round(float(r["TD_RATE"]), 2),
        }

    def note_short(note: str) -> str:
        # Two note templates exist today (see DATA_AVAILABILITY_NOTE, main.py):
        # "No 2025-26 data -- projected from <season>[; DD/TD not available...]"
        # "Below qualification threshold in 2025-26 (N GP) -- projected from
        # <season>[; DD/TD not available...]". The GP-count regex is checked
        # first since it's the more specific signal; the DD/TD suffix (3
        # players) is intentionally dropped here -- that detail stays in the
        # full note text, not the row-glance abbreviation.
        if not note:
            return ""
        gp_match = re.search(r"\((\d+) GP\)", note)
        if gp_match:
            return f"{gp_match.group(1)} GP in 25-26"
        if note.startswith("No 2025-26 data"):
            return "no 25-26 data"
        return ""

    def player_tags(z: list[float]) -> list[dict]:
        candidates = [(label, val) for label, val in zip(Z_LABELS, z) if label not in TAG_EXCLUDE]
        strengths = sorted((c for c in candidates if c[1] >= TAG_THRESHOLD), key=lambda c: -c[1])[:2]
        weaknesses = sorted((c for c in candidates if c[1] <= -TAG_THRESHOLD), key=lambda c: c[1])[:2]
        return ([{"label": l, "z": v, "sign": "pos"} for l, v in strengths] +
                [{"label": l, "z": v, "sign": "neg"} for l, v in weaknesses])

    vets = []
    for _, r in rankings.iterrows():
        pos, team = pos_lookup.get(r["PLAYER_NAME"], ("", ""))
        team = current_teams.get(canonical_player_key(r["PLAYER_NAME"]), team)
        note = r["DATA_AVAILABILITY_NOTE"]
        note = "" if (isinstance(note, float) and math.isnan(note)) else str(note)
        # Real NBA injury-report text (body part + mechanism) for the most
        # recent loaded season, when main.py's optional nbainjuries fetch
        # found one -- see main.py's RECENT_SEVERE_INJURY. Diagnostic only,
        # same as DATA_AVAILABILITY_NOTE: surfaced for a human to weigh, no
        # projection adjustment.
        injury = r.get("RECENT_SEVERE_INJURY", "")
        injury = "" if (isinstance(injury, float) and math.isnan(injury)) else str(injury)
        z = player_z(r)
        vets.append({
            "rank": int(r["RANK"]),
            "name": r["PLAYER_NAME"],
            "pos": pos,
            "team": team,
            "val": round(float(r["TOTAL_VALUE"]) + VAL_DISPLAY_SHIFT, 3),
            "note": note,
            "noteShort": note_short(note),
            "injury": injury,
            "z": z,
            "tags": player_tags(z),
            "stats": {
                "projected": player_projected(r),
                "rate": player_rate(r),
                "actual": actual_2025_26.get(r["PLAYER_NAME"]),
                "gpFactor": round(float(r["GP_FACTOR"]), 3),
                "declineFactor": round(float(r["DECLINE_FACTOR"]), 3),
            },
        })

    roos = []
    for _, r in rookies.iterrows():
        roos.append({
            "rank": int(r["RANK"]),
            "name": r["PLAYER_NAME"],
            "pick": int(r["OVERALL_PICK"]),
            "val": round(float(r["TOTAL_VALUE"]) + VAL_DISPLAY_SHIFT, 3),
            "pts": round(float(r["PTS"]), 1),
            "reb": round(float(r["REB"]), 1),
            "ast": round(float(r["AST"]), 1),
            "min": round(float(r["MIN"]), 1),
            "z": player_z(r, roo_col_mean, roo_col_stdev),
        })
    roos.sort(key=lambda r: r["rank"])

    return {"zLabels": Z_LABELS, "tagExclude": sorted(TAG_EXCLUDE), "veterans": vets, "rookies": roos}


def main() -> None:
    data = build_data()
    html = TEMPLATE.replace("__DATA_JSON__", json.dumps(data, separators=(",", ":")))
    OUTPUT_PATH.write_text(html)
    print(f"Wrote {OUTPUT_PATH} ({len(html):,} bytes) -- "
          f"{len(data['veterans'])} veterans, {len(data['rookies'])} rookies")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DURANT Draft Board</title>
<meta name="description" content="A live, fully offline draft-day board for a 14-category head-to-head fantasy basketball league: search, filter, sort, mark picks and track your own team’s category needs in real time.">
<link href="https://fonts.googleapis.com/css2?family=Prata&family=Manrope:wght@400;500;700&display=swap" rel="stylesheet">
<style>
/* Hallmark · shape: kept (app screen) · genre: editorial · theme: Hedgerow (custom pick, gold accent override) · redesign: full
 * hero: none (app screen) · nav: kept · footer: kept (none) · imagery: none · signature: the per-player chart and tags as a field-guide's own index · hedgerow: hedge
 * axes: dark/high-contrast-serif/chromatic-green · posture: drenched · contrast: pass · fold: n/a (app screen) · v2.0.0
 * waive 28 (success/error strength-weakness semantics kept as this tool's own functional signal, reinforced by text labels, not decorative) */
@import url("./tokens.css");
@import url("./base.css");
:root{
  --surface-hover: color-mix(in oklch, var(--color-accent) 12%, transparent);
  --shadow-float: 0 8px 20px oklch(8% 0.01 158 / 0.4);
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--color-paper);color:var(--color-ink);font-family:var(--font-body);}
body{-webkit-font-smoothing:antialiased;}
::selection{background:color-mix(in oklab, var(--color-accent) 30%, transparent);color:var(--color-ink);}
html{scrollbar-color:var(--color-rule) var(--color-paper);}
::-webkit-scrollbar{width:12px;height:12px;}
::-webkit-scrollbar-track{background:var(--color-paper);}
::-webkit-scrollbar-thumb{background:var(--color-rule);border:3px solid var(--color-paper);}
::-webkit-scrollbar-thumb:hover{background:var(--color-muted);}

/* ---------- header / controls ---------- */
.topbar{position:sticky;top:0;z-index:var(--z-sticky-nav);background:var(--color-paper);border-bottom:1px solid var(--color-rule);padding:0 var(--space-md);}
.tabs{display:flex;gap:var(--space-lg);margin-bottom:0;border-bottom:1px solid var(--color-rule);}
.tab{
  font-family:var(--font-body);font-weight:500;font-size:var(--text-sm);
  color:var(--color-muted);background:none;border:none;border-bottom:2px solid transparent;
  padding:var(--space-sm) var(--space-3xs) var(--space-sm);cursor:pointer;margin-top:var(--space-xs);
}
.tab.active{color:var(--color-accent);border-bottom-color:var(--color-accent);}
.tab .count{font-family:var(--font-body);font-weight:400;color:var(--color-muted);margin-left:var(--space-2xs);}
.tab.active .count{color:var(--color-ink-2);}

.searchRow{display:flex;align-items:center;gap:var(--space-sm);padding:var(--space-sm) 0 0;}
.controls{display:flex;align-items:center;gap:var(--space-sm);flex-wrap:wrap;padding:var(--space-sm) 0;border-bottom:1px solid var(--color-rule);}
.search{
  font-family:var(--font-body);font-size:var(--text-sm);color:var(--color-ink);background:var(--color-paper-3);
  border:1px solid var(--color-muted);padding:var(--space-xs) var(--space-sm);width:220px;
}
.search::placeholder{color:var(--color-muted);}
.search:focus-visible{outline:2px solid var(--color-focus);outline-offset:0;}

.chips{display:flex;gap:var(--space-2xs);}
.chip{
  font-family:var(--font-body);font-size:var(--text-sm);font-weight:700;color:var(--color-muted);
  background:transparent;border:1.5px solid var(--color-accent);border-radius:999px;
  padding:var(--space-xs) var(--space-sm);cursor:pointer;user-select:none;
}
.chip.on{color:var(--color-accent-ink);background:var(--color-accent);border-color:var(--color-accent);}
.chip:focus-visible{outline:2px solid var(--color-focus);outline-offset:0;}

.sortSelect{
  font-family:var(--font-body);font-size:var(--text-sm);font-weight:500;color:var(--color-muted);
  background:var(--color-paper-3);border:1px solid var(--color-muted);
  padding:var(--space-xs) var(--space-sm);cursor:pointer;
}

.stats{margin-left:auto;font-family:var(--font-body);font-size:var(--text-sm);color:var(--color-muted);white-space:nowrap;}
.stats b{color:var(--color-ink);font-weight:700;}
.stats .flagged{color:var(--color-accent-2);}

/* undo/confirmation toast -- fires on every drafted-toggle (keyboard or
   click) so a fast multi-letter search-and-Enter always confirms WHO got
   marked, especially important when hide-drafted is on and the row
   vanishes instantly with no other visual trace. */
.toast{
  position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(8px);
  background:var(--color-ink);border:1px solid var(--color-ink);color:var(--color-paper);
  font-family:var(--font-body);font-size:var(--text-sm);padding:var(--space-sm) var(--space-md);cursor:pointer;border-radius:999px;
  opacity:0;pointer-events:none;transition:opacity var(--dur-short) var(--ease-out),transform var(--dur-short) var(--ease-out);z-index:var(--z-toast);
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}
.toast .hint{color:var(--color-paper-2);margin-left:var(--space-xs);}

/* ---------- table ---------- */
.wrap{padding:0 var(--space-md) var(--space-xl);}
table{width:100%;border-collapse:collapse;font-family:var(--font-body);}
thead th{
  position:sticky;top:var(--topbar-h,87px);z-index:var(--z-sticky);background:var(--color-paper);
  text-align:left;font-family:var(--font-body);font-size:var(--text-sm);font-weight:500;
  color:var(--color-muted);padding:var(--space-sm) var(--space-xs) var(--space-xs);border-bottom:1.5px solid var(--color-accent);
}
th.num,td.num{text-align:right;}
tbody tr{border-bottom:1px solid var(--color-rule);cursor:pointer;}
tbody tr[tabindex]:focus-visible{outline:2px solid var(--color-focus);outline-offset:-2px;}
tbody tr:nth-child(even){background:var(--color-paper-2);}
tbody tr:hover{background:var(--surface-hover);}
tbody tr.hidden{display:none;}
td{padding:var(--space-xs) var(--space-xs);vertical-align:middle;font-size:var(--text-sm);font-variant-numeric:tabular-nums;}
.rank{font-family:var(--font-body);color:var(--color-muted);font-size:var(--text-xs);font-weight:700;width:1%;font-variant-numeric:tabular-nums;cursor:pointer;padding:var(--space-2xs) var(--space-sm);text-align:center;user-select:none;}
.rankNum{display:block;padding:var(--space-3xs) 0;}
.rank:hover,.rank:focus-visible{background:var(--surface-hover);color:var(--color-accent);}
.rank:focus-visible{outline:2px solid var(--color-focus);outline-offset:-2px;}
.rankHint{font-family:var(--font-body);font-size:var(--text-xs);font-weight:500;color:var(--color-muted);margin-top:var(--space-3xs);white-space:nowrap;}
.name-cell{min-width:170px;}
.name{font-family:var(--font-display);font-weight:400;font-size:var(--text-lg);color:var(--color-ink);}
.meta{font-family:var(--font-body);font-size:var(--text-xs);color:var(--color-ink-2);margin-left:var(--space-xs);}
.val{font-family:var(--font-display);font-weight:400;font-size:var(--text-xl);color:var(--color-accent-2);font-variant-numeric:tabular-nums;border-left:1.5px solid var(--color-accent);padding-left:var(--space-xs);}

/* drafted state -- the signature: an executed order, not a fade.
   ">> FILLED" reads like a terminal confirming a trade went through. */
tr.drafted{background:var(--color-paper) !important;}
tr.drafted:hover{background:var(--color-paper-2) !important;}
tr.drafted .name{
  color:var(--color-muted);
  text-decoration:line-through;text-decoration-color:var(--color-error);text-decoration-thickness:1px;
}
tr.drafted .meta,tr.drafted .val{color:var(--color-muted);border-left-color:var(--color-rule);}
tr.drafted .tags{opacity:.25;}
tr.chart-row.dim .chart{opacity:.25;}
tr.drafted .noteInline{opacity:.35;}
tr.drafted .balanceStrip{opacity:.35;}
tr.drafted .rowGp{opacity:.35;}
tr.drafted .posRank{opacity:.35;}
tr.drafted .injuryInline{opacity:.35;}

/* availability flag -- readable at a glance, no click required (only 13/130
   rows carry one, so it doesn't add noise). Full note text lives in the
   expanded chart row (.chartNote below). */
.noteInline{font-family:var(--font-body);font-size:var(--text-xs);color:var(--color-accent-deep);margin-left:var(--space-xs);}

/* confirmed severe-injury flag (real NBA injury-report text, see
   main.py's RECENT_SEVERE_INJURY) -- distinct colour from .noteInline since
   it's a different, more serious signal (a real diagnosed injury, not a
   data-coverage gap). A custom CSS tooltip on hover, not the native
   title attribute -- title tooltips turned out unreliable in practice
   (inconsistent show delay/positioning), so this renders its own
   always-the-same popup from a data-tip attribute instead. */
.injuryInline{position:relative;font-family:var(--font-body);font-size:var(--text-xs);color:var(--color-error);margin-left:var(--space-xs);cursor:help;}
.injuryInline:hover::after{
  content:attr(data-tip);
  position:absolute;left:0;top:calc(100% + 6px);z-index:var(--z-tooltip);
  display:block;width:max-content;max-width:280px;
  background:var(--color-ink);border:1px solid var(--color-ink);
  color:var(--color-paper);font-weight:400;font-size:var(--text-xs);letter-spacing:0;
  white-space:normal;line-height:1.4;
  padding:var(--space-xs) var(--space-sm);box-shadow:var(--shadow-float);
}

/* balance strip: 12 threshold-coloured cells (same centered/scaled z the
   tags use, same ±0.75σ cutoff -- a cell colours if and only if that
   category would qualify as a tag, by construction). Blank/border means
   "typical" -- this is deliberately not a continuous heatmap, it shows
   only where a player is UNUSUAL. Fills the space right of tags. */
.rowRight{display:flex;align-items:center;width:100%;}
.rowMid{display:flex;align-items:center;gap:var(--space-sm);margin-left:28px;white-space:nowrap;}
.posRank{font-family:var(--font-body);font-size:var(--text-xs);font-weight:700;color:var(--color-accent);}
.rowGp{font-family:var(--font-body);font-size:var(--text-xs);color:var(--color-ink-2);}
.rowGp b{color:var(--color-ink);font-weight:700;font-variant-numeric:tabular-nums;}

/* tier-cliff marker: a thin rule where the VAL gap to the previous
   undrafted player (in Value order) exceeds CLIFF_THRESHOLD -- live among
   undrafted players, Value-sort only (a category sort's row order isn't
   VAL order, so a VAL-gap marker there would land on arbitrary rows). */
tr.cliff{border-top:1.5px dashed var(--color-accent);}
.balanceStrip{display:flex;gap:1px;width:250px;margin-left:auto;flex:none;}
.balanceCell{flex:1;display:flex;flex-direction:column;align-items:center;}
.balanceCell .sw{width:100%;height:15px;}
.balanceCell .l{font-family:var(--font-body);font-size:8px;color:var(--color-muted);margin-top:var(--space-3xs);letter-spacing:-.03em;overflow:hidden;white-space:nowrap;}

/* strength/weakness tags: up to 2 green + 2 red pills per row, category
   name only -- click the row to see all 12 categories in the expanded
   chart below it. TD/TECH/TO are excluded from tag generation (see
   TAG_EXCLUDE in build_draft_board.py) but still appear in that chart. */
.tags{display:flex;align-items:center;gap:var(--space-xs);flex-wrap:wrap;min-height:26px;}
.tag{
  font-family:var(--font-body);font-size:var(--text-sm);font-weight:700;letter-spacing:.02em;
  padding:var(--space-2xs) var(--space-sm);border:1px solid currentColor;border-radius:999px;
}
.tag.pos{color:var(--color-success);background:color-mix(in oklch, var(--color-success) 18%, transparent);}
.tag.neg{color:var(--color-error);background:color-mix(in oklch, var(--color-error) 18%, transparent);}
.tagLegend{display:flex;align-items:center;gap:var(--space-md);font-family:var(--font-body);font-size:var(--text-xs);font-weight:400;color:var(--color-ink-2);white-space:nowrap;}
.tagLegend .sw{display:inline-block;width:var(--space-xs);height:var(--space-xs);border-radius:50%;margin-right:var(--space-2xs);vertical-align:-1px;}
.tagLegend .sw.pos{background:var(--color-success);}
.tagLegend .sw.neg{background:var(--color-error);}

/* live category-need panel: sum of z-scores across rows marked "mine"
   (shift+click a rank), weakest category first -- see updateMineSummary */
.mineSummary{display:flex;align-items:center;gap:var(--space-xs);flex-wrap:wrap;padding:var(--space-xs) 0;
  border-bottom:1px solid var(--color-rule);min-height:34px;}
.mineLabel{font-family:var(--font-body);font-size:var(--text-xs);font-weight:500;color:var(--color-ink-2);white-space:nowrap;}
.mineHint{font-family:var(--font-body);font-size:var(--text-xs);color:var(--color-muted);}
.mineCat{font-family:var(--font-body);font-size:var(--text-xs);font-weight:700;padding:var(--space-3xs) var(--space-xs);border:1px solid currentColor;border-radius:999px;white-space:nowrap;}
.mineCat.pos{color:var(--color-success);}
.mineCat.neg{color:var(--color-error);}
.mineCat.flat{color:var(--color-muted);}
.mineStar{display:block;color:var(--color-muted);cursor:pointer;font-size:var(--text-xs);font-weight:500;
  user-select:none;padding:var(--space-2xs) 0 var(--space-3xs);
  border-top:1px solid var(--color-rule);}
.mineStar:hover{color:var(--color-accent);}
tr.mine .mineStar{color:var(--color-accent);font-weight:800;}
tr.mine .rank{color:var(--color-accent);}
tr.mine .name{text-decoration:underline;text-decoration-color:var(--color-accent);text-decoration-thickness:2px;}

/* expanded row: projected/actual per-game stat cards, then the category chart */
tr.chart-row td{padding:var(--space-sm) var(--space-xs) var(--space-sm) var(--space-xl);background:var(--color-paper-2);}
tr.chart-row.hidden{display:none;}
tr.chart-row:not(.open){display:none;}
.statBlockLabel,.chartLabel{
  font-family:var(--font-body);font-size:var(--text-xs);font-weight:500;
  color:var(--color-muted);margin:var(--space-3xs) 0 var(--space-xs);
}
.chartNote{font-family:var(--font-body);font-size:var(--text-sm);color:var(--color-accent-deep);margin-bottom:var(--space-md);}
.statRow{display:flex;gap:var(--space-xs);flex-wrap:wrap;margin-bottom:var(--space-md);}
.statCard{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-width:44px;background:var(--color-paper-3);border:1px solid var(--color-rule);padding:var(--space-xs) var(--space-2xs);color:var(--color-ink);
}
.statCard .v{font-family:var(--font-body);font-size:var(--text-sm);font-weight:700;color:var(--color-ink);font-variant-numeric:tabular-nums;}
.statCard .l{font-family:var(--font-body);font-size:9px;color:var(--color-ink-2);margin-top:var(--space-3xs);letter-spacing:.03em;}
.statEmpty{font-family:var(--font-body);font-size:var(--text-sm);color:var(--color-muted);margin-bottom:var(--space-md);}

/* per-player category chart: all 12 categories, one shared 0-baseline,
   per-column z-score normalization (same values as the tags), category
   label + numeric value under each bar, bar height clamped at ±3σ
   (the printed value is never clamped, only the bar). */
.chart{position:relative;display:flex;gap:var(--space-3xs);height:100px;}
.chart .baseline{position:absolute;left:0;right:0;top:32px;height:1px;background:var(--color-rule);}
.chart .col{position:relative;width:48px;flex:none;display:flex;flex-direction:column;align-items:center;}
.chart .barTrack{position:relative;width:100%;height:64px;}
.chart .bar{position:absolute;left:10px;right:10px;}
.chart .bar.pos{background:var(--color-success);bottom:50%;}
.chart .bar.neg{background:var(--color-error);top:50%;}
.chart .label{font-family:var(--font-body);font-size:var(--text-xs);font-weight:500;color:var(--color-ink-2);margin-top:var(--space-2xs);}
.chart .value{font-family:var(--font-body);font-size:9.5px;color:var(--color-muted);}

/* ---------- rookies ---------- */
.disclaimer{
  background:var(--color-paper-3);border:1.5px solid var(--color-accent);
  color:var(--color-ink);font-family:var(--font-body);font-size:var(--text-sm);padding:var(--space-sm) var(--space-md);margin:var(--space-sm) 0;
}
.disclaimer::before{content:"Note: ";font-weight:700;color:var(--color-accent-2);}
.tier-block{margin:var(--space-lg) 0 var(--space-xs);}
.tier-title{
  font-family:var(--font-display);font-weight:400;font-size:var(--text-lg);
  color:var(--color-ink);border-bottom:1.5px solid var(--color-accent);padding-bottom:var(--space-2xs);margin-bottom:var(--space-3xs);
}
.tier-title .n{color:var(--color-muted);font-weight:400;font-family:var(--font-body);font-size:var(--text-sm);margin-left:var(--space-xs);}

.empty{padding:var(--space-xl) var(--space-xs);color:var(--color-muted);font-family:var(--font-body);font-size:var(--text-sm);}

@media (max-width:640px){
  .search{width:150px;}
  .chart{overflow-x:auto;}
  .stats{width:100%;order:10;margin-left:0;}
  /* the balance strip and positional/GP badge are supplementary reads --
     full 12-category detail is one tap away via the expanded chart row,
     so dropping them here (rather than shrinking them illegibly) is what
     keeps the collapsed row from forcing horizontal scroll on a phone. */
  .rowMid,.balanceStrip{display:none;}
  .name-cell{min-width:0;}
  .meta{display:block;margin-left:0;}
  .tagLegend{white-space:normal;}
}
.chip:active,.mineStar:active{opacity:.7;}
button:disabled,input:disabled,select:disabled{opacity:.55;cursor:not-allowed;}
</style>
</head>
<body>

<div class="topbar">
  <div class="tabs">
    <button class="tab active" data-tab="vets">Veterans <span class="count" id="vetCount"></span></button>
    <button class="tab" data-tab="roos">Rookies <span class="count" id="rooCount"></span></button>
  </div>
  <div class="searchRow">
    <input class="search" id="search" type="text" placeholder="Search… ( / )" autocomplete="off">
    <button class="chip" id="hideDraftedChip" type="button">Hide drafted</button>
  </div>
  <div class="controls" id="vetControls">
    <div class="chips" id="posChips"></div>
    <select class="sortSelect" id="sortSelect"></select>
    <div class="stats" id="statLine"></div>
  </div>
  <div class="controls" id="rooControls" style="display:none">
    <div class="stats" id="statLineRoo"></div>
  </div>
  <div class="mineSummary" id="mineSummary"></div>
</div>

<div class="toast" id="toast"></div>

<div class="wrap">
  <div id="vetsPane">
    <table>
      <thead>
        <tr>
          <th class="rank">#<div class="rankHint">draft</div></th>
          <th class="name-cell">Player</th>
          <th class="num">Val</th>
          <th>
            <div class="tagLegend">
              <span class="sw pos"></span>strength ≥ +0.75σ,
              <span class="sw neg"></span>weakness ≤ -0.75σ.
              Click a row for all 12 categories, click &#9733; for “mine.”
            </div>
          </th>
        </tr>
      </thead>
      <tbody id="vetBody"></tbody>
    </table>
  </div>

  <div id="roosPane" style="display:none">
    <div class="disclaimer">Speculative: pick-curve + combine-residual regression, not real in-season data. Each rookie gets an individually ranked projection.</div>
    <div id="rooTiers"></div>
  </div>
</div>

<script id="draft-data" type="application/json">__DATA_JSON__</script>
<script>
(function(){
  "use strict";
  var DATA = JSON.parse(document.getElementById("draft-data").textContent);
  var Z_LABELS = DATA.zLabels;
  var TAG_EXCLUDE = new Set(DATA.tagExclude);
  var STORE_KEY = "draftBoard2026_27_drafted";
  var MINE_KEY = "draftBoard2026_27_mine";

  function esc(s){
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  /* sticky thead offset: measure the real topbar height instead of guessing */
  function syncStickyOffset(){
    var h = document.querySelector(".topbar").offsetHeight;
    document.documentElement.style.setProperty("--topbar-h", h + "px");
  }
  window.addEventListener("resize", syncStickyOffset);

  function makeRowActivatable(tr){
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " "){
        e.preventDefault();
        tr.click();
      }
    });
  }

  function loadSet(key){
    try { return new Set(JSON.parse(localStorage.getItem(key) || "[]")); }
    catch(e){ return new Set(); }
  }
  function saveSet(key, set){
    localStorage.setItem(key, JSON.stringify(Array.from(set)));
  }
  var drafted = loadSet(STORE_KEY);
  function saveDrafted(){ saveSet(STORE_KEY, drafted); }

  /* ---------- "mine" -- shift+click a rank to mark it as your own pick ----
     Independent of `drafted`: punting/category-need only make sense scoped
     to your own roster, not everyone who's gone off the board. Marking
     "mine" also marks drafted (you can't own a pick nobody's made), but
     un-marking "mine" leaves drafted alone -- for correcting a mis-click,
     not un-drafting the player. */
  var mine = loadSet(MINE_KEY);
  function saveMine(){ saveSet(MINE_KEY, mine); }

  function zKey(kind, name){ return kind + ":" + name; }

  /* ---------- shared drafted-toggle + undo + confirmation toast ----------
     One function handles every drafted-toggle path (rank-cell click, row
     click on a rookie, keyboard Enter) so undo/toast coverage is uniform
     rather than special-cased per trigger. Single-slot undo (most recent
     action only), not a full history stack -- matches "a fast path back
     for a genuine mistake," not a redo stack. */
  var toastEl = document.getElementById("toast");
  var toastTimer = null;
  function showToast(text, undoable){
    toastEl.innerHTML = esc(text) + (undoable ? '<span class="hint">click or ⌘Z to undo</span>' : "");
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function(){ toastEl.classList.remove("show"); }, 2500);
  }

  var lastAction = null; /* {rowObj, prevState} for the single most recent toggle */

  function setRowDrafted(rowObj, isDrafted, opts){
    opts = opts || {};
    if (isDrafted) drafted.add(rowObj.key); else drafted.delete(rowObj.key);
    rowObj.tr.classList.toggle("drafted", isDrafted);
    if (rowObj.chartRow) rowObj.chartRow.classList.toggle("dim", isDrafted);
    saveDrafted();
    if (!isDrafted && mine.has(rowObj.key)){
      /* can't own a pick that's back on the board */
      mine.delete(rowObj.key);
      rowObj.tr.classList.remove("mine");
      saveMine();
      updateMineSummary();
    }
    if (opts.silent){
      /* live-sync applies several picks per poll -- one consolidated toast
         from the caller beats one "Drafted: X" per player. */
    } else if (opts.recordUndo !== false){
      lastAction = {rowObj: rowObj, prevState: !isDrafted};
      showToast((isDrafted ? "Drafted: " : "Undrafted: ") + rowObj.name, true);
    } else {
      showToast("Restored: " + rowObj.name, false);
    }
    updateStats();
    updateRooStats();
    applyFilter(); /* re-run so hide-drafted immediately shows/hides this row */
    updatePositionalRanks();
    updateCliffMarkers();
  }

  toastEl.addEventListener("click", function(){ undoLast(); });

  function undoLast(){
    if (!lastAction) return;
    var a = lastAction;
    lastAction = null;
    setRowDrafted(a.rowObj, a.prevState, {recordUndo: false});
  }

  function toggleMine(rowObj){
    var isMine = !mine.has(rowObj.key);
    if (isMine) mine.add(rowObj.key); else mine.delete(rowObj.key);
    rowObj.tr.classList.toggle("mine", isMine);
    saveMine();
    if (isMine && !drafted.has(rowObj.key)) setRowDrafted(rowObj, true, {silent: true});
    showToast((isMine ? "Marked mine: " : "Unmarked: ") + rowObj.name, false);
    updateMineSummary();
  }

  /* ---------- live category-need panel ----------
     Sums the per-category z-score (Z_LABELS order) across every veteran or
     rookie marked "mine" -- a quick, honest, zero-backend read of which
     categories your actual roster is weak in as you draft. Rookies are
     z-scored against the rookie pool, not the veteran one (same convention
     TOTAL_VALUE already uses), via build_draft_board.py's roo_col_mean/
     roo_col_stdev -- summing both pools' z together treats "unusual for a
     rookie" and "unusual for a veteran" as the same unit, an approximation
     the alternative (no rookie signal at all) was strictly worse than. */
  var mineSummaryEl = document.getElementById("mineSummary");
  function updateMineSummary(){
    var picks = vetRows.concat(rooRows).filter(function(r){ return mine.has(r.key); });

    if (!picks.length){
      mineSummaryEl.innerHTML = '<span class="mineLabel">MY TEAM (0)</span>' +
        '<span class="mineHint">click the &#9733; next to a rank to start tracking your team</span>';
    } else {
      var sums = Z_LABELS.map(function(_, i){
        return picks.reduce(function(acc, r){ return acc + r.z[i]; }, 0);
      });
      var order = Z_LABELS.map(function(_, i){ return i; })
        .sort(function(a, b){ return sums[a] - sums[b]; });
      var cells = order.map(function(i){
        var cls = sums[i] >= 0.5 ? "pos" : (sums[i] <= -0.5 ? "neg" : "flat");
        return '<span class="mineCat ' + cls + '">' + Z_LABELS[i] + ' ' +
          (sums[i] >= 0 ? "+" : "") + sums[i].toFixed(1) + '</span>';
      }).join("");
      mineSummaryEl.innerHTML =
        '<span class="mineLabel">MY TEAM (' + picks.length + ') -- weakest first:</span>' + cells;
    }
    syncStickyOffset(); /* defensive: chip count can still change wrap height */
  }

  /* ---------- tags (collapsed row) + expanded per-player chart ----------
     Each player's `z` array is a proper per-category z-score (centered on
     the pool mean, divided by the pool stdev) computed at build time -- see
     build_draft_board.py -- and `tags` is precomputed from that same array
     (threshold ±0.75σ, TD/TECH/TO excluded). The expanded chart reuses `z`
     for all 12 categories; only the tags are restricted. */
  var CHART_SCALE = 3.0; /* z magnitude that fills a full half-chart; display only, values print unclamped */

  function tagsHTML(tags){
    return tags.map(function(t){
      var title = t.label + " " + (t.sign === "pos" ? "+" : "") + t.z.toFixed(2) + "σ";
      return '<span class="tag ' + t.sign + '" title="' + title + '">' + t.label + '</span>';
    }).join("");
  }

  /* balance strip: threshold-colored, not a continuous heatmap -- blank
     (var(--border)) means "typical," so the strip shows only where a
     player is unusual. Same z source and ±0.75σ cutoff as the tags
     (TAG_THRESHOLD in build_draft_board.py). All 12 categories render for
     a consistent fixed-order layout, but TO/TD/TECH/DD are always neutral
     placeholders (never colored) -- those 4 are permanently excluded from
     tag generation because their naturally small pool variance makes
     ordinary values read as extreme (verified against Kawhi Leonard,
     whose TECH z-score alone was +2.13). Placeholder rather than omitted
     keeps "a cell colors iff it would also qualify as a tag" true, while
     still showing all 12 category labels. */
  var BALANCE_THRESHOLD = 0.75;
  var BALANCE_STRONG = 1.5;
  function balanceColor(z){
    if (z >= BALANCE_STRONG) return "#3ddc97";
    if (z >= BALANCE_THRESHOLD) return "#6fae92";
    if (z <= -BALANCE_STRONG) return "#ff6b6b";
    if (z <= -BALANCE_THRESHOLD) return "#c98888";
    return "var(--border)";
  }

  function balanceStripHTML(zArr){
    var out = "";
    for (var i = 0; i < Z_LABELS.length; i++){
      var z = zArr[i];
      var excluded = TAG_EXCLUDE.has(Z_LABELS[i]);
      var color = excluded ? "var(--border)" : balanceColor(z);
      var title = Z_LABELS[i] + " " + (z >= 0 ? "+" : "") + z.toFixed(2) + "σ" + (excluded ? " (not scored)" : "");
      out += '<div class="balanceCell" title="' + title + '">' +
        '<span class="sw" style="background:' + color + '"></span>' +
        '<span class="l">' + Z_LABELS[i] + '</span></div>';
    }
    return out;
  }

  function chartHTML(zArr){
    var out = '<span class="baseline"></span>';
    for (var i = 0; i < Z_LABELS.length; i++){
      var z = zArr[i];
      var pct = Math.max(0, Math.min(50, Math.abs(z) / CHART_SCALE * 50));
      var cls = z >= 0 ? "pos" : "neg";
      out += '<div class="col">' +
        '<div class="barTrack"><span class="bar ' + cls + '" style="height:' + pct + '%"></span></div>' +
        '<span class="label">' + Z_LABELS[i] + '</span>' +
        '<span class="value">' + (z >= 0 ? "+" : "") + z.toFixed(2) + '</span>' +
        '</div>';
    }
    return out;
  }

  /* ---------- projected/actual per-game stat cards (expanded row, above the chart) ----------
     `stats.projected` always has all 13 fields; `stats.actual` has the same 11
     minus dd/td (that BBR file has no double-double column) and is null for
     players with no 2025-26 row at all -- see build_draft_board.py. */
  var STAT_FIELDS = [
    {key:"gp", label:"GP", dec:0},
    {key:"min", label:"MIN", dec:1},
    {key:"pts", label:"PTS", dec:1},
    {key:"reb", label:"REB", dec:1},
    {key:"ast", label:"AST", dec:1},
    {key:"st", label:"ST", dec:1},
    {key:"blk", label:"BLK", dec:1},
    {key:"to", label:"TO", dec:1},
    {key:"fgPct", label:"FG%", dec:3, stripZero:true},
    {key:"threep", label:"3PM", dec:1},
    {key:"ftm", label:"FTM", dec:1},
    {key:"dd", label:"DD", dec:2},
    {key:"td", label:"TD", dec:2}
  ];
  var ACTUAL_FIELDS = STAT_FIELDS.slice(0, 11); /* everything but dd, td */
  /* rate has no gp/min/fgPct -- gp/min aren't rate quantities, and FG% was
     never GP/decline-adjusted to begin with (model.py), so there's no gap
     to show for it. */
  var RATE_FIELDS = STAT_FIELDS.filter(function(f){
    return f.key !== "gp" && f.key !== "min" && f.key !== "fgPct";
  });

  function fmtStat(v, dec, stripZero){
    var s = v.toFixed(dec);
    if (stripZero) s = s.replace(/^(-?)0\./, "$1.");
    return s;
  }

  function statCardsHTML(stats, fields){
    return fields.map(function(f){
      return '<div class="statCard"><span class="v">' + fmtStat(stats[f.key], f.dec, f.stripZero) +
        '</span><span class="l">' + f.label + '</span></div>';
    }).join("");
  }

  function statsBlockHTML(stats){
    var out = "";
    if (stats.rate){
      out += '<div class="statBlockLabel">Rate — before availability/age adjustment</div>' +
        '<div class="statRow">' + statCardsHTML(stats.rate, RATE_FIELDS) + '</div>';
    }
    var adjBits = [stats.gpFactor.toFixed(2) + '× GP_FACTOR'];
    if (stats.declineFactor < 1) adjBits.push(stats.declineFactor.toFixed(2) + '× DECLINE_FACTOR');
    out += '<div class="statBlockLabel">Projected 2026-27 per game — ' + adjBits.join(' × ') + ' applied</div>' +
      '<div class="statRow">' + statCardsHTML(stats.projected, STAT_FIELDS) + '</div>';
    if (stats.actual){
      out += '<div class="statBlockLabel">Actual 2025-26 per game — ' + stats.actual.gp + ' GP</div>' +
        '<div class="statRow">' + statCardsHTML(stats.actual, ACTUAL_FIELDS) + '</div>';
    } else {
      out += '<div class="statBlockLabel">Actual 2025-26 per game</div>' +
        '<div class="statEmpty">No 2025-26 data</div>';
    }
    return out;
  }

  var openChart = null; /* the rowObj whose chart is currently expanded, if any */

  function closeOpenChart(){
    if (openChart && openChart.chartRow) openChart.chartRow.classList.remove("open");
    openChart = null;
  }

  function openChartFor(rowObj){
    if (!rowObj.chartRow){
      var tr2 = document.createElement("tr");
      tr2.className = "chart-row";
      if (drafted.has(rowObj.key)) tr2.classList.add("dim");
      var td = document.createElement("td");
      td.colSpan = 4;
      var noteHTML = rowObj.note ? '<div class="chartNote">⚠ ' + esc(rowObj.note) + '</div>' : "";
      td.innerHTML = noteHTML + statsBlockHTML(rowObj.stats) +
        '<div class="chartLabel">Category value vs pool</div>' +
        '<div class="chart">' + chartHTML(rowObj.z) + '</div>';
      tr2.appendChild(td);
      rowObj.tr.parentNode.insertBefore(tr2, rowObj.tr.nextSibling);
      rowObj.chartRow = tr2;
    }
    rowObj.chartRow.classList.add("open");
    openChart = rowObj;
  }

  function toggleChart(rowObj){
    if (openChart === rowObj){ closeOpenChart(); return; }
    closeOpenChart();
    openChartFor(rowObj);
  }

  /* ---------- veterans table ---------- */
  var vetBody = document.getElementById("vetBody");
  var vetRows = [];

  DATA.veterans.forEach(function(v){
    var tr = document.createElement("tr");
    tr.dataset.name = v.name.toLowerCase();
    tr.dataset.pos = v.pos;
    var key = zKey("v", v.name);
    if (drafted.has(key)) tr.classList.add("drafted");
    if (mine.has(key)) tr.classList.add("mine");

    var noteInline = v.noteShort ? '<span class="noteInline">' + esc(v.noteShort) + '</span>' : "";
    var injuryInline = v.injury ? '<span class="injuryInline" data-tip="' + esc(v.injury) + '" title="' + esc(v.injury) + '">&#8853; injury</span>' : "";

    tr.innerHTML =
      '<td class="rank" tabindex="0" role="button" title="Click to toggle drafted">' +
        '<span class="rankNum">' + v.rank + '</span>' +
        '<span class="mineStar" title="Mark as your pick">&#9733; mine</span></td>' +
      '<td class="name-cell"><span class="name">' + esc(v.name) + '</span>' +
        '<span class="meta">' + esc(v.pos) + (v.team ? " · " + esc(v.team) : "") + '</span>' + noteInline + injuryInline + '</td>' +
      '<td class="num val">' + v.val.toFixed(2) + '</td>' +
      '<td><div class="rowRight"><div class="tags">' + tagsHTML(v.tags) + '</div>' +
        '<div class="rowMid">' +
          '<span class="posRank" title="Rank among undrafted ' + esc(v.pos) + 's">—</span>' +
          '<span class="rowGp"><b>' + v.stats.projected.gp + '</b> GP</span>' +
        '</div>' +
        '<div class="balanceStrip">' + balanceStripHTML(v.z) + '</div></div></td>';

    var rowObj = {tr: tr, name: v.name, pos: v.pos, key: key, rank: v.rank, val: v.val, z: v.z, stats: v.stats,
                  note: v.note, posRankEl: null, chartRow: null};
    rowObj.posRankEl = tr.querySelector(".posRank");

    var rankCell = tr.querySelector(".rank");
    rankCell.addEventListener("click", function(e){
      if (e.target.closest(".mineStar")) return; /* star has its own handler */
      e.stopPropagation();
      setRowDrafted(rowObj, !drafted.has(key));
    });
    rankCell.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " "){
        e.preventDefault(); e.stopPropagation();
        setRowDrafted(rowObj, !drafted.has(key));
      }
    });
    tr.querySelector(".mineStar").addEventListener("click", function(e){
      e.stopPropagation();
      toggleMine(rowObj);
    });

    makeRowActivatable(tr);
    tr.addEventListener("click", function(e){
      toggleChart(rowObj);
    });

    vetBody.appendChild(tr);
    vetRows.push(rowObj);
  });

  /* position chips */
  var POSITIONS = ["PG","SG","SF","PF","C"];
  var activePos = new Set();
  var chipsWrap = document.getElementById("posChips");
  POSITIONS.forEach(function(p){
    var b = document.createElement("button");
    b.className = "chip"; b.textContent = p; b.type = "button";
    b.addEventListener("click", function(){
      if (activePos.has(p)) { activePos.delete(p); b.classList.remove("on"); }
      else { activePos.add(p); b.classList.add("on"); }
      applyFilter();
    });
    chipsWrap.appendChild(b);
  });

  /* positional rank: computed among UNDRAFTED players only, at each of the
     5 positions, ordered by true overall rank (not whatever the current
     display sort is) -- this is the scarcity number that actually drives
     draft decisions, not overall rank. Recomputed on every drafted-state
     change (see setRowDrafted). A drafted player's badge simply stops
     updating rather than clearing, so it reads as "last live value before
     going off the board." */
  function updatePositionalRanks(){
    POSITIONS.forEach(function(pos){
      var group = vetRows.filter(function(r){ return r.pos === pos; })
                          .sort(function(a, b){ return a.rank - b.rank; });
      var i = 0;
      group.forEach(function(r){
        if (drafted.has(r.key)) return;
        i++;
        r.posRankEl.textContent = pos + i;
      });
    });
  }

  /* tier-cliff marker: a thin rule where the VAL gap to the previous
     undrafted player (in true Value order) exceeds CLIFF_THRESHOLD --
     verified against real data (9 cliffs across 130 players at this
     threshold, mean gap 0.10/median 0.046, so 0.25 is a genuine outlier
     cutoff, not noise). Live among undrafted players; only rendered when
     sorted by Value, since a category sort's row order isn't VAL order. */
  var CLIFF_THRESHOLD = 0.25;
  function updateCliffMarkers(){
    vetRows.forEach(function(r){ r.tr.classList.remove("cliff"); });
    if (sortSelect.value !== "value") return;
    var undraftedInOrder = vetRows.filter(function(r){ return !drafted.has(r.key); })
                                   .sort(function(a, b){ return a.rank - b.rank; });
    for (var i = 1; i < undraftedInOrder.length; i++){
      var gap = undraftedInOrder[i - 1].val - undraftedInOrder[i].val;
      if (gap > CLIFF_THRESHOLD) undraftedInOrder[i].tr.classList.add("cliff");
    }
  }

  /* category sort: any of the 12 categories, descending by that category's
     z-score (already sign-corrected, e.g. TO), or back to "Value" (rank
     order) -- veterans only; rookies are always shown as a flat table
     ordered by their individual rank. */
  var sortSelect = document.getElementById("sortSelect");
  (function(){
    var opt = document.createElement("option");
    opt.value = "value"; opt.textContent = "Sort: Value";
    sortSelect.appendChild(opt);
    Z_LABELS.forEach(function(label, idx){
      var o = document.createElement("option");
      o.value = String(idx); o.textContent = "Sort: " + label;
      sortSelect.appendChild(o);
    });
  })();
  sortSelect.addEventListener("change", applySort);

  function applySort(){
    var val = sortSelect.value;
    if (val === "value"){
      vetRows.sort(function(a, b){ return a.rank - b.rank; });
    } else {
      var idx = parseInt(val, 10);
      vetRows.sort(function(a, b){ return b.z[idx] - a.z[idx]; });
    }
    vetRows.forEach(function(r){
      vetBody.appendChild(r.tr);
      if (r.chartRow) vetBody.appendChild(r.chartRow);
    });
    updateCliffMarkers();
  }

  /* search + hide-drafted are shared across both tabs: typing filters
     veterans AND rookies at once, auto-switching to whichever tab has
     matches so a rookie going off the board never needs a manual tab
     switch. Position chips stay veteran-only (rookies have no position). */
  var searchEl = document.getElementById("search");
  var hideDrafted = false;
  var hideDraftedChip = document.getElementById("hideDraftedChip");
  hideDraftedChip.addEventListener("click", function(){
    hideDrafted = !hideDrafted;
    hideDraftedChip.classList.toggle("on", hideDrafted);
    applyFilter();
  });
  searchEl.addEventListener("input", applyFilter);

  function switchTab(name){
    tabs.forEach(function(x){ x.classList.toggle("active", x.dataset.tab === name); });
    var isVets = name === "vets";
    document.getElementById("vetsPane").style.display = isVets ? "" : "none";
    document.getElementById("roosPane").style.display = isVets ? "none" : "";
    document.getElementById("vetControls").style.display = isVets ? "" : "none";
    document.getElementById("rooControls").style.display = isVets ? "none" : "";
    syncStickyOffset();
  }

  function applyFilter(){
    var q = searchEl.value.trim().toLowerCase();

    var vetVisible = 0;
    vetRows.forEach(function(r){
      var matchName = !q || r.name.toLowerCase().indexOf(q) !== -1;
      var matchPos = activePos.size === 0 || activePos.has(r.pos);
      var matchDrafted = !hideDrafted || !drafted.has(r.key);
      var show = matchName && matchPos && matchDrafted;
      if (show) vetVisible++;
      r.tr.classList.toggle("hidden", !show);
      if (r.chartRow){
        r.chartRow.classList.toggle("hidden", !show);
        if (!show && openChart === r) closeOpenChart();
      }
    });

    var rooVisible = 0;
    rooRows.forEach(function(r){
      var matchName = !q || r.name.toLowerCase().indexOf(q) !== -1;
      var matchDrafted = !hideDrafted || !drafted.has(r.key);
      var show = matchName && matchDrafted;
      if (show) rooVisible++;
      r.tr.classList.toggle("hidden", !show);
    });

    if (q){
      var activeIsVets = document.getElementById("vetsPane").style.display !== "none";
      if (activeIsVets && vetVisible === 0 && rooVisible > 0) switchTab("roos");
      else if (!activeIsVets && rooVisible === 0 && vetVisible > 0) switchTab("vets");
    }

    updateStats();
    updateRooStats();
  }

  function updateStats(){
    var total = vetRows.length;
    var draftedCount = vetRows.filter(function(r){ return drafted.has(r.key); }).length;
    var remaining = total - draftedCount;
    var flaggedRemaining = vetRows.filter(function(r){
      return !drafted.has(r.key) && DATA.veterans.find(function(v){return v.name===r.name;}).note;
    }).length;
    document.getElementById("statLine").innerHTML =
      "<b>" + remaining + "</b> remaining / " + total +
      '  &nbsp;·&nbsp;  <span class="flagged">' + flaggedRemaining + " flagged</span>";
    document.getElementById("vetCount").textContent = "(" + remaining + ")";
  }

  /* ---------- rookies ---------- */
  var rooWrap = document.getElementById("rooTiers");
  var rooSorted = DATA.rookies.slice().sort(function(a, b){ return a.rank - b.rank; });

  var rooRows = [];
  var table = document.createElement("table");
  var thead = document.createElement("thead");
  thead.innerHTML = '<tr><th class="rank">#</th><th class="name-cell">Player</th><th class="num">Val</th><th class="num">Projected</th></tr>';
  table.appendChild(thead);
  var tbody = document.createElement("tbody");
  rooSorted.forEach(function(m){
    var tr = document.createElement("tr");
    tr.dataset.name = m.name.toLowerCase();
    var key = zKey("r", m.name);
    if (drafted.has(key)) tr.classList.add("drafted");
    if (mine.has(key)) tr.classList.add("mine");
    tr.innerHTML =
      '<td class="rank"><span class="rankNum">' + m.rank + '</span>' +
        '<span class="mineStar" title="Mark as your pick">&#9733; mine</span></td>' +
      '<td class="name-cell"><span class="name">' + esc(m.name) + '</span></td>' +
      '<td class="num val">' + m.val.toFixed(2) + '</td>' +
      '<td class="num" style="font-family:var(--mono);font-size:12px;color:var(--text-dim)">' +
        'Pick ' + m.pick + ' · ' + m.pts + ' pts · ' + m.reb + ' reb · ' + m.ast + ' ast · ' + m.min + ' min</td>';
    var rowObj = {tr: tr, name: m.name, key: key, z: m.z, chartRow: null};
    makeRowActivatable(tr);
    tr.addEventListener("click", function(e){
      if (e.target.closest(".mineStar")) return; /* star has its own handler */
      setRowDrafted(rowObj, !drafted.has(key));
    });
    tr.querySelector(".mineStar").addEventListener("click", function(e){
      e.stopPropagation();
      toggleMine(rowObj);
    });
    tbody.appendChild(tr);
    rooRows.push(rowObj);
  });
  table.appendChild(tbody);
  rooWrap.appendChild(table);

  function updateRooStats(){
    var total = rooRows.length;
    var draftedCount = rooRows.filter(function(r){ return drafted.has(r.key); }).length;
    document.getElementById("statLineRoo").innerHTML = "<b>" + (total - draftedCount) + "</b> remaining / " + total;
    document.getElementById("rooCount").textContent = "(" + (total - draftedCount) + ")";
  }

  /* ---------- live draft sync (optional) ----------
     Polls drafted_live.json, written by scripts/live_draft_sync.py while a
     real Yahoo draft is live, and auto-marks any name it lists as drafted.
     Silently does nothing if the file doesn't exist yet or the page was
     opened as a file:// URL (fetch of local files is blocked there) -- this
     is a pure enhancement, never required for the board to work standalone. */
  var LIVE_POLL_MS = 5000;
  var liveSyncUnmatchedShown = new Set();

  function findRowByName(name){
    var lower = name.toLowerCase();
    for (var i = 0; i < vetRows.length; i++){ if (vetRows[i].name.toLowerCase() === lower) return vetRows[i]; }
    for (var j = 0; j < rooRows.length; j++){ if (rooRows[j].name.toLowerCase() === lower) return rooRows[j]; }
    return null;
  }

  function pollLiveDraft(){
    fetch("drafted_live.json", {cache: "no-store"}).then(function(res){
      return res.ok ? res.json() : null;
    }).then(function(data){
      if (!data) return;
      var newlyDrafted = [];
      (data.drafted || []).forEach(function(name){
        var row = findRowByName(name);
        if (row && !drafted.has(row.key)){
          setRowDrafted(row, true, {silent: true});
          newlyDrafted.push(name);
        }
      });
      if (newlyDrafted.length){
        showToast("Synced from Yahoo: " + newlyDrafted.join(", "), false);
      }
      (data.unmatched || []).forEach(function(name){
        if (!liveSyncUnmatchedShown.has(name)){
          liveSyncUnmatchedShown.add(name);
          showToast("Yahoo pick not found on board -- mark manually: " + name, false);
        }
      });
    }).catch(function(){ /* no sync script running -- the default, expected state */ });
  }
  setInterval(pollLiveDraft, LIVE_POLL_MS);
  pollLiveDraft();

  /* ---------- tabs ---------- */
  var tabs = document.querySelectorAll(".tab");
  tabs.forEach(function(t){
    t.addEventListener("click", function(){ switchTab(t.dataset.tab); });
  });

  /* ---------- keyboard-first drafting ----------
     "/" focuses search (unless already typing somewhere). Escape does
     double duty: an open expanded chart takes priority (collapse it
     first), search only clears once nothing is expanded -- the least
     surprising order, since the chart is the more "modal" of the two.
     Enter in the search box drafts the first non-drafted VISIBLE match in
     whichever tab is currently showing (auto-switch already put you on
     the right one), skipping already-drafted rows so a repeated search
     can't accidentally un-draft someone. Cmd/Ctrl+Z is a global backup for
     the toast's click-to-undo. */
  function draftTopVisibleMatch(){
    var activeIsVets = document.getElementById("vetsPane").style.display !== "none";
    var pool = activeIsVets ? vetRows : rooRows;
    for (var i = 0; i < pool.length; i++){
      var r = pool[i];
      if (!r.tr.classList.contains("hidden") && !drafted.has(r.key)){
        setRowDrafted(r, true);
        return;
      }
    }
  }

  searchEl.addEventListener("keydown", function(e){
    if (e.key === "Enter"){
      e.preventDefault();
      draftTopVisibleMatch();
    }
  });

  document.addEventListener("keydown", function(e){
    var tag = document.activeElement ? document.activeElement.tagName : "";
    var inField = tag === "INPUT" || tag === "TEXTAREA";

    if (e.key === "/" && !inField){
      e.preventDefault();
      searchEl.focus();
      return;
    }
    if (e.key === "Escape"){
      if (openChart){ e.preventDefault(); closeOpenChart(); return; }
      if (searchEl.value){ e.preventDefault(); searchEl.value = ""; applyFilter(); }
      return;
    }
    if ((e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z")){
      if (lastAction){ e.preventDefault(); undoLast(); }
    }
  });

  updateStats();
  updateRooStats();
  updatePositionalRanks();
  updateCliffMarkers();
  updateMineSummary();
  syncStickyOffset();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
