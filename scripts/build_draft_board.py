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
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "draft_board_2026_27.html"

Z_COLS = ["PTS_G", "REB_G", "AST_G", "ST_G", "BLK_G", "TO_G",
          "FG%_G", "FTM_G", "3PTM_G", "DD_G", "TD_G", "TECH_G"]
Z_LABELS = ["PTS", "REB", "AST", "ST", "BLK", "TO", "FG%", "FTM", "3PM", "DD", "TD", "TECH"]
# Categories excluded from tag generation (not from the expanded chart, which
# always shows all 12): TD is bimodal -- 105/130 players share its exact floor
# value (see the category-weighting GitHub issue filed 2026-08-15) -- so
# anyone above it reads as an extreme outlier and it dominates every strength
# tag. TO correlates with usage, so nearly every good player reads as weak at
# it -- true but not distinctive. TECH rides along with TD as part of the same
# low-signal "milestone" group. DD has the same "dominates by variance" effect
# as TD (its post-weight pool stdev, 0.71, is the largest of any category --
# see the per-column-normalization note below) without being bimodal, so it's
# excluded too. Verified by hand against 130 real players: including all four
# gives Jokic "+FG% TD", Wembanyama "+TD DD", and "-TO" on nearly every
# top-20 player; excluding them gives Wembanyama "+BLK REB", Harden
# "+AST FTM -FG%", Gobert "+BLK FG% -AST 3PM".
TAG_EXCLUDE = {"TO", "TD", "TECH", "DD"}
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

    def player_z(r) -> list[float]:
        return [round((float(r[c]) - col_mean[c]) / col_stdev[c], 3) if pd.notna(r[c]) else 0.0
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
        note = r["DATA_AVAILABILITY_NOTE"]
        note = "" if (isinstance(note, float) and math.isnan(note)) else str(note)
        z = player_z(r)
        vets.append({
            "rank": int(r["RANK"]),
            "name": r["PLAYER_NAME"],
            "pos": pos,
            "team": team,
            "val": round(float(r["TOTAL_VALUE"]) + VAL_DISPLAY_SHIFT, 3),
            "note": note,
            "noteShort": note_short(note),
            "z": z,
            "tags": player_tags(z),
            "stats": {
                "projected": player_projected(r),
                "actual": actual_2025_26.get(r["PLAYER_NAME"]),
            },
        })

    roos = []
    for _, r in rookies.iterrows():
        roos.append({
            "tier": r["TIER"],
            "name": r["PLAYER_NAME"],
            "pick": int(r["OVERALL_PICK"]),
            "val": round(float(r["TOTAL_VALUE"]) + VAL_DISPLAY_SHIFT, 3),
            "pts": round(float(r["PTS"]), 1),
            "reb": round(float(r["REB"]), 1),
            "ast": round(float(r["AST"]), 1),
            "min": round(float(r["MIN"]), 1),
        })

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
<style>
:root{
  --bg:#0a0c0f; --surface:#10141a; --surface-alt:#141a22; --surface-hover:#1a222c;
  --text:#e8e6df; --text-dim:#9aa3b2; --text-faint:#808a96;
  --accent:#d98e3b; --flag:#e0a83f; --drafted:#d97362;
  --pos-z:#4a8f6b; --neg-z:#d97362;
  --strength:#5aa37a; --weakness:#d9605a;
  --border:#1c222b; --border-strong:#2b333f;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --sans: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:var(--sans);}
body{-webkit-font-smoothing:antialiased;}
::selection{background:var(--accent);color:#0a0c0f;}
html{scrollbar-color:var(--border-strong) var(--bg);}
::-webkit-scrollbar{width:12px;height:12px;}
::-webkit-scrollbar-track{background:var(--bg);}
::-webkit-scrollbar-thumb{background:var(--border-strong);border:3px solid var(--bg);border-radius:0;}
::-webkit-scrollbar-thumb:hover{background:var(--text-faint);}

/* ---------- header / controls ---------- */
.topbar{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--border-strong);padding:0 14px;}
.tabs{display:flex;gap:22px;margin-bottom:0;border-bottom:1px solid var(--border);}
.tab{
  font-family:var(--sans);font-weight:700;font-size:12px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--text-dim);background:none;border:none;border-bottom:2px solid transparent;
  padding:12px 2px 10px;cursor:pointer;margin-top:8px;
}
.tab.active{color:var(--accent);border-bottom-color:var(--accent);}
.tab .count{font-family:var(--mono);font-weight:400;color:var(--text-faint);margin-left:6px;}
.tab.active .count{color:var(--text-dim);}

.searchRow{display:flex;align-items:center;gap:10px;padding:10px 0 0;}
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--border);}
.search{
  font-family:var(--sans);font-size:14px;color:var(--text);background:var(--surface);
  border:1px solid var(--border-strong);border-radius:0;padding:7px 10px;width:220px;
}
.search::placeholder{color:var(--text-faint);}
.search:focus{outline:1px solid var(--accent);outline-offset:0;border-color:var(--accent);}

