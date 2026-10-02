---
name: DURANT Draft Board — Trading-Floor Terminal
description: A Bloomberg-terminal-style, single-file offline draft-day tool for one operator scanning ranked fantasy basketball players under pick-clock pressure.
colors:
  bg: "#0a0c0f"
  surface: "#10141a"
  surface-alt: "#141a22"
  surface-hover: "#1a222c"
  text: "#e8e6df"
  text-dim: "#9aa3b2"
  text-faint: "#808a96"
  accent: "#d98e3b"
  flag: "#e0a83f"
  drafted: "#d97362"
  pos-z: "#4a8f6b"
  neg-z: "#d97362"
  strength: "#5aa37a"
  weakness: "#d9605a"
  border: "#1c222b"
  border-strong: "#2b333f"
typography:
  mono:
    fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "normal"
    letterSpacing: "normal"
  label:
    fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.08em"
  wordmark:
    fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "0.14em"
  tab:
    fontFamily: 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "0.1em"
rounded:
  all: "0px"
spacing:
  xs: "2px"
  sm: "6px"
  md: "9px"
  lg: "14px"
  xl: "22px"
components:
  tab:
    backgroundColor: "transparent"
    textColor: "{colors.text-dim}"
    typography: "{typography.tab}"
    padding: "12px 2px 10px"
  tab-active:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    typography: "{typography.tab}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-dim}"
    typography: "{typography.mono}"
    rounded: "{rounded.all}"
    padding: "6px 10px"
  chip-on:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.all}"
    padding: "6px 10px"
  search-input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.mono}"
    rounded: "{rounded.all}"
    padding: "7px 10px"
    width: "220px"
  tag-pos:
    backgroundColor: "{colors.strength}"
    textColor: "{colors.strength}"
    rounded: "{rounded.all}"
    padding: "2px 6px"
  tag-neg:
    backgroundColor: "{colors.weakness}"
    textColor: "{colors.weakness}"
    rounded: "{rounded.all}"
    padding: "2px 6px"
---

# Design System: DURANT Draft Board — Trading-Floor Terminal

## Overview

**Creative North Star: "The Trading-Floor Terminal"**

This board reads like a live trading-desk monitor built for one operator making fast, decisive calls, not the friendly card-dashboard layout every fantasy tool defaults to. A near-black terminal ground, bone-white monospace type, and amber emphasis carry the whole surface; the only two departures from neutral ink are the amber rank/value/active-state accent and the signed green/red category deltas that read like a P&L feed. There is no card chrome anywhere: rows are separated by hairlines, corners are square, and density beats decoration at every choice point, because the tool exists to be scanned under a pick-clock, not admired.

The system commits fully to real terminal furniture rather than a generic "dark mode" reskin: a status-dot ticker strip at the header, tabular numerals wherever numbers must compare column to column, and a signature "executed order" drafted-state (`>> FILLED`) that treats marking a player as filling a trade, not just toggling a checkbox. This is a deliberate, disclosed risk — the direction sits closest to the incumbent board's own prior dark theme and to the genre default for stats tools — mitigated by committing to that terminal-specific vocabulary rather than a plain repaint.

This is a full visual-world replacement (not an extension of a prior DESIGN.md); tokens below are read directly from the shipped build, not from the pre-build direction contract.

**Key Characteristics:**
- Near-black terminal ground with a single warm amber accent, reserved for rank/value emphasis and active state
- One typeface family for everything — mono set as both `--mono` and `--sans` — no separate display face
- Zero border-radius anywhere; hairline dividers instead of card containers
- Signed green/red deltas for category strength/weakness, driven by the same ±0.75σ threshold everywhere it appears
- A named signature state (`>> FILLED`) standing in for "drafted," styled as an executed order, not a fade or checkbox

## Colors

A near-monochrome bone-on-black terminal ground with amber as the single warm accent and a green/red signed pair reserved strictly for data polarity (never for arbitrary decoration).

### Primary
- **Terminal Amber** (`#d98e3b`): rank numbers, the Val (DURANT total value) column, the active tab's label and underline, the season tag border, focus outlines, `::selection` background, cliff-marker dashed rule, tier-block titles, position-rank badge.

### Secondary
- **Signal Green** (`#4a8f6b` chart bars / `#5aa37a` tags and strong balance cells): positive z-score bars in the expanded chart, strength tags, and the "strong" step of the balance strip.
- **Signal Red** (`#d97362` drafted marker / `#d9605a` tags and chart negative bars): negative z-score bars, weakness tags, the balance strip's negative steps, and the drafted-row `>> FILLED` marker color (a distinct hue role from generic weakness-red, sharing the family).
- **Flag Amber-Light** (`#e0a83f`): data-availability warnings (`[!]` disclaimer banner, inline "no 25-26 data" notes, chart-row note), kept one step lighter than the primary accent so it reads as "notice" rather than "primary emphasis."

