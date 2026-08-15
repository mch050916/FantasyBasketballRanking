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
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "draft_board_2026_27.html"

Z_COLS = ["PTS_G", "REB_G", "AST_G", "ST_G", "BLK_G", "TO_G",
          "FG%_G", "FTM_G", "3PTM_G", "DD_G", "TD_G", "TECH_G"]
Z_LABELS = ["PTS", "REB", "AST", "ST", "BLK", "TO", "FG%", "FTM", "3PM", "DD", "TD", "TECH"]


def build_data() -> dict:
    rankings = pd.read_csv(REPO_ROOT / "durant_rankings_2026_27.csv")
    rookies = pd.read_csv(REPO_ROOT / "durant_rankings_rookies_2026_27.csv")

    pos_lookup: dict[str, tuple[str, str]] = {}
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

    vets = []
    for _, r in rankings.iterrows():
        pos, team = pos_lookup.get(r["PLAYER_NAME"], ("", ""))
        note = r["DATA_AVAILABILITY_NOTE"]
        note = "" if (isinstance(note, float) and math.isnan(note)) else str(note)
        vets.append({
            "rank": int(r["RANK"]),
            "name": r["PLAYER_NAME"],
            "pos": pos,
            "team": team,
            "val": round(float(r["TOTAL_VALUE"]), 3),
            "note": note,
            "z": [round(float(r[c]), 3) if pd.notna(r[c]) else 0.0 for c in Z_COLS],
        })

    roos = []
    for _, r in rookies.iterrows():
        roos.append({
            "tier": r["TIER"],
            "name": r["PLAYER_NAME"],
            "pick": int(r["OVERALL_PICK"]),
            "val": round(float(r["TOTAL_VALUE"]), 3),
            "pts": round(float(r["PTS"]), 1),
            "reb": round(float(r["REB"]), 1),
            "ast": round(float(r["AST"]), 1),
            "min": round(float(r["MIN"]), 1),
        })

    return {"zLabels": Z_LABELS, "veterans": vets, "rookies": roos}


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
  --bg:#12151a; --surface:#1a1f26; --surface-alt:#20262f; --surface-hover:#262d38;
  --text:#e9e6de; --text-dim:#8890a0; --text-faint:#5b6270;
  --accent:#d98e3b; --flag:#e8b34d; --drafted:#b5432e;
  --pos-z:#4fa3c7; --neg-z:#c77b4f;
  --border:#2a313b; --border-strong:#38414d;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:var(--sans);}
body{-webkit-font-smoothing:antialiased;}
::selection{background:var(--accent);color:#12151a;}

/* ---------- header / controls ---------- */
.topbar{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--border-strong);padding:10px 14px 0;}
.tabs{display:flex;gap:2px;margin-bottom:8px;}
.tab{
  font-family:var(--sans);font-weight:800;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--text-dim);background:var(--surface);border:1px solid var(--border);border-bottom:none;
  padding:8px 16px;cursor:pointer;border-radius:4px 4px 0 0;
}
.tab.active{color:var(--accent);background:var(--surface-alt);border-color:var(--border-strong);}
.tab .count{font-family:var(--mono);font-weight:400;color:var(--text-faint);margin-left:6px;}
.tab.active .count{color:var(--text-dim);}

.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--border);}
.search{
  font-family:var(--sans);font-size:14px;color:var(--text);background:var(--surface);
  border:1px solid var(--border-strong);border-radius:4px;padding:7px 10px;width:220px;
}
.search::placeholder{color:var(--text-faint);}
.search:focus{outline:2px solid var(--accent);outline-offset:1px;}

.chips{display:flex;gap:4px;}
.chip{
  font-family:var(--mono);font-size:12px;font-weight:600;color:var(--text-dim);
  background:var(--surface);border:1px solid var(--border-strong);border-radius:3px;
  padding:5px 9px;cursor:pointer;user-select:none;
}
.chip.on{color:var(--bg);background:var(--accent);border-color:var(--accent);}
.chip:focus-visible{outline:2px solid var(--accent);outline-offset:1px;}