.chips{display:flex;gap:1px;}
.chip{
  font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.04em;color:var(--text-dim);
  background:var(--surface);border:1px solid var(--border-strong);border-radius:0;
  padding:6px 10px;cursor:pointer;user-select:none;
}
.chip.on{color:var(--bg);background:var(--accent);border-color:var(--accent);}
.chip:focus-visible{outline:1px solid var(--accent);outline-offset:0;}

.sortSelect{
  font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.02em;color:var(--text-dim);
  background:var(--surface);border:1px solid var(--border-strong);border-radius:0;
  padding:6px 9px;cursor:pointer;
}

.stats{margin-left:auto;font-family:var(--mono);font-size:13px;color:var(--text-dim);white-space:nowrap;}
.stats b{color:var(--text);font-weight:700;}
.stats .flagged{color:var(--flag);}

/* undo/confirmation toast -- fires on every drafted-toggle (keyboard or
   click) so a fast multi-letter search-and-Enter always confirms WHO got
   marked, especially important when hide-drafted is on and the row
   vanishes instantly with no other visual trace. */
.toast{
  position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(8px);
  background:var(--surface-alt);border:1px solid var(--border-strong);color:var(--text);
  font-family:var(--mono);font-size:13px;padding:9px 16px;border-radius:0;cursor:pointer;
  opacity:0;pointer-events:none;transition:opacity .15s,transform .15s;z-index:50;
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}
.toast .hint{color:var(--text-faint);margin-left:8px;}

/* ---------- table ---------- */
.wrap{padding:0 14px 40px;}
table{width:100%;border-collapse:collapse;font-family:var(--sans);}
thead th{
  position:sticky;top:var(--topbar-h,87px);z-index:10;background:var(--bg);
  text-align:left;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-faint);padding:9px 8px 7px;border-bottom:1px solid var(--border-strong);
}
th.num,td.num{text-align:right;}
tbody tr{border-bottom:1px solid var(--border);cursor:pointer;}
tbody tr[tabindex]:focus-visible{outline:1px solid var(--accent);outline-offset:-1px;}
tbody tr:nth-child(even){background:var(--surface);}
tbody tr:hover{background:var(--surface-hover);}
tbody tr.hidden{display:none;}
td{padding:7px 8px;vertical-align:middle;font-size:13px;font-variant-numeric:tabular-nums;}
.rank{font-family:var(--mono);color:var(--text-dim);font-size:12px;font-weight:700;width:1%;font-variant-numeric:tabular-nums;cursor:pointer;padding:6px 8px;border-radius:0;text-align:center;}
.rank:hover,.rank:focus-visible{background:var(--surface-hover);color:var(--accent);}
.rank:focus-visible{outline:1px solid var(--accent);outline-offset:-1px;}
.rankHint{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--text-faint);margin-top:2px;white-space:nowrap;}
.name-cell{min-width:170px;}
.name{font-weight:700;font-size:13.5px;color:var(--text);}
.meta{font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-left:6px;}
.val{font-family:var(--mono);font-weight:700;font-size:13px;color:var(--accent);font-variant-numeric:tabular-nums;}

/* drafted state -- the signature: an executed order, not a fade.
   ">> FILLED" reads like a terminal confirming a trade went through. */
tr.drafted{background:var(--bg) !important;}
tr.drafted:hover{background:var(--surface) !important;}
tr.drafted .name{
  color:var(--text-faint);
  text-decoration:line-through;text-decoration-color:var(--drafted);text-decoration-thickness:1px;
}
tr.drafted .name::before{
  content:">> FILLED";
  color:var(--drafted);font-weight:700;font-size:10px;letter-spacing:.04em;
  margin-right:8px;text-decoration:none;display:inline-block;
}
tr.drafted .meta,tr.drafted .val{color:var(--text-faint);}
tr.drafted .tags{opacity:.25;}
tr.chart-row.dim .chart{opacity:.25;}
tr.drafted .noteInline{opacity:.35;}
tr.drafted .balanceStrip{opacity:.35;}
tr.drafted .rowGp{opacity:.35;}
tr.drafted .posRank{opacity:.35;}

/* availability flag -- readable at a glance, no click required (only 13/130
   rows carry one, so it doesn't add noise). Full note text lives in the
   expanded chart row (.chartNote below). */
.noteInline{font-family:var(--mono);font-size:11px;color:var(--flag);margin-left:6px;}