### Neutral
- **Terminal Black** (`#0a0c0f`): page background.
- **Panel** (`#10141a`): table zebra-striping (even rows), stat-card background alternate.
- **Panel Alt** (`#141a22`): header/ticker bar background, stat-card fill, disclaimer banner fill.
- **Panel Hover** (`#1a222c`): row hover background.
- **Bone Text** (`#e8e6df`): primary text — player names, values.
- **Dim Text** (`#9aa3b2`): secondary text — position/team meta, unselected tab labels, chips.
- **Faint Text** (`#808a96`): tertiary text — placeholder text, counts, chart axis labels, tier player-counts.
- **Hairline** (`#1c222b`): row dividers, tab-strip base rule.
- **Hairline Strong** (`#2b333f`): sticky-header rule, input/chip/select borders, scrollbar thumb.

### Named Rules
**The One Accent Rule.** Amber (`#d98e3b`) marks value and active state only — rank, Val, active tab, focus rings. It never doubles as a status color; strength/weakness always render in the green/red pair, never in amber, so amber's meaning ("this is the number/selection that matters right now") stays singular.

**The Signed-Only Color Rule.** Green and red never appear as decoration. Both hues are driven by the same underlying z-score and the same ±0.75σ threshold in every place they appear (tags, balance strip, expanded chart) — a color that isn't backed by that threshold does not get to use these hues.

## Typography

**Body/Display/Label Font:** `ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace` — declared identically as both `--mono` and `--sans`; there is no separate display or humanist face anywhere in the system.

**Character:** One monospace voice for the entire surface — table data, labels, the wordmark, tab names, tags, tier titles. This is a deliberate world commitment (not an oversight): a terminal reads as a terminal because numbers align in fixed-width columns and labels read like ticker text, not because of a paired display/body hierarchy. There is no separate "display" or "system" face; introducing one would break the world.

### Hierarchy
- **Wordmark** (700, 12px, letter-spacing 0.14em): "DURANT TERM" in the header bar only.
- **Tab label** (700, 12px, letter-spacing 0.1em, uppercase): Veterans/Rookies tab text; amber when active.
- **Section/column label** (700, 11px, letter-spacing 0.08em, uppercase, faint text): table column headers, stat-card labels, tier-title suffix, chart axis labels.
- **Player name** (700, 13.5px): the one slightly-larger-than-body weight in the table, anchoring the row.
- **Body/data** (400, 13px, tabular numerals): table cell values, stat cards, chart values — `font-variant-numeric: tabular-nums` set at the `td` level so every numeric column compares cleanly row to row.
- **Micro-label** (700, 9–11px): tag pills, balance-strip category letters, chart bar values, the `>> FILLED` marker.

### Named Rules
**The Tabular-Numerals Rule.** Every cell where numbers must compare vertically (`Val`, category z-scores, GP/MIN/PTS stat cards) sets `font-variant-numeric: tabular-nums`. A number that doesn't need column comparison (prose, notes) is exempt.

**The No-Display-Face Rule.** The system uses exactly one type family, monospace, for every role. This is durable and load-bearing to the "terminal" world; it is a rule to keep, not a gap to fill with a future headline face.

## Layout

Single-column, full-bleed layout with a sticky header stack (terminal ticker bar → tab strip → search/controls row) and a dense table filling the rest of the viewport — no page margins, no card containers, no max-width constraint. The sticky table header offset is computed at runtime from the actual topbar height (`syncStickyOffset()`), not a fixed guess, since the topbar's content (search row + controls row) varies between the Veterans and Rookies tabs.

Horizontal padding is 14px (`.wrap`, `.termbar`, `.topbar`) — the system's one consistent page gutter. Table cell padding is 7–9px vertical, 8px horizontal; the expanded chart row adds a 34px left indent so its content visually nests under the row that opened it.

**Responsive breakpoint: 640px.** Below this width:
- The search input narrows from 220px to 150px, and the stats line wraps to its own row (`order:10`) rather than staying inline right of the controls.
- The wordmark ("DURANT TERM") is hidden — the ticker and season tag alone carry the header bar's identity at narrow width.
- The category chart gains horizontal scroll (`overflow-x:auto`) rather than compressing 12 columns illegibly.
- **`.rowMid` (positional-rank badge + GP count) and `.balanceStrip` (the 12-cell threshold strip) are dropped entirely, not shrunk.** This is a documented, deliberate density trade: both are supplementary reads that duplicate information available one tap away in the expanded per-player chart row, and the alternative — shrinking a 250px, 12-cell strip to fit a phone width — would force horizontal scroll on the collapsed row itself, which the system treats as worse than omission. The tags (strength/weakness pills) stay visible at every width; they are the one always-on category signal.

