---
name: DURANT — The Ember Signal
description: A near-black, single-accent, system-sans visual world spanning a real landing page and a dense offline draft-day tool, built for fast operator scanning, not card chrome.
colors:
  bg: "#0b0c10"
  panel: "rgba(255,255,255,.055)"
  panel-solid: "#15171c"
  panel-alt-solid: "#1b1e24"
  border: "rgba(255,255,255,.08)"
  border-strong: "rgba(255,255,255,.16)"
  ink: "#eef0f4"
  ink-dim: "#a7acb8"
  ink-faint: "#838a97"
  ember: "#ff7a33"
  flag: "#e0a83f"
  strength: "#3ddc97"
  weakness: "#ff6b6b"
typography:
  display:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "44px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "normal"
    letterSpacing: "normal"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.08em"
  code:
    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace'
    fontSize: "12.5px"
    fontWeight: 400
    letterSpacing: "normal"
rounded:
  control: "7px"
  control-lg: "9px"
  container: "14px"
  pill: "999px"
  table: "0px"
spacing:
  xs: "2px"
  sm: "8px"
  md: "14px"
  lg: "24px"
  xl: "60px"
components:
  button-primary:
    backgroundColor: "{colors.ember}"
    textColor: "#17120c"
    rounded: "{rounded.control-lg}"
    padding: "12px 22px"
  search-input:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
    width: "220px"
  chip:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.ink-dim}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
  chip-on:
    backgroundColor: "{colors.ember}"
    textColor: "{colors.bg}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
  tag-strength:
    backgroundColor: "{colors.strength}"
    textColor: "{colors.strength}"
    rounded: "{rounded.control}"
    padding: "4px 9px"
  tag-weakness:
    backgroundColor: "{colors.weakness}"
    textColor: "{colors.weakness}"
    rounded: "{rounded.control}"
    padding: "4px 9px"
  toolkit-card:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.ink}"
    padding: "26px 26px 24px"
---

# Design System: DURANT — The Ember Signal

## Overview

**Creative North Star: "The Ember Signal"**

This is a full visual-world replacement of the prior "Trading-Floor Terminal" system, read directly from the shipped build (`index.html` and the `TEMPLATE` string in `scripts/build_draft_board.py`), not from the direction contract's planning language. The old world committed to amber on black with all-monospace terminal type and zero radius everywhere; the shipped world keeps near-black and a warm single accent, but drops the terminal cosplay — no ticker-strip furniture, no monospace-everywhere, no `>> FILLED` order-confirmation marker. What replaced it is quieter: a near-black ground, flat translucent-white panels instead of solid navy-gray surfaces, one ember-orange accent, and ordinary system UI type for every role except literal CLI command snippets.

The two surfaces now read as one coherent product rather than a tool plus an orphaned splash page. `index.html` is a real small website — sticky blurred nav, hero with a single restrained accent-stroke arc mark behind the wordmark, a numbered 2x2 toolkit grid with staggered entrance motion — while `draft_board_2026_27.html` stays a dense, flat, data-first table for scanning under pick-clock pressure. The same tokens (bg, panel, border, ember, strength/weakness green-red) run through both; what differs is composition, not vocabulary. A deliberate density split governs shape: standalone controls (search, chips, buttons, tags, toasts) get a small 5–10px radius, but the ranked table itself stays flat and square-cornered, because a live-draft tool needs row density, not card chrome.

**Key Characteristics:**
- Near-black ground (`#0b0c10`) with flat, translucent-white panels (`rgba(255,255,255,.055–.16)`) — no solid navy-gray surface tokens
- A single accent, ember orange (`#ff7a33`), replacing the old world's amber and its multi-hue drafted/flag palette
- System sans-serif UI type everywhere; monospace survives only in literal CLI command snippets, not as a UI voice
- Small radius (5–10px) on standalone controls; the dense table stays flat and unrounded — a deliberate, not accidental, split
- One restrained abstract "arc" mark used exactly once (behind the hero wordmark); not repeated as a motif elsewhere
- No colored glow shadows and no gradient text anywhere — both deliberately avoided, flagged in-build as generic-AI-UI tells

## Colors

A near-monochrome near-black ground with one warm accent and a green/red signed pair reserved for data polarity.