/* balance strip: 12 threshold-colored cells (same centered/scaled z the
   tags use, same ±0.75σ cutoff -- a cell colors if and only if that
   category would qualify as a tag, by construction). Blank/border means
   "typical" -- this is deliberately not a continuous heatmap, it shows
   only where a player is UNUSUAL. Fills the space right of tags. */
.rowRight{display:flex;align-items:center;width:100%;}
.rowMid{display:flex;align-items:center;gap:10px;margin-left:28px;white-space:nowrap;}
.posRank{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--accent);}
.rowGp{font-family:var(--mono);font-size:11.5px;color:var(--text-dim);}
.rowGp b{color:var(--text);font-weight:700;font-variant-numeric:tabular-nums;}

/* tier-cliff marker: a thin rule where the VAL gap to the previous
   undrafted player (in Value order) exceeds CLIFF_THRESHOLD -- live among
   undrafted players, Value-sort only (a category sort's row order isn't
   VAL order, so a VAL-gap marker there would land on arbitrary rows). */
tr.cliff{border-top:2px dashed var(--accent);}
.balanceStrip{display:flex;gap:1px;width:250px;margin-left:auto;flex:none;}
.balanceCell{flex:1;display:flex;flex-direction:column;align-items:center;}
.balanceCell .sw{width:100%;height:15px;border-radius:0;}
.balanceCell .l{font-family:var(--mono);font-size:8px;color:var(--text-faint);margin-top:2px;letter-spacing:-.03em;overflow:hidden;white-space:nowrap;}

/* strength/weakness tags: up to 2 green + 2 red pills per row, category
   name only -- click the row to see all 12 categories in the expanded
   chart below it. TD/TECH/TO are excluded from tag generation (see
   TAG_EXCLUDE in build_draft_board.py) but still appear in that chart. */
.tags{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-height:26px;}
.tag{
  font-family:var(--mono);font-size:14px;font-weight:700;letter-spacing:.02em;
  border-radius:0;padding:4px 9px;border:1px solid currentColor;
}
.tag.pos{color:var(--strength);background:color-mix(in srgb, var(--strength) 18%, transparent);}
.tag.neg{color:var(--weakness);background:color-mix(in srgb, var(--weakness) 18%, transparent);}
.tagLegend{display:flex;align-items:center;gap:12px;font-family:var(--mono);font-size:11px;font-weight:400;color:var(--text-dim);white-space:nowrap;text-transform:none;letter-spacing:0;}
.tagLegend .sw{display:inline-block;width:9px;height:9px;border-radius:1px;margin-right:5px;vertical-align:-1px;}
.tagLegend .sw.pos{background:var(--strength);}
.tagLegend .sw.neg{background:var(--weakness);}

/* expanded row: projected/actual per-game stat cards, then the category chart */
tr.chart-row td{padding:10px 8px 12px 34px;background:var(--surface);}
tr.chart-row.hidden{display:none;}
tr.chart-row:not(.open){display:none;}
.statBlockLabel,.chartLabel{
  font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;color:var(--text-faint);margin:2px 0 6px;
}
.chartNote{font-family:var(--mono);font-size:12px;color:var(--flag);margin-bottom:14px;}
.statRow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;}
.statCard{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-width:44px;background:var(--surface-alt);border-radius:0;border:1px solid var(--border);padding:6px 4px;
}
.statCard .v{font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text);font-variant-numeric:tabular-nums;}
.statCard .l{font-family:var(--mono);font-size:9px;color:var(--text-dim);margin-top:2px;letter-spacing:.03em;}
.statEmpty{font-family:var(--mono);font-size:12px;color:var(--text-faint);font-style:italic;margin-bottom:14px;}

/* per-player category chart: all 12 categories, one shared 0-baseline,
   per-column z-score normalization (same values as the tags), category
   label + numeric value under each bar, bar height clamped at ±3σ
   (the printed value is never clamped, only the bar). */
.chart{position:relative;display:flex;gap:2px;height:100px;}
.chart .baseline{position:absolute;left:0;right:0;top:32px;height:1px;background:var(--border-strong);}
.chart .col{position:relative;width:48px;flex:none;display:flex;flex-direction:column;align-items:center;}
.chart .barTrack{position:relative;width:100%;height:64px;}
.chart .bar{position:absolute;left:10px;right:10px;border-radius:0;}
.chart .bar.pos{background:var(--pos-z);bottom:50%;border-radius:2px 2px 0 0;}
.chart .bar.neg{background:var(--neg-z);top:50%;border-radius:0 0 2px 2px;}
.chart .label{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text-dim);margin-top:4px;}
.chart .value{font-family:var(--mono);font-size:9.5px;color:var(--text-faint);}