.stats{margin-left:auto;font-family:var(--mono);font-size:13px;color:var(--text-dim);white-space:nowrap;}
.stats b{color:var(--text);font-weight:700;}
.stats .flagged{color:var(--flag);}

/* ---------- table ---------- */
.wrap{padding:0 14px 40px;}
table{width:100%;border-collapse:collapse;font-family:var(--sans);}
thead th{
  position:sticky;top:var(--topbar-h,87px);z-index:10;background:var(--bg);
  text-align:left;font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.06em;
  text-transform:uppercase;color:var(--text-faint);padding:8px 8px 6px;border-bottom:1px solid var(--border-strong);
}
th.num,td.num{text-align:right;}
tbody tr{border-bottom:1px solid var(--border);cursor:pointer;}
tbody tr[tabindex]:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;}
tbody tr:nth-child(even){background:var(--surface);}
tbody tr:hover{background:var(--surface-hover);}
tbody tr.hidden{display:none;}
td{padding:6px 8px;vertical-align:middle;font-size:13px;}
.rank{font-family:var(--mono);color:var(--text-faint);font-size:12px;width:1%;font-variant-numeric:tabular-nums;}
.name-cell{min-width:170px;}
.name{font-weight:600;font-size:14px;color:var(--text);}
.meta{font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-left:6px;}
.val{font-family:var(--mono);font-weight:700;font-size:13px;font-variant-numeric:tabular-nums;}

/* drafted state -- the signature: an inked strike, not a fade */
tr.drafted{background:var(--bg) !important;}
tr.drafted:hover{background:var(--surface) !important;}
tr.drafted .name{
  color:var(--text-faint);
  text-decoration:line-through;text-decoration-color:var(--drafted);text-decoration-thickness:2px;
}
tr.drafted .meta,tr.drafted .val{color:var(--text-faint);}
tr.drafted .zbars{opacity:.25;}
tr.drafted .note-badge{opacity:.35;}

/* availability flag */
.note-badge{
  display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--flag);
  margin-left:6px;cursor:pointer;vertical-align:middle;position:relative;top:-1px;
}
.note-row{display:none;}
.note-row.open{display:table-row;}
.note-row td{
  padding:2px 8px 8px 34px;font-family:var(--mono);font-size:11.5px;color:var(--flag);
  border-bottom:1px solid var(--border);background:var(--surface);
}

/* z-score profile: 12 tiny diverging bars per row */
/* One continuous strip per player -- a silhouette, not 12 mini-charts.
   --zslot is the per-category column width; the same repeating band
   pattern is painted behind both the header labels and every row's bars
   so a column can be traced straight down without counting. */
:root{ --zslot: 24px; --zcols: 12; }
.zbars{
  position:relative;height:26px;width:calc(var(--zslot) * var(--zcols));
  background:var(--surface-alt);border-radius:3px;overflow:hidden;flex:none;
  background-image:repeating-linear-gradient(to right,
    transparent 0, transparent var(--zslot),
    rgba(255,255,255,.035) var(--zslot), rgba(255,255,255,.035) calc(var(--zslot) * 2));
}
.zbars .baseline{position:absolute;left:0;right:0;top:50%;height:1px;background:var(--border-strong);}
.zbars .bar{position:absolute;width:calc(var(--zslot) - 3px);margin-left:1.5px;}
.zbars .bar.pos{background:var(--pos-z);bottom:50%;}
.zbars .bar.neg{background:var(--neg-z);top:50%;}
.zhead{
  display:flex;width:calc(var(--zslot) * var(--zcols));
  background-image:repeating-linear-gradient(to right,
    transparent 0, transparent var(--zslot),
    rgba(255,255,255,.035) var(--zslot), rgba(255,255,255,.035) calc(var(--zslot) * 2));
}
.zhead span{width:var(--zslot);font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:-.02em;color:var(--text-dim);text-align:center;overflow:hidden;}
.zlegend{display:flex;align-items:center;gap:14px;margin-left:16px;font-family:var(--mono);font-size:11px;color:var(--text-dim);white-space:nowrap;}
.zlegend .sw{display:inline-block;width:9px;height:9px;border-radius:1px;margin-right:5px;vertical-align:-1px;}
.zlegend .sw.pos{background:var(--pos-z);}
.zlegend .sw.neg{background:var(--neg-z);}
.zlegend .scale{color:var(--text);font-weight:600;}

