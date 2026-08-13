# Availability Labeled Set

`availability_labeled_set.csv` — every player independently diagnosed as an
`availability overtrust` (real chronic-miss pattern: predicted well, actual
came in much worse, low `AVAILABILITY_SIGNAL`) or `availability undertrust`
(predicted low on availability, actual came in much better — firing an
availability-risk rule on these would actively hurt) case across all three
exact-league benchmarks (2025-26, 2024-25, 2023-24).

**Provenance:** built from `durant_rankings_2025_26.csv` (pre-availability-
risk-factor model state — the diagnostic label itself doesn't depend on that
feature) via `validate.build_breakout_availability_artifact()` with
`top_n=500` (default `top_n=10` would truncate this), filtered to the two
availability labels, with `GP_2024_25`/`GP_2023_24` (raw, pre-qualification-
filter games played) attached directly from the BBR total-stats CSVs.

**Counts:** 15 unique players / 19 rows labeled `availability overtrust`,
26 unique players / 35 rows labeled `availability undertrust`, across the
three benchmark seasons (a player can appear more than once if they show
the pattern in more than one season, and can appear under *different*
labels in different seasons — e.g. Jimmy Butler is `overtrust` in 2024-25
and `undertrust` in 2023-24).

**Built for:** the availability-risk detection-condition redesign (see the
issue that replaces #2 — link added when filed). Design against recall on
the `availability overtrust` rows; use `availability undertrust` as the
false-positive guard; report both.

**Depleting-resource note:** this set was built by hand-inspecting exactly
the three exact-league benchmarks the acceptance gate also uses. Using it as
a design target and *also* as part of later acceptance evaluation is the
same problem `docs/adr/0001` calls out for the holdout seasons themselves —
a metric computed against data a design decision was tuned against has
reduced power to independently confirm that decision. Treat this set as
partially spent for evaluation purposes once it's been used to shape the
detection condition's design.