/* ---------- rookies ---------- */
.disclaimer{
  background:var(--surface-alt);border:1px solid var(--border-strong);
  color:var(--flag);font-family:var(--mono);font-size:12.5px;padding:10px 14px;margin:12px 0;border-radius:0;
}
.disclaimer::before{content:"[!] ";font-weight:700;}
.tier-block{margin:18px 0 8px;}
.tier-title{
  font-family:var(--sans);font-weight:800;font-size:13px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--accent);border-bottom:1px solid var(--border-strong);padding-bottom:5px;margin-bottom:2px;
}
.tier-title .n{color:var(--text-faint);font-weight:400;font-family:var(--mono);margin-left:8px;}

.empty{padding:30px 8px;color:var(--text-faint);font-family:var(--mono);font-size:13px;}

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
              <span class="sw pos"></span>strength ≥ +0.75σ
              <span class="sw neg"></span>weakness ≤ -0.75σ
              &nbsp;&nbsp;· click a row to see all 12 categories
            </div>
          </th>
        </tr>
      </thead>
      <tbody id="vetBody"></tbody>
    </table>
  </div>

  <div id="roosPane" style="display:none">
    <div class="disclaimer">Speculative: historical draft-slot production baselines, not real in-season data. Rookies sharing a draft-slot bucket share identical projected stats by construction — tiers, not ranks.</div>
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

  function loadDrafted(){
    try { return new Set(JSON.parse(localStorage.getItem(STORE_KEY) || "[]")); }
    catch(e){ return new Set(); }
  }
  function saveDrafted(set){
    localStorage.setItem(STORE_KEY, JSON.stringify(Array.from(set)));
  }
  var drafted = loadDrafted();

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
    saveDrafted(drafted);
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
    if (z >= BALANCE_STRONG) return "#5aa37a";
    if (z >= BALANCE_THRESHOLD) return "#8fc4a6";
    if (z <= -BALANCE_STRONG) return "#d9605a";
    if (z <= -BALANCE_THRESHOLD) return "#e59a92";
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
    var out = '<div class="statBlockLabel">Projected 2026-27 per game</div>' +
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

    var noteInline = v.noteShort ? '<span class="noteInline">' + esc(v.noteShort) + '</span>' : "";

    tr.innerHTML =
      '<td class="rank" tabindex="0" role="button" title="Click to toggle drafted">' + v.rank + '</td>' +
      '<td class="name-cell"><span class="name">' + esc(v.name) + '</span>' +
        '<span class="meta">' + esc(v.pos) + (v.team ? " · " + esc(v.team) : "") + '</span>' + noteInline + '</td>' +
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
      e.stopPropagation();
      setRowDrafted(rowObj, !drafted.has(key));
    });
    rankCell.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " "){
        e.preventDefault(); e.stopPropagation();
        setRowDrafted(rowObj, !drafted.has(key));
      }
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
     order) -- veterans only, rookies keep their tier grouping. */
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
  var TIER_ORDER = [];
  DATA.rookies.forEach(function(r){ if (TIER_ORDER.indexOf(r.tier) === -1) TIER_ORDER.push(r.tier); });

  var rooRows = [];
  TIER_ORDER.forEach(function(tier){
    var members = DATA.rookies.filter(function(r){ return r.tier === tier; });
    var block = document.createElement("div");
    block.className = "tier-block";
    block.innerHTML = '<div class="tier-title">' + esc(tier) + '<span class="n">' + members.length + ' players</span></div>';
    var table = document.createElement("table");
    var thead = document.createElement("thead");
    thead.innerHTML = '<tr><th class="rank">Pick</th><th class="name-cell">Player</th><th class="num">Val</th><th class="num">Projected</th></tr>';
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    members.forEach(function(m){
      var tr = document.createElement("tr");
      tr.dataset.name = m.name.toLowerCase();
      var key = zKey("r", m.name);
      if (drafted.has(key)) tr.classList.add("drafted");
      tr.innerHTML =
        '<td class="rank">#' + m.pick + '</td>' +
        '<td class="name-cell"><span class="name">' + esc(m.name) + '</span></td>' +
        '<td class="num val">' + m.val.toFixed(2) + '</td>' +
        '<td class="num" style="font-family:var(--mono);font-size:12px;color:var(--text-dim)">' +
          m.pts + ' pts · ' + m.reb + ' reb · ' + m.ast + ' ast · ' + m.min + ' min</td>';
      var rowObj = {tr: tr, name: m.name, key: key, chartRow: null};
      makeRowActivatable(tr);
      tr.addEventListener("click", function(){
        setRowDrafted(rowObj, !drafted.has(key));
      });
      tbody.appendChild(tr);
      rooRows.push(rowObj);
    });
    table.appendChild(tbody);
    block.appendChild(table);
    rooWrap.appendChild(block);
  });

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
  syncStickyOffset();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