### Primary
- **Ember** (`#ff7a33`): primary CTA button fill, hero headline's one emphasized word, eyebrow labels, nav wordmark dot, live-status pill text/border, toolkit card hover border and "go" link, rank number and Val accent bar, active tab label/underline, chip-on fill, cliff-marker dashed border, focus outlines, `::selection` background, tier-block titles.

### Secondary
- **Strength Green** (`#3ddc97`): positive z-score chart bars, strength tags, "mine" category-need chips when positive.
- **Weakness Red** (`#ff6b6b`): negative z-score chart bars, weakness tags, and — unlike the prior world — the drafted-row strikethrough color too. The old system gave "drafted" its own distinct red hue (`#d97362`) separate from "weakness" red (`#d9605a`); the shipped build collapses both onto the single weakness red (`#ff6b6b`). This is an observed simplification, not a redundant token to re-split.
- **Flag Amber** (`#e0a83f`): data-availability notices only (`[!]` disclaimer banner, inline "no prior-season data" notes) — kept visually distinct from ember so a notice never reads as the primary accent.

### Neutral
- **Near-Black** (`#0b0c10`): page background on both surfaces.
- **Panel** (`rgba(255,255,255,.055)`): row-hover tone on the draft board (translucent, so it layers correctly over zebra striping).
- **Panel Solid** (`#15171c`): toolkit cards, search/chip/select fills, stat-card alt fill, zebra-striped table rows.
- **Panel Alt Solid** (`#1b1e24`): card hover fill on the landing page, toast background, disclaimer banner fill.
- **Ink** (`#eef0f4`): primary text — player names, headline, body copy.
- **Ink Dim** (`#a7acb8`): secondary text — lede copy, meta (position/team), unselected tab labels, chip text.
- **Ink Faint** (`#838a97`): tertiary text — placeholder, stat labels, table column headers, card numbering.
- **Border** (`rgba(255,255,255,.08)`): default hairline — row dividers, card grid lines, section rules.
- **Border Strong** (`rgba(255,255,255,.16)`): structural rule — sticky-header base, input/chip/select borders, scrollbar thumb.

### Named Rules
**The One Accent Rule.** Ember (`#ff7a33`) is the system's only decorative/brand color. It never does double duty as a status color — strength/weakness always render in the green/red pair, never in ember, so ember's meaning ("primary action, emphasis, or active state") stays singular.

**The One Owned Device Rule.** The faint quarter-circle arc stroke behind the hero wordmark appears exactly once, at 8% opacity, on the landing page only. It is not a repeatable background motif — a future surface should not inherit "add an arc" as a system pattern; it is this one page's signature, not a component.

## Typography

**UI Font:** `-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif` (the draft board additionally lists `Inter` in its stack) — used for every role on both surfaces: headline, body, labels, table data, tags, nav.
**Code Font:** `ui-monospace, "SF Mono", Menlo, monospace` — used exclusively for literal CLI command snippets on the landing page's toolkit cards (e.g. `python scripts/punt_planner.py --team "YourTeam"`). It is not a UI voice; nothing else in the system uses it.

**Character:** A plain, legible system-UI voice carries the whole product now. This is a direct reversal of the prior world's "one monospace voice for everything" doctrine — note the draft board's CSS still names a `--mono` custom property, but it is now assigned the identical sans-serif stack as `--sans`; the variable name is vestigial, not a live typographic distinction. Numeric legibility is preserved not through monospace but through `font-variant-numeric: tabular-nums` applied directly to every comparison column.

### Hierarchy
- **Display / Hero H1** (800, 44px, line-height 1.1, letter-spacing -0.02em; 32px below 720px): the landing page's one headline, with exactly one word recolored ember via `<em>` (not italic — the system repurposes `<em>` as a color hook, never for italic emphasis).
- **Headline / Section Title** (800, 26px, letter-spacing -0.01em): "Everything for draft day..." toolkit section title.
- **Title / Card Name** (700, 16px): toolkit card names (Draft Board, Punt Planner, etc.).
- **Body / Lede** (400, 16.5px, line-height 1.6, ink-dim): hero supporting copy, max-width 520px.
- **Body / Data** (400, 13px, tabular-nums): table cell values — set at the `td` level so every numeric column compares cleanly row to row.
- **Label** (700, 11-12px, letter-spacing .08-.1em, uppercase): eyebrow labels, table column headers, tab labels, tier titles, nav wordmark.
- **Stat Number** (800, 26px, tabular-nums): the hero's 3-stat row (14 categories / 100% offline / 3 CLI companions) and the draft board's live counters.

