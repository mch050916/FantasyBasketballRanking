(function () {
  "use strict";

  var CATEGORIES = ["FGM", "FG%", "FTM", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF", "TECH", "DD", "TD"];

  // Must match each script's own DASHBOARD_RESULT_PREFIX exactly -- the one
  // line every tool prints, in addition to its normal human-readable report,
  // holding a structured summary a renderX() function turns into a themed
  // card. Nothing from the raw stream reaches the screen on a normal run.
  var DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__";

  // Backend chatter (cache loads, NBA API fetch/backfill progress, per-player
  // [skip] lines -- see data.py's cache helpers), filtered out of the
  // error-fallback text so an actual failure message isn't buried under it.
  var NOISE_PATTERNS = [
    /^\[skip\]/, /from cache:?/, /cached (for|to)/, /^Rebuilding .*cache/,
    /^Fetching /, /^No cache found/, /^This only runs once/,
    /^Cache missing .*backfilling/, /^Season schedule fetched:/,
  ];
  function isNoiseLine(line) {
    var trimmed = line.trim();
    return trimmed !== "" && NOISE_PATTERNS.some(function (re) { return re.test(trimmed); });
  }

  var ESCAPE_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  function esc(value) {
    return String(value).replace(/[&<>"]/g, function (c) { return ESCAPE_MAP[c]; });
  }

  // Descriptions are the same copy index.html's toolkit cards already use --
  // not re-written here, just reused where the task is explained a second time.
  var TOOLS = {
    punt_planner: {
      label: "Punt Planner", endpoint: "punt_planner",
      description: "Ranks which categories a roster is already losing most, and re-ranks the full player pool with one category's weight zeroed.",
      fields: [
        { name: "team", label: "Team", type: "team-select", required: true },
        { name: "punt", label: "Category to punt (optional)", type: "category-select" },
        { name: "show_players", label: "Players to show", type: "number", value: 15 },
      ],
    },
    find_trades: {
      label: "Trade Finder", endpoint: "find_trades",
      description: "Searches every 1-for-1 swap in the league for trades that improve both sides' expected categories won per week. Leave Team blank to search the whole league.",
      fields: [
        { name: "team", label: "Team (blank = whole league)", type: "team-select", required: false },
        { name: "max_value_gap", label: "Max value gap", type: "number", step: "0.01", value: 0.15 },
        { name: "sim_weeks", label: "Simulated weeks", type: "number", value: 2000 },
        { name: "top", label: "Top results", type: "number", value: 10 },
      ],
    },
    analyze_trade: {
      label: "Trade Analyzer", endpoint: "analyze_trade",
      description: "Full per-category before/after breakdown for one proposed trade — expected categories won per week, both sides, against the league field. Type player names to pick from the real pool.",
      fields: [
        { name: "team", label: "Your team", type: "team-select", required: true },
        { name: "partner", label: "Partner team", type: "team-select", required: true, excludeField: "team" },
        { name: "give", label: "Players you give (comma-separated)", type: "player-text", rosterFrom: "team" },
        { name: "get", label: "Players you get (comma-separated)", type: "player-text", rosterFrom: "partner" },
      ],
    },
    buy_low_sell_high: {
      label: "Buy Low / Sell High", endpoint: "buy_low_sell_high",
      description: "Diffs real in-season per-game performance against each player's preseason projection, weighted the same way the model values categories. Leave everything blank for the default view.",
      fields: [
        { name: "season", label: "Season (blank = current)", type: "text", placeholder: "e.g. 2025-26" },
        { name: "min_games", label: "Minimum games", type: "number", value: 5 },
        { name: "top", label: "Top results", type: "number", value: 15 },
      ],
    },
    schedule_strength: {
      label: "Schedule Strength", endpoint: "schedule_strength",
      description: "Real games-per-team for any fantasy week — who to stream, who to sit, straight from the live NBA schedule.",
      fields: [
        { name: "week", label: "Week (any date in it, blank = today)", type: "date" },
        { name: "team", label: "Team (optional)", type: "team-select" },
      ],
    },
  };

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function fieldInputHTML(field, meta) {
    var id = "f_" + field.name;
    if (field.type === "team-select") {
      var opts = (field.required ? "" : '<option value="">(none)</option>')
        + meta.teams.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + "</option>"; }).join("");
      return '<select id="' + id + '" name="' + field.name + '">' + opts + "</select>";
    }
    if (field.type === "category-select") {
      var copts = '<option value="">(worst category)</option>'
        + CATEGORIES.map(function (c) { return '<option value="' + c + '">' + c + "</option>"; }).join("");
      return '<select id="' + id + '" name="' + field.name + '">' + copts + "</select>";
    }
    if (field.type === "player-text") {
      var listId = id + "_list";
      var opts2 = meta.players.map(function (p) { return '<option value="' + esc(p) + '">'; }).join("");
      return '<input id="' + id + '" name="' + field.name + '" type="text" list="' + listId + '"'
        + ' placeholder="Comma-separated player names">'
        + '<datalist id="' + listId + '">' + opts2 + "</datalist>";
    }
    var attrs = ' type="' + field.type + '"';
    if (field.value !== undefined) attrs += ' value="' + esc(field.value) + '"';
    if (field.step) attrs += ' step="' + field.step + '"';
    if (field.placeholder) attrs += ' placeholder="' + esc(field.placeholder) + '"';
    return '<input id="' + id + '" name="' + field.name + '"' + attrs + ">";
  }

  function buildForm(tool, meta) {
    var form = document.getElementById("toolForm");
    form.innerHTML = tool.fields.map(function (f) {
      return '<div><label for="f_' + f.name + '">' + f.label + "</label>" + fieldInputHTML(f, meta)
        + (f.hint ? '<div class="hint">' + f.hint + "</div>" : "") + "</div>";
    }).join("")
      + '<div class="actions">'
      + '<button type="submit">Run</button>'
      + '<span class="status" id="status"><span class="dot"></span><span id="statusText">Idle</span></span>'
      + "</div>";
  }

  // A field's suggestions can depend on another field's current value --
  // "give" should only suggest players actually on "team"'s roster, and
  // "partner" should never offer whatever "team" is currently set to (the
  // self-trade default this was built to fix). Wired generically off the
  // field schema's `rosterFrom`/`excludeField` rather than hardcoded to
  // analyze_trade specifically, in case another tool needs the same shape.
  function datalistOptionsHTML(players) {
    return players.map(function (p) { return '<option value="' + esc(p) + '">'; }).join("");
  }

  function rebuildTeamSelectOptions(selectEl, teams, excludeValue, required) {
    var current = selectEl.value;
    var available = teams.filter(function (t) { return t !== excludeValue; });
    var opts = (required ? "" : '<option value="">(none)</option>')
      + available.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + "</option>"; }).join("");
    selectEl.innerHTML = opts;
    selectEl.value = available.indexOf(current) !== -1 ? current : (available[0] || "");
  }

  function wireFieldDependencies(tool, meta) {
    tool.fields.forEach(function (f) {
      if (f.rosterFrom) {
        var sourceEl = document.getElementById("f_" + f.rosterFrom);
        var listEl = document.getElementById("f_" + f.name + "_list");
        if (!sourceEl || !listEl) return;
        var updateRoster = function () {
          listEl.innerHTML = datalistOptionsHTML((meta.rosters && meta.rosters[sourceEl.value]) || []);
        };
        sourceEl.addEventListener("change", updateRoster);
        updateRoster();
      }
      if (f.excludeField) {
        var excludedEl = document.getElementById("f_" + f.excludeField);
        var selfEl = document.getElementById("f_" + f.name);
        if (!excludedEl || !selfEl) return;
        var updateOptions = function () {
          rebuildTeamSelectOptions(selfEl, meta.teams, excludedEl.value, !!f.required);
          // Cascades to anything scoped off THIS field (e.g. "get" is
          // rosterFrom:"partner" -- partner's value may have just changed).
          selfEl.dispatchEvent(new Event("change"));
        };
        excludedEl.addEventListener("change", updateOptions);
        updateOptions();
      }
    });
  }

  function setStatus(state, text) {
    var status = document.getElementById("status");
    status.className = "status" + (state ? " " + state : "");
    document.getElementById("statusText").textContent = text;
  }

  function collectFields(tool) {
    var fields = {};
    tool.fields.forEach(function (f) {
      var el = document.getElementById("f_" + f.name);
      if (el && el.value !== "") fields[f.name] = el.value;
    });
    return fields;
  }

  // \r redraws the current (last) line in place, same as a real terminal --
  // the server sends raw bytes with no line interpretation of its own (see
  // dashboard_server.py). Nothing from this buffer reaches the screen on a
  // normal run -- every tool now prints a DASHBOARD_RESULT_PREFIX JSON line
  // that a renderX() function turns into a themed card. The raw lines are
  // kept only as the fallback shown on an actual failure (bad input, a
  // crash) -- never as a visible "log," which the person asking for this
  // page explicitly did not want on the frontend at all.
  function bufferLines(state, text) {
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (ch === "\r") {
        state.lines[state.lines.length - 1] = "";
      } else if (ch === "\n") {
        state.lines.push("");
      } else {
        state.lines[state.lines.length - 1] += ch;
      }
    }
  }

  function tip(text) {
    return '<span class="tip" tabindex="0" data-tip="' + esc(text) + '">?</span>';
  }

  function sideHTML(label, side) {
    var cls = side.delta > 0.005 ? "up" : (side.delta < -0.005 ? "down" : "flat");
    var sign = side.delta >= 0 ? "+" : "";
    return '<div class="verdictTeam"><span class="verdictTeamName">' + esc(label) + "</span>"
      + '<span class="verdictTeamLine">' + side.before.toFixed(2) + " &rarr; " + side.after.toFixed(2)
      + ' <b class="' + cls + '">(' + sign + side.delta.toFixed(2) + ")</b></span></div>";
  }

  function categoryRowHTML(cat) {
    var cls = cat.delta > 0.005 ? "up" : (cat.delta < -0.005 ? "down" : "flat");
    var sign = cat.delta >= 0 ? "+" : "";
    return "<tr><td>" + esc(cat.category) + "</td>"
      + '<td class="num">' + cat.before.toFixed(2) + "</td>"
      + '<td class="num">' + cat.after.toFixed(2) + "</td>"
      + '<td class="num ' + cls + '">' + sign + cat.delta.toFixed(2) + "</td></tr>";
  }

  // A clear verdict is the whole point -- "should I do this trade" answered
  // in one glance, not buried in a 14-row table. +/-0.05 expected categories
  // won per week is a real, not noise-level, swing at this scale (the
  // printed CLI report's own worked examples this session mostly sat in the
  // -0.01 to +0.02 range for a single 1-for-1 swap).
  var VERDICT_THRESHOLD = 0.05;

  function analyzeTradeCardHTML(data) {
    var mine = data.teams[data.team];
    var theirs = data.teams[data.partner];
    var verdictClass = mine.delta >= VERDICT_THRESHOLD ? "favor"
      : mine.delta <= -VERDICT_THRESHOLD ? "against" : "even";
    var verdictLabel = verdictClass === "favor" ? "Favors you"
      : verdictClass === "against" ? "Unfavorable" : "Roughly even";
    var giveText = (data.give && data.give.length) ? data.give.join(", ") : "nothing";
    var getText = (data.get && data.get.length) ? data.get.join(", ") : "nothing";

    return '<div class="verdictHead">'
        + '<span class="verdictBadge ' + verdictClass + '">' + verdictLabel + "</span>"
        + '<span class="verdictSummary">' + esc(data.team) + " gives " + esc(giveText)
          + " &rarr; receives " + esc(getText)
          + tip("Favors you / Unfavorable kicks in at a ±" + VERDICT_THRESHOLD
            + " swing in expected categories won per week; smaller swings show as Roughly even.")
          + "</span>"
      + "</div>"
      + '<div class="verdictTeams">' + sideHTML(data.team, mine) + sideHTML(data.partner, theirs) + "</div>"
      + '<table class="verdictTable"><thead><tr><th>Category</th><th class="num">Before</th>'
        + '<th class="num">After</th><th class="num">&Delta;' + tip("Change in win share for this "
          + "category if the trade happens -- a tie counts as half a win, same as the headline number.")
          + "</th></tr></thead><tbody>"
        + mine.categories.map(categoryRowHTML).join("") + "</tbody></table>";
  }

  function puntPlannerCardHTML(data) {
    var catRows = data.categories.map(function (c) {
      return "<tr><td>" + esc(c.category)
        + (c.isPunt ? ' <span class="miniBadge punt">PUNT</span>' : "")
        + '</td><td class="num">' + c.share.toFixed(3) + "</td></tr>";
    }).join("");
    var playerRows = data.players.map(function (p) {
      return "<tr><td" + (p.mine ? ' class="playerMine"' : "") + ">" + esc(p.name) + "</td>"
        + '<td class="num">' + p.value.toFixed(2) + "</td>"
        + '<td class="num" style="color:var(--ink-faint);">' + p.was.toFixed(2) + "</td></tr>";
    }).join("");

    return '<div class="verdictHead"><span class="verdictBadge even">Punting ' + esc(data.punt) + "</span>"
        + '<span class="verdictSummary">' + esc(data.team) + " — expected categories won per week"
          + tip("How many of the league's scored categories this roster is projected to win in a "
            + "typical head-to-head week, simulated against the field.") + "</span></div>"
      + '<div class="verdictTeams oneCol"><div class="verdictTeam">'
        + '<span class="verdictTeamName">Expected / week</span>'
        + '<span class="verdictTeamLine">' + data.expected.toFixed(2) + " / " + data.n + "</span>"
        + "</div></div>"
      + '<p class="sectionLabel">Category breakdown, worst to best'
        + tip("Win rate against the league field, counting a tie as half a win. Lowest share first "
          + "-- your strongest punt candidates.") + "</p>"
      + '<table class="verdictTable"><thead><tr><th>Category</th><th class="num">Share</th></tr></thead>'
        + "<tbody>" + catRows + "</tbody></table>"
      + '<div class="verdictTeams oneCol" style="margin-top:16px;"><div class="verdictTeam">'
        + '<span class="verdictTeamName">Conceding ' + esc(data.punt) + " outright</span>"
        + '<span class="verdictTeamLine">' + data.remaining.expected.toFixed(2) + " / " + data.remaining.n
          + ' remaining categories <span class="sub">(avg ' + data.remaining.avgRemaining.toFixed(3)
          + "/cat, vs " + data.remaining.avgToday.toFixed(3) + "/cat today)</span></span></div></div>"
      + '<p class="sectionLabel">Top players re-ranked with ' + esc(data.punt) + " weighted to 0"
        + tip("Player value recomputed with the punted category's weight zeroed out -- who looks "
          + "good once you've given up on that category. Your own roster is highlighted.") + "</p>"
      + '<table class="verdictTable"><thead><tr><th>Player</th><th class="num">Val</th>'
        + '<th class="num">Was</th></tr></thead><tbody>' + playerRows + "</tbody></table>";
  }

  function findTradesCardHTML(data) {
    if (!data.trades.length) {
      return '<div class="verdictHead"><span class="verdictBadge even">No hits</span>'
          + '<span class="verdictSummary">Screened ' + data.screened + " value-fair swaps, none improved "
            + "both sides at this threshold.</span></div>"
        + '<p class="resultEmpty">Try a larger max value gap, or search the whole league instead '
          + "of one team.</p>";
    }
    var rows = data.trades.map(function (t) {
      return '<div class="tradeHit"><div class="tradeHitLine">' + esc(t.teamA) + " gives " + esc(t.give)
          + " &harr; " + esc(t.teamB) + " gives " + esc(t.get) + "</div>"
        + '<div class="tradeHitDeltas"><span>' + esc(t.teamA) + " <b>+" + t.deltaA.toFixed(3) + "</b> cats/wk</span>"
          + "<span>" + esc(t.teamB) + " <b>+" + t.deltaB.toFixed(3) + "</b> cats/wk</span></div></div>";
    }).join("");

    return '<div class="verdictHead"><span class="verdictBadge favor">' + data.trades.length
        + " mutually-improving</span>"
        + '<span class="verdictSummary">Screened ' + data.screened + " value-fair swaps (gap &le; "
          + data.maxValueGap + ", " + data.simWeeks + " weeks/opponent)"
          + tip("\"Value-fair\" means both players are within the max value gap in overall ranked "
            + "value -- not a judgment on whether the trade is good. cats/wk is the change in expected "
            + "categories won per week for that team if the trade happens.") + "</span></div>"
      + rows
      + '<p class="resultEmpty" style="margin-top:12px;">Screened at ' + data.simWeeks + " weeks/opponent "
        + "for speed -- confirm any of these with Trade Analyzer's full precision before proposing it.</p>";
  }

  function buyLowSellHighCardHTML(data) {
    function rows(list) {
      return list.map(function (p) {
        return "<tr><td>" + esc(p.name) + '</td><td class="num">' + (p.score >= 0 ? "+" : "")
          + p.score.toFixed(3) + '</td><td class="num" style="color:var(--ink-faint);">' + p.gp + " GP</td></tr>";
      }).join("");
    }
    if (!data.count) {
      return '<div class="verdictHead"><span class="verdictBadge even">No data yet</span>'
        + '<span class="verdictSummary">No players with &ge; ' + data.minGames + " games in "
          + esc(data.season) + " yet.</span></div>";
    }
    var scoreTip = tip("Weighted average deviation from this player's preseason projection, in the "
      + "categories the model values most. Positive = outperforming (sell high), negative = "
      + "underperforming (buy low).");
    return '<div class="verdictHead"><span class="verdictBadge even">' + data.count + " players</span>"
        + '<span class="verdictSummary">&ge; ' + data.minGames + " games in " + esc(data.season)
          + (data.degraded ? ' <span class="miniBadge" style="color:var(--weakness);'
            + 'border-color:var(--weakness);">DEGRADED FETCH</span>' : "") + "</span></div>"
      + '<div class="verdictTeams"><div class="verdictTeam">'
        + '<span class="verdictTeamName">Sell high' + scoreTip + "</span>"
        + '<table class="verdictTable"><tbody>' + rows(data.sellHigh) + "</tbody></table></div>"
        + '<div class="verdictTeam"><span class="verdictTeamName">Buy low' + scoreTip + "</span>"
        + '<table class="verdictTable"><tbody>' + rows(data.buyLow) + "</tbody></table></div></div>";
  }

  function scheduleStrengthCardHTML(data) {
    var teamRows = data.teams.map(function (t) {
      return "<tr><td>" + esc(t.team) + '</td><td class="num">' + t.games + "</td></tr>";
    }).join("");
    var html = '<div class="verdictHead"><span class="verdictBadge even">' + esc(data.season) + "</span>"
        + '<span class="verdictSummary">Games per team — week of ' + esc(data.weekOf)
          + tip("More games this week means more raw counting-stat opportunity for that team's "
            + "players -- a real streaming/start-sit signal a full-season ranking can't capture.")
          + "</span></div>"
      + '<table class="verdictTable"><thead><tr><th>Team</th><th class="num">Games</th></tr></thead>'
        + "<tbody>" + teamRows + "</tbody></table>";
    if (data.roster) {
      var rosterRows = data.roster.players.map(function (p) {
        return "<tr><td>" + esc(p.name) + '</td><td class="num">' + esc(p.nbaTeam || "?")
          + '</td><td class="num">' + p.games + "</td></tr>";
      }).join("");
      html += '<p class="sectionLabel">' + esc(data.roster.team) + "'s roster this week</p>"
        + '<table class="verdictTable"><thead><tr><th>Player</th><th class="num">Team</th>'
          + '<th class="num">Games</th></tr></thead><tbody>' + rosterRows + "</tbody></table>";
    }
    return html;
  }

  var CARD_RENDERERS = {
    analyze_trade: analyzeTradeCardHTML,
    punt_planner: puntPlannerCardHTML,
    find_trades: findTradesCardHTML,
    buy_low_sell_high: buyLowSellHighCardHTML,
    schedule_strength: scheduleStrengthCardHTML,
  };

  function renderResult(data) {
    var result = document.getElementById("result");
    var renderer = data && CARD_RENDERERS[data.kind];
    result.innerHTML = renderer ? renderer(data) : "";
  }

  function renderLoading() {
    document.getElementById("result").innerHTML =
      '<div class="resultLoading"><span class="dot"></span>Running…</div>';
  }

  // Only reached on an actual failure (bad input, a crash, or a malformed/
  // missing result line) -- the noise filter keeps a wall of per-player
  // [skip] lines from swamping whatever real error message is in there.
  function renderError(rawText) {
    var lines = rawText.split("\n").filter(function (line) { return !isNoiseLine(line); });
    var text = lines.join("\n").replace(/\[exit code: \d+\]\s*$/, "").trim();
    document.getElementById("result").innerHTML =
      '<p class="resultError">' + esc(text || "Something went wrong.") + "</p>";
  }

  async function runTool(tool, fields) {
    renderLoading();
    var state = { lines: [""] };
    setStatus("running", "Running…");

    var res = await fetch("/api/run/" + tool.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });

    if (!res.ok) {
      renderError(await res.text());
      setStatus(res.status === 409 ? "running" : "error",
        res.status === 409 ? "Busy — try again shortly" : "Failed to start");
      return;
    }

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      bufferLines(state, decoder.decode(chunk.value, { stream: true }));
    }

    var resultLine = state.lines.find(function (line) {
      return line.indexOf(DASHBOARD_RESULT_PREFIX) === 0;
    });
    var fullText = state.lines.join("\n");
    var exitMatch = fullText.match(/\[exit code: (\d+)\]\s*$/);
    var ok = exitMatch && exitMatch[1] === "0";

    var parsed = null;
    if (resultLine) {
      try {
        parsed = JSON.parse(resultLine.slice(DASHBOARD_RESULT_PREFIX.length));
      } catch (e) {
        parsed = null;
      }
    }

    if (ok && parsed) {
      renderResult(parsed);
      setStatus("done", "Done");
    } else if (ok) {
      // Exited clean but printed no structured result -- shouldn't happen
      // for a known tool, but show what it actually said rather than a
      // silently empty card.
      renderError(fullText);
      setStatus("done", "Finished");
    } else {
      renderError(fullText);
      setStatus("error", exitMatch ? "Exited with code " + exitMatch[1] : "Failed");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toolKey = qs("tool");
    var tool = TOOLS[toolKey];
    if (!tool) {
      document.getElementById("toolTitle").textContent = "Unknown tool";
      return;
    }
    document.getElementById("toolTitle").textContent = tool.label;
    document.getElementById("toolLede").textContent = tool.description || "";
    document.title = "DURANT — " + tool.label;

    fetch("/api/meta").then(function (r) {
      if (!r.ok) throw new Error("Server returned " + r.status);
      return r.json();
    }).then(function (meta) {
      buildForm(tool, meta);
      wireFieldDependencies(tool, meta);
      document.getElementById("toolForm").addEventListener("submit", function (e) {
        e.preventDefault();
        var button = e.target.querySelector("button");
        button.disabled = true;
        runTool(tool, collectFields(tool)).finally(function () { button.disabled = false; });
      });
    }).catch(function (err) {
      document.getElementById("toolForm").innerHTML = "";
      renderError("Could not load team/player data: " + err.message +
        "\n\nIs the server running? Start it with: python scripts/serve_dashboard.py");
    });
  });
})();