/* ---------- rookies ---------- */
.disclaimer{
  background:#2a2114;border:1px solid var(--flag);border-left:4px solid var(--flag);
  color:var(--flag);font-family:var(--mono);font-size:12.5px;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0;
}
.tier-block{margin:18px 0 8px;}
.tier-title{
  font-family:var(--sans);font-weight:800;font-size:13px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--accent);border-bottom:1px solid var(--border-strong);padding-bottom:5px;margin-bottom:2px;
}
.tier-title .n{color:var(--text-faint);font-weight:400;font-family:var(--mono);margin-left:8px;}

.empty{padding:30px 8px;color:var(--text-faint);font-family:var(--mono);font-size:13px;}

@media (max-width:640px){
  .search{width:150px;}
  .zbars{display:none;}
  .stats{width:100%;order:10;margin-left:0;}
}
</style>
</head>
<body>

<div class="topbar">
  <div class="tabs">
    <button class="tab active" data-tab="vets">Veterans <span class="count" id="vetCount"></span></button>
    <button class="tab" data-tab="roos">Rookies <span class="count" id="rooCount"></span></button>
  </div>
  <div class="controls" id="vetControls">
    <input class="search" id="search" type="text" placeholder="Search name…" autocomplete="off">
    <div class="chips" id="posChips"></div>
    <div class="stats" id="statLine"></div>
  </div>
  <div class="controls" id="rooControls" style="display:none">
    <input class="search" id="searchRoo" type="text" placeholder="Search name…" autocomplete="off">
    <div class="stats" id="statLineRoo"></div>
  </div>
</div>