### Named Rules
**The Tabular-Numerals Rule.** Every cell where numbers must compare vertically (Val, z-scores, hero stat row) sets `font-variant-numeric: tabular-nums`, carried over unchanged from the prior world — this survived the redesign because it is a legibility mechanism, not a terminal-aesthetic one.

**The No-Monospace-UI Rule.** Monospace type is reserved for literal command-line text the user would type or paste verbatim. It does not return as a UI label font, a wordmark font, or a data font anywhere — that role belongs to the system sans stack now.

## Layout

The landing page (`index.html`) uses a centered `max-width: 1180px` container (`.wrap`) with 24px horizontal padding, and real page sections: sticky blurred nav → hero (88px top padding) → a `border-top` rule-divided toolkit section (60px vertical padding) → footer. The hero's entrance elements (eyebrow, h1, lede, actions, stats) fade up in a staggered sequence (0s, .06s, .12s, .18s, .24s delays) via a shared `fadeUp` keyframe. The toolkit section is a `2x2` grid (`repeat(2, 1fr)`, 1px gap filled by `--border` so dividers read as hairlines between tiles) that collapses to one column below 720px; each card's entrance is staggered an additional .05s–.23s.

The draft board (`draft_board_2026_27.html`) stays single-column, full-bleed: a sticky header stack (tabs → search row → controls row) above a dense table filling the rest of the viewport, no max-width, no page margins. The sticky table-header offset is computed at runtime from the live topbar height (`--topbar-h`), not a fixed guess. Horizontal padding is 14px (`.wrap`, `.topbar`) on this surface — tighter than the landing page's 24px, consistent with a denser, tool-not-site posture.

**Responsive breakpoints:** the landing page collapses its 2x2 toolkit grid to one column and shrinks the H1 to 32px at 720px. The draft board narrows its search input (220px → 150px), wraps the stats line to its own row, scrolls the category chart horizontally, and drops the positional-rank badge and 12-cell balance strip entirely (not shrunk) at 640px — both are supplementary reads duplicated one tap away in the expanded per-player chart row.

## Elevation & Depth

Flat by default on both surfaces — tonal layering and hairline borders do the separation work, not shadows. The one exception is interaction feedback: the primary CTA button lifts 2px and gains a **neutral dark elevation shadow** (`0 8px 20px rgba(0,0,0,.4)`) on hover, and toolkit cards lift 3px with an ember-tinted left border on hover. Both are deliberately colorless/neutral-dark shadows, not colored "glow" shadows — the build explicitly avoids tinted glow as a known generic-AI-UI tell.

### Shadow Vocabulary
- **Button hover elevation** (`box-shadow: 0 8px 20px rgba(0,0,0,.4)`): the only shadow in the system; fires on `.btnPrimary:hover` only.

### Named Rules
**The No-Glow Rule.** No shadow in this system carries a hue from the accent or semantic palette. Depth, where it exists at all, reads as a neutral dark elevation cue, never as a colored halo around an element.

## Shapes

A deliberate two-register system: standalone controls get a small, tasteful radius (5-10px), while the dense table stays flat and square. Search input, chips, and the sort select use 7-8px; the primary button uses 9px; the toast and disclaimer banner use 8-10px; tags use 5px; the toolkit-card grid container (not the individual cards) uses 14px with `overflow: hidden` to clip tile corners; the nav status pill uses a full 999px pill. Against that, the table itself, its header, rows, stat cards, and chart bars are explicitly `border-radius: 0` (chart bars gain a tiny 2px cap only on the rounded end facing away from the shared baseline). Borders throughout are translucent white (`rgba(255,255,255,.08)` / `.16`) rather than solid navy-gray hairlines — a flatter, more "glass panel" border language than the prior world's opaque hex hairlines.

### Named Rules
**The Control-vs-Table Radius Rule.** Small radius (5-10px) belongs to standalone interactive chrome (buttons, inputs, chips, tags, toasts, pills). The ranked table is exempt by design — a live-draft tool needs row density, not card chrome, so the table stays flat regardless of how rounded its surrounding controls are.

## Components

### Buttons
- **Primary:** ember fill (`#ff7a33`), dark ink text (`#17120c`), 9px radius, 12px/22px padding, 700 weight. Hover lifts 2px with a neutral dark shadow (see Elevation).
- **Ghost / secondary link:** no fill, ink-dim text, color shifts to full ink on hover — used for the hero's "See the toolkit" smooth-scroll link.