## Elevation & Depth

No shadows anywhere in the system — a flat terminal ground with tonal layering as the only depth cue. Table rows step through four flat tones (`--bg` → `--surface` even-row zebra → `--surface-hover` on hover → `--bg` again when drafted, explicitly reverting the zebra tone to read as "receded"), and the expanded chart row sits on `--surface` to read as nested content, not an elevated panel. Borders (`--border`, `--border-strong`) do the separation work that shadows would do in a lifted system.

### Named Rules
**The Flat-Ground Rule.** Nothing lifts. Depth and state are communicated by background-tone stepping and hairline borders only; introducing a `box-shadow` anywhere would contradict the terminal-monitor world this system is built to read as.

## Shapes

Square corners everywhere — `border-radius: 0` is set explicitly on inputs, chips, chart bars, tags, the scrollbar thumb, and stat cards (the codebase's `--radius` equivalent is simply absent; every rounded-capable rule pins `border-radius:0`). Containers are bounded by 1px hairlines (`--border` for row dividers, `--border-strong` for structural rules like the sticky header base and input/chip borders), never by a filled card shape. The one exception to straight lines is the status dot in the header bar, a 7px filled circle — a single rounded glyph standing in for a terminal's "live" indicator, not a shape language applied elsewhere.

### Named Rules
**The Square-Corner Rule.** `border-radius: 0` is the default for every boxed element (inputs, chips, tags, cards, scrollbar). The status dot is the one named exception, justified as a literal live-indicator convention, not a precedent for rounding elsewhere.

## Components

### Tabs
Veterans / Rookies, uppercase mono labels with a trailing faint-mono player count. Inactive tabs sit in dim text with a transparent underline; the active tab turns amber text with a 2px amber bottom border. No background fill differentiates active from inactive — color and underline alone carry the state, consistent with the flat-ground rule.

### Chips
- **Style:** square, 1px `--border-strong` outline, `--surface` background, mono bold label, no fill at rest.
- **State:** `.chip.on` inverts to solid amber background with black (`--bg`) text — used for the "Hide drafted" toggle and the position filter chips (PG/SG/SF/PF/C, generated from the data). Selected/filter state, not primary/secondary action.

### Search Input
Square, 1px `--border-strong` border, `--surface` fill, mono type, placeholder in faint text (`Search… ( / )` — the keyboard-shortcut hint is baked into the placeholder copy itself). Focus state swaps the border to amber and adds a matching 1px amber outline; no glow or shadow.

### Sort Select
A native `<select>` element, themed only at the shell level (square border, `--surface` background, mono bold label) — its dropdown popup chrome is intentionally left as the browser's native cross-platform default. This was a disclosed finish-review keep-decision, not an oversight: custom-theming a native select popup was judged disproportionate scope for a personal, single-user, single-session tool. Not a system rule to extend — a future component needing a styled dropdown should not inherit "leave native chrome" as doctrine; it was a scope call for this one control.

### The Ranked Table (signature component)
The dense monospace grid is the board's primary surface: `#` (rank, click-to-draft) | Player (name + pos/team meta) | Val (amber, tabular) | a combined cell holding strength/weakness tags, positional-rank badge, GP count, and the 12-cell balance strip. Even rows carry a subtle `--surface` zebra tone; hover lifts to `--surface-hover`; the header row is sticky with an offset measured from the live topbar height. Rows are keyboard-activatable (`tabindex`, `role="button"`, Enter/Space) as well as clickable.

### Tags (strength/weakness pills)
Up to 2 green "strength" + 2 red "weakness" pills per row, square, 1px `currentColor` border, 18%-opacity tinted fill (`color-mix`), mono bold 11px category label only (no numeric value — the value lives in the expanded chart). Driven by the same ±0.75σ z-score threshold as the balance strip. TD, TECH, TO, and DD are permanently excluded from tag generation (`TAG_EXCLUDE`) because their pool variance is bimodal or trivially correlated with usage and would dominate every player's tags — verified by hand against 130 real players (see `build_draft_board.py` header comment). This exclusion is a data-legibility finding about the DURANT model's own category distribution, not a visual-system prohibition; it should not be read as "never show TD/TECH" in any future surface.

### Balance Strip
12 fixed-order category cells to the right of the tags, each a small colored swatch + faint category-letter label. Colors step through 4 states from the same z-score (strong/mild green, mild/strong red, or border-neutral for "typical" or for the 4 tag-excluded categories, shown as neutral placeholders rather than omitted so the 12-category layout stays fixed-width). Dropped below 640px (see Layout).

### The ">> FILLED" Drafted-State Signature (signature component)
The system's most distinctive rule: marking a player drafted does not fade or strike the whole row cheaply — it renders a `>> FILLED` tag in the drafted-red hue immediately before the player's name (mono, bold, 10px, tracked), strikes the name through in that same red, and dims (25–35% opacity) every secondary element in the row — tags, balance strip, GP badge, positional-rank badge, notes — while returning the row's background to base `--bg` (explicitly overriding the zebra tone, so a drafted row visually "recedes" rather than merely graying). The row still hover-highlights to `--surface`. This reads as an executed trade confirmation, matching the STORY beat in the direction contract, not a generic "unavailable" treatment (no full opacity fade, no removal from view unless "Hide drafted" is active).

### Toast / Undo
A single bottom-centered toast (`position:fixed`, square corners, `--surface-alt` fill, 1px `--border-strong` outline) confirms every drafted-toggle regardless of trigger (click, keyboard, rank-cell), with a "click or ⌘Z to undo" hint appended for undoable actions. Single-slot undo only (most recent action), matching a fast correction path rather than a full history stack. Auto-dismisses after 2.5s or on click.

### The Expanded Per-Player Chart Row
Clicking a row (or its rank cell) inserts a nested `tr.chart-row` beneath it: two rows of stat cards (Projected 2026-27, then Actual 2025-26 per-game, or an italic "No 2025-26 data" placeholder), then a 12-column bar chart on a shared zero baseline. Bars run up (green, positive z) or down (red, negative z) from a 1px baseline rule at 32px, height clamped visually at ±3σ though the printed numeric value is never clamped. Only one chart row is open at a time (`openChart`); opening a new one closes the prior. Bars scroll horizontally rather than compress below 640px.

### Rookie Tier Blocks
Rookies render as tier-grouped blocks (`.tier-block`) instead of a numeric rank column, because rookies sharing a draft-slot bucket share identical baseline projections by construction (disclosed via a standing `[!]`-prefixed disclaimer banner above the section). Each block has an amber, uppercase, tracked tier title with a faint mono player-count suffix, underlined by a `--border-strong` hairline — a lighter-weight echo of the veteran table's header style rather than a new visual language.

### Cliff Marker
A 2px dashed amber top-border (`tr.cliff`) marks a value-gap exceeding a fixed threshold (0.25) between adjacent undrafted players when sorted by Value — live and reactive to drafted-state, but only meaningful (and only rendered) in Value-sort order, since a category sort's row order isn't Value order.

## Do's and Don'ts

### Do:
- **Do** keep every numeric column (`Val`, z-scores, stat cards) on `tabular-nums` so figures compare cleanly down a column.
- **Do** drive every green/red instance (tags, balance strip, chart bars) from the same ±0.75σ z-score threshold — a color not backed by that threshold has no place in this system.
- **Do** use `border-radius: 0` on every new boxed element (inputs, chips, tags, cards) — the status dot is the sole named exception.
- **Do** treat the `>> FILLED` executed-order pattern (prefix tag + strikethrough + secondary-element dimming + zebra-tone reversion) as the canonical "item is done/committed" state for any future row-based list in this tool, not a fade or removal.
- **Do** route future edits through `scripts/build_draft_board.py`'s `TEMPLATE` string — `draft_board_2026_27.html` is a generated artifact, rewritten wholesale by `python3 scripts/build_draft_board.py`; hand-editing the generated HTML directly will be silently discarded on the next build.

### Don't:
- **Don't** introduce a second type family (display, serif, or system-UI sans) anywhere in this world — the single monospace voice is load-bearing to the terminal identity, confirmed across every role from wordmark to body data.
- **Don't** add `box-shadow` or any lifted/card treatment — depth is tonal-layering only (see Elevation & Depth); a shadow would contradict the flat-ground terminal world.
- **Don't** canonize the native, unstyled `<select>` dropdown popup as a system-wide "leave selects native" rule. It is recorded here as a disclosed, scope-bounded keep-decision for this personal single-user tool's sort control, not a design-system prohibition against ever styling a dropdown.
- **Don't** read the `TAG_EXCLUDE` category exclusions (TD, TECH, TO, DD) as a visual rule against ever surfacing those categories — they're fully shown, un-excluded, in the expanded chart. The exclusion is specific to badge/tag generation, where their variance behavior would dominate every player's tags; it is a data-legibility finding, not a display prohibition.