<div class="wrap">
  <div id="vetsPane">
    <table>
      <thead>
        <tr>
          <th class="rank">#</th>
          <th class="name-cell">Player</th>
          <th class="num">Val</th>
          <th>
            <div style="display:flex;align-items:center;">
              <div class="zhead" id="zHeadRow"></div>
              <div class="zlegend" id="zLegend"></div>
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

  /* ---------- z-score profile strip: one silhouette per player, not 12 mini-charts ---------- */
  var Z_SCALE = 1.6; /* z magnitude that fills a full half-strip -- also drives the legend text */
  var ZSLOT = 24;
  function zBarsHTML(zArr){
    var out = '<span class="baseline"></span>';
    for (var i = 0; i < zArr.length; i++){
      var z = zArr[i];
      var pct = Math.max(0, Math.min(50, Math.abs(z) / Z_SCALE * 50));
      var cls = z >= 0 ? "pos" : "neg";
      var title = Z_LABELS[i] + " " + (z >= 0 ? "+" : "") + z.toFixed(2);
      out += '<span class="bar ' + cls + '" title="' + title + '" style="left:' + (i * ZSLOT) + 'px;height:' + pct + '%"></span>';
    }
    return out;
  }

  var zHead = "";
  for (var i = 0; i < Z_LABELS.length; i++){
    zHead += "<span>" + Z_LABELS[i].slice(0,3) + "</span>";
  }
  document.getElementById("zHeadRow").innerHTML = zHead;
  document.getElementById("zLegend").innerHTML =
    '<span class="sw pos"></span>above avg &nbsp;&nbsp;<span class="sw neg"></span>below avg' +
    ' &nbsp;&nbsp;<span class="scale">· full-height bar = ' + Z_SCALE.toFixed(1) + ' std. dev. from the pool average</span>';

  /* ---------- veterans table ---------- */
  var vetBody = document.getElementById("vetBody");
  var vetRows = [];

  DATA.veterans.forEach(function(v){
    var tr = document.createElement("tr");
    tr.dataset.name = v.name.toLowerCase();
    tr.dataset.pos = v.pos;
    var key = zKey("v", v.name);
    if (drafted.has(key)) tr.classList.add("drafted");

    var noteBadge = v.note ? '<span class="note-badge" title="' + esc(v.note) + '"></span>' : "";

    tr.innerHTML =
      '<td class="rank">' + v.rank + '</td>' +
      '<td class="name-cell"><span class="name">' + esc(v.name) + '</span>' +
        '<span class="meta">' + esc(v.pos) + (v.team ? " · " + esc(v.team) : "") + '</span>' + noteBadge + '</td>' +
      '<td class="num val">' + v.val.toFixed(2) + '</td>' +
      '<td><div class="zbars">' + zBarsHTML(v.z) + '</div></td>';

    var noteRow = null;
    if (v.note){
      noteRow = document.createElement("tr");
      noteRow.className = "note-row";
      var td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = "⚠ " + v.note;
      noteRow.appendChild(td);
    }

    makeRowActivatable(tr);
    tr.addEventListener("click", function(e){
      if (e.target.classList.contains("note-badge")){
        if (noteRow) noteRow.classList.toggle("open");
        return;
      }
      if (drafted.has(key)) { drafted.delete(key); tr.classList.remove("drafted"); }
      else { drafted.add(key); tr.classList.add("drafted"); }
      saveDrafted(drafted);
      updateStats();
    });

    vetBody.appendChild(tr);
    if (noteRow) vetBody.appendChild(noteRow);
    vetRows.push({tr: tr, name: v.name, pos: v.pos, key: key});
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

  var searchEl = document.getElementById("search");
  searchEl.addEventListener("input", applyFilter);

  function applyFilter(){
    var q = searchEl.value.trim().toLowerCase();
    vetRows.forEach(function(r){
      var matchName = !q || r.name.toLowerCase().indexOf(q) !== -1;
      var matchPos = activePos.size === 0 || activePos.has(r.pos);
      var show = matchName && matchPos;
      r.tr.classList.toggle("hidden", !show);
      var nr = r.tr.nextElementSibling;
      if (nr && nr.classList.contains("note-row")){
        nr.classList.toggle("hidden", !show);
        if (!show) nr.classList.remove("open"); /* .open would otherwise outrank .hidden */
      }
    });
    updateStats();
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
      makeRowActivatable(tr);
      tr.addEventListener("click", function(){
        if (drafted.has(key)) { drafted.delete(key); tr.classList.remove("drafted"); }
        else { drafted.add(key); tr.classList.add("drafted"); }
        saveDrafted(drafted);
        updateRooStats();
      });
      tbody.appendChild(tr);
      rooRows.push({tr: tr, name: m.name, key: key});
    });
    table.appendChild(tbody);
    block.appendChild(table);
    rooWrap.appendChild(block);
  });

  var searchRoo = document.getElementById("searchRoo");
  searchRoo.addEventListener("input", function(){
    var q = searchRoo.value.trim().toLowerCase();
    rooRows.forEach(function(r){
      r.tr.classList.toggle("hidden", !(!q || r.name.toLowerCase().indexOf(q) !== -1));
    });
  });

  function updateRooStats(){
    var total = rooRows.length;
    var draftedCount = rooRows.filter(function(r){ return drafted.has(r.key); }).length;
    document.getElementById("statLineRoo").innerHTML = "<b>" + (total - draftedCount) + "</b> remaining / " + total;
    document.getElementById("rooCount").textContent = "(" + (total - draftedCount) + ")";
  }

  /* ---------- tabs ---------- */
  var tabs = document.querySelectorAll(".tab");
  tabs.forEach(function(t){
    t.addEventListener("click", function(){
      tabs.forEach(function(x){ x.classList.remove("active"); });
      t.classList.add("active");
      var isVets = t.dataset.tab === "vets";
      document.getElementById("vetsPane").style.display = isVets ? "" : "none";
      document.getElementById("roosPane").style.display = isVets ? "none" : "";
      document.getElementById("vetControls").style.display = isVets ? "" : "none";
      document.getElementById("rooControls").style.display = isVets ? "none" : "";
      syncStickyOffset();
    });
  });

  updateStats();
  updateRooStats();
  syncStickyOffset();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