### Nav
Sticky, `rgba(11,12,16,.75)` background with `backdrop-filter: blur(10px)`, bottom hairline border. Wordmark pairs a 7px ember dot with 800-weight text. A live-status pill (full 999px radius, 1px border) reads "no draft in progress" in ink-faint at rest, or switches to ember text/border and a drafted/your-team count once `localStorage` shows a draft underway — read live from the draft board's own storage keys, no duplicated dataset.

### Toolkit Card
Numbered (01-04), flat panel-solid fill inside a hairline-divided grid, 3px left border that stays transparent at rest and turns ember on hover alongside a 3px lift. Houses a name, description, and either a "go" link (card 1, linking to the draft board) or a literal monospace CLI command snippet (cards 2-4) in a `rgba(0,0,0,.35)` inset block.

### Search Input / Chips / Sort Select
Flat panel-solid fill, 1px `border-strong` outline, 7-8px radius, sans-serif type (not monospace, a reversal from the prior world). Focus swaps the border to ember and adds a matching ember outline; no glow. Chip-on state inverts to solid ember fill with near-black text.

### Tags (strength/weakness pills)
Up to 2 green + 2 red pills per row, 5px radius, 1px `currentColor` border, 18%-opacity tinted fill (`color-mix`), sans-serif 700-weight label. Driven by the same ±0.75σ z-score threshold as the balance strip, carried over unchanged from the prior world.

### Val (Value) — scoreboard readout (signature component)
The Val column no longer renders as plain ember-colored text (the prior world's treatment). It now renders as a scoreboard readout: right-aligned, tabular-nums, 700-weight, with a 2px solid ember border running down its left edge as a separator bar rather than color alone carrying the emphasis.

### Drafted State
Marking a player drafted dims the row's secondary elements to 25-35% opacity, strikes the player name through in weakness red, and reverts the row to base background (explicitly overriding zebra striping so a drafted row visually recedes). The prior world's `>> FILLED` prefix-tag marker is dropped entirely — this build uses plain dim + strikethrough, no textual confirmation tag.

### Toast
Bottom-centered, panel-alt-solid fill, 1px `border-strong` outline, 10px radius, fades/translates on show. Confirms every drafted-toggle with an optional "click or ⌘Z to undo" hint.

### The Ranked Table (signature component)
The dense grid stays the board's primary surface and stays flat by design (see Shapes): rank | player (name + meta) | Val (scoreboard readout) | combined tags/badges/balance-strip cell. Zebra striping and hover tone are now translucent-white (`rgba(255,255,255,.055)`) rather than a solid hex panel tone.

## Do's and Don'ts

### Do:
- **Do** keep the table flat (`border-radius: 0`) even as every standalone control around it carries 5-10px radius — this split is deliberate, not an inconsistency to fix.
- **Do** use ember (`#ff7a33`) as the only decorative accent; drive strength/weakness exclusively through the green/red pair.
- **Do** render the Val column as a scoreboard readout (right-aligned, tabular-nums, left ember border bar), not plain colored text.
- **Do** route future edits through `scripts/build_draft_board.py`'s `TEMPLATE` string — `draft_board_2026_27.html` is a generated artifact, rewritten wholesale by `python3 scripts/build_draft_board.py`.
- **Do** use the neutral dark elevation shadow (`0 8px 20px rgba(0,0,0,.4)`) for the one hover-lift case that needs a shadow at all.

### Don't:
- **Don't** reintroduce monospace as a UI type voice. It is reserved for literal CLI command snippets only (see Typography).
- **Don't** add a colored "glow" shadow or gradient text anywhere — both are deliberately avoided as generic AI-UI tells; the one shadow in the system is neutral dark, and no text anywhere uses a gradient fill.
- **Don't** repeat the hero's arc-stroke mark as a recurring background motif on other pages or sections — it is a one-time signature, not a component (see The One Owned Device Rule).
- **Don't** reintroduce a `>> FILLED`-style textual confirmation tag for the drafted state — the shipped build deliberately replaced it with plain dim + strikethrough; recording the old marker as current doctrine would misstate what's actually live.
- **Don't** treat the draft board's `--mono` custom property name as evidence that monospace survives as a UI font there — it currently resolves to the same sans-serif stack as `--sans`. This is a naming leftover in the build, not a token to design against.
