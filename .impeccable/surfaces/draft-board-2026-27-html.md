---
version: 1
slug: "draft-board-2026-27-html"
primary_target: "draft_board_2026_27.html"
related_targets: []
---

## Scope

Redesign (full visual world replacement) of `draft_board_2026_27.html`, the standalone offline draft-day tool. Personal, single-user (Chester), Operate mode. Functionality, data, and the offline single-file build model are unchanged — this is a visual-world replacement only.

## Audience, job, action, proof, constraints

- Audience: one user (Chester), live during his own fantasy draft, under pick-clock pressure.
- Job: scan ranked players fast, compare 12 DURANT categories at a glance, mark players drafted as the draft proceeds, switch Veterans/Rookies tabs, search by name.
- Proof/content: real DURANT rankings data embedded at build time (`durant_rankings_2026_27.csv`, `durant_rankings_rookies_2026_27.csv`).
- Constraints: must work fully offline (self-contained HTML, no network), must not sacrifice data density or scanning speed for decoration, no gamified/playful tone.

## Direction contract

**THESIS:** The board reads like a live trading-desk terminal built for one operator making fast, decisive calls — not the friendly card-dashboard layout every fantasy tool defaults to.

**OWN-WORLD:** Near-black terminal ground (#0b0e12/#0f1319), bone-white monospace type (ui-monospace/SF Mono stack) throughout, amber (#d98e3b) reserved for rank/value emphasis and active tab state, green (#4a8f6b) / red (#d97362) signed deltas for category strength/weakness, hairline dividers (no rounded cards), uppercase tracked labels, a ticker-style header strip, tabular numerals everywhere numbers must compare column to column.

**STORY:** The user opens the board mid-draft, sees a live ticker of top movers across the header, scans the dense ranked grid where category cells read green (strength) or red (weakness) at a glance, types to filter instantly, and clicks a rank cell to "fill" a player — the row dims, strikes through, and gets a ">> FILLED" tag, like an executed order on a trading desk.

**FIRST VIEWPORT:** Header bar (status dot, "DURANT TERM" wordmark, scrolling ticker of top movers, live/season tag) at top; tab strip below (Veterans/Rookies, amber underline on active) with counts; toolbar (search input left, legend right); dense monospace ranked table filling the remaining viewport — rank | player+pos | value | 12 category columns, right-aligned tabular numerals, hover-highlighted rows, no card chrome or rounded containers.

**FORM:** Bloomberg-terminal / trading-floor monitor wall. This was Impeccable's own top-ranked grounded candidate (kicker IMPECCABLE'S PICK on the decision round) and a user override of the roll's assigned direction (Scouting Index Card, direction concept-seed key `33f20961`, assigned index 3); a user-pinned choice beats the roll. Confirmed by the user against two build alternates (Scouting Index Card, Split-Flap Concourse Board) via real interactive HTML prototypes.

**Honest risk (disclosed, accepted by user):** this is the direction closest to the current board's own existing dark theme and the category default for fantasy/stats tools generally — familiar and effective, chosen knowingly over two more novel alternatives. Mitigate by committing fully to real terminal chrome (ticker, status dot, monospace grid, executed-order fill state) rather than a generic "dark mode" reskin, so it reads as its own world, not a repaint of the incumbent.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Unresolved decisions

- Exact ticker content/behavior at full scale (which players/stats feature, refresh cadence — this is a static file, so "live" is stylistic, not literal).
- Whether the rookie tab's tier-based grouping (vs. numeric rank) gets its own visual treatment within this world.
