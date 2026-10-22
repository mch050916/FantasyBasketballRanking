(function () {
  "use strict";

  var CATEGORIES = ["FGM", "FG%", "FTM", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF", "TECH", "DD", "TD"];

  // Must match dashboard_server.py's DASHBOARD_RESULT_PREFIX exactly -- the
  // one line a tool (currently only analyze_trade.py) can print, in
  // addition to its normal human-readable report, for a structured verdict
  // instead of parsing aligned text. Filtered out of the visible console.
  var DASHBOARD_RESULT_PREFIX = "__DASHBOARD_RESULT__";

  // Backend chatter (cache loads, NBA API fetch/backfill progress, per-player
  // [skip] lines -- see data.py's cache helpers) vs. the tool's actual result
  // (rankings, trade lists, schedule tables -- each script's own print()
  // calls). Tucked into the collapsed "Backend log" disclosure instead of
  // drowning the result a person actually asked for.
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
  // dashboard_server.py), so this is the one place that logic lives. A
  // completed line starting with DASHBOARD_RESULT_PREFIX is structured data
  // for renderVerdict, not something a person reading the console should see.
  function appendToConsole(state, text) {
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
    var shown = state.lines.filter(function (line) {
      return line.indexOf(DASHBOARD_RESULT_PREFIX) !== 0;
    });
    var resultLines = shown.filter(function (line) { return !isNoiseLine(line); });
    var logLines = shown.filter(isNoiseLine);

    var output = document.getElementById("output");
    output.textContent = resultLines.join("\n");
    output.scrollTop = output.scrollHeight;

    var log = document.getElementById("log");
    var logBody = document.getElementById("log-body");
    log.className = logLines.length ? "show" : "";
    document.getElementById("log-summary").textContent =
      "Backend log (" + logLines.length + (logLines.length === 1 ? " line)" : " lines)");
    logBody.textContent = logLines.join("\n");
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

  function renderVerdict(data) {
    var card = document.getElementById("verdict");
    if (!data) {
      card.className = "card verdict";
      card.innerHTML = "";
      return;
    }

    var mine = data.teams[data.team];
    var theirs = data.teams[data.partner];
    var verdictClass = mine.delta >= VERDICT_THRESHOLD ? "favor"
      : mine.delta <= -VERDICT_THRESHOLD ? "against" : "even";
    var verdictLabel = verdictClass === "favor" ? "Favors you"
      : verdictClass === "against" ? "Unfavorable" : "Roughly even";
    var giveText = (data.give && data.give.length) ? data.give.join(", ") : "nothing";
    var getText = (data.get && data.get.length) ? data.get.join(", ") : "nothing";

    card.className = "card verdict show";
    card.innerHTML =
      '<div class="verdictHead">'
        + '<span class="verdictBadge ' + verdictClass + '">' + verdictLabel + "</span>"
        + '<span class="verdictSummary">' + esc(data.team) + " gives " + esc(giveText)
          + " &rarr; receives " + esc(getText) + "</span>"
      + "</div>"
      + '<div class="verdictTeams">' + sideHTML(data.team, mine) + sideHTML(data.partner, theirs) + "</div>"
      + '<table class="verdictTable"><thead><tr><th>Category</th><th class="num">Before</th>'
        + '<th class="num">After</th><th class="num">&Delta;</th></tr></thead><tbody>'
        + mine.categories.map(categoryRowHTML).join("") + "</tbody></table>";
  }

  async function runTool(tool, fields) {
    var output = document.getElementById("output");
    output.textContent = "";
    var log = document.getElementById("log");
    log.className = "";
    log.open = false;
    document.getElementById("log-body").textContent = "";
    renderVerdict(null);
    var state = { lines: [""] };
    setStatus("running", "Running…");

    var res = await fetch("/api/run/" + tool.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });

    if (!res.ok) {
      output.textContent = await res.text();
      setStatus(res.status === 409 ? "running" : "error",
        res.status === 409 ? "Busy — try again shortly" : "Failed to start");
      return;
    }

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      appendToConsole(state, decoder.decode(result.value, { stream: true }));
    }

    var resultLine = state.lines.find(function (line) {
      return line.indexOf(DASHBOARD_RESULT_PREFIX) === 0;
    });
    if (resultLine) {
      try {
        renderVerdict(JSON.parse(resultLine.slice(DASHBOARD_RESULT_PREFIX.length)));
      } catch (e) {
        // Malformed/truncated result line -- leave the verdict card hidden
        // rather than show something misleading; the raw report is still
        // fully visible in the console either way.
      }
    }

    var fullText = state.lines.join("\n");
    var exitMatch = fullText.match(/\[exit code: (\d+)\]\s*$/);
    if (exitMatch && exitMatch[1] === "0") {
      setStatus("done", "Done");
    } else if (exitMatch) {
      setStatus("error", "Exited with code " + exitMatch[1]);
    } else {
      setStatus("done", "Finished");
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
      document.getElementById("output").textContent =
        "Could not load team/player data: " + err.message +
        "\n\nIs the server running? Start it with: python scripts/serve_dashboard.py";
    });
  });
})();
