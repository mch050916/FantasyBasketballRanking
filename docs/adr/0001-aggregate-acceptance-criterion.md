---
status: accepted
---

# Model changes are accepted on aggregate exact-league metrics, not family-level diagnostics

Issue #1's role-growth tune moved the role-growth-underreaction family's avg |delta| from 43.78 to 43.72 across 6 hits — a metric with no sensitivity at that n, so the decision was gated on a number that couldn't have detected success even if the tune had worked. Going forward, family-level avg |delta| (breakout/availability labels, category-distortion families, etc.) is diagnostic-only: it tells us where to look, but never decides whether a change ships. Acceptance is instead gated on aggregate Spearman and MAE computed over all matched players in the three exact-league benchmarks — 2025-26 (n=72), 2024-25 (n=87), 2023-24 (n=98) — with the acceptance shape (no meaningful regression on any of the three, improvement on at least two) and the numeric "meaningful" threshold declared in the plan doc *before* the change is implemented, never adjusted after seeing results. `compare_baselines.py` prints before/after aggregate Spearman+MAE for all three seasons side by side so this check is one command.

## Method: paired bootstrap, not independent confidence bands

Comparing two independently-computed confidence intervals (one for the baseline run, one for the candidate run) is too conservative — the bands overlap even when a change is real, because most of each band's width comes from sample composition, which is identical between the two runs. `compare_baselines.py --bootstrap` instead does a **paired** bootstrap: each of ~5000 iterations draws one set of player indices and applies it to both runs, so the recorded delta (candidate − baseline) isolates the effect of the change itself. The key number is `pct_improved` — the proportion of resampled deltas that moved in the right direction. How high `pct_improved` needs to be before it counts as "meaningful" is not fixed at some conventional number like 95% — it depends on the effect size the specific change can realistically produce (see issue #2's threshold below for a worked example with reasoning). This is what the numeric "meaningful" threshold above should be set against, not a bare point-estimate difference.

Pairing is by player identity (`PLAYER_KEY`, the same canonical name-key `identity.py`/`validate.py` use everywhere else), not row position — verified 2026-08-14 with a regression test that shuffles one side's row order and confirms the paired result is byte-identical (`test_pairing_is_by_identity_not_position`). This matters because a model change can shift which players qualify or reorder the output; a positional implementation would pass every other test here (both sides come from the same deterministically-ordered pipeline in real use) but breaks silently the moment row order diverges. Players present in only one run are excluded from the paired comparison and reported separately (`excluded_before_only` / `excluded_after_only`) so a large exclusion count doesn't pass unnoticed.

**Null-change sanity check (2026-08-14):** running `--bootstrap` with the current main baseline as both `--before` and `--after` gives `pct_improved` = 0.0% (not ~50%) on both metrics, for all three exact-league benchmarks, with the delta distribution a point mass at exactly zero. This is the mathematically necessary result, not a bug: pairing on identical data means every resampled iteration applies the same indices to byte-identical arrays on both sides, so the delta is exactly zero on every draw — confirmed directly (`RANK_before == RANK_after` and `ACTUAL_RANK_before == ACTUAL_RANK_after` for all paired rows). A ~50% split is the signature of two *independently*-varying sides with no true difference — self-comparison against literally the same file has no independent variation to produce that split. (Self-comparison alone can't distinguish identity-based pairing from a positional bug either, since both sides are already in matching order in this degenerate case — that's what the shuffle-order regression test above is for.)

**Coverage: three checks, three different failure modes — don't assume one implies another.**

| Check | Verifies | Blind to |
|---|---|---|
| Null-change sanity check | Determinism (identical inputs → delta ≡ 0) | Positional vs. identity-based pairing — self-comparison is order-symmetric, so a positional bug passes it too |
| Shuffle-order regression test | Pairing is identity-based, not positional | Only exercises a *fixed* player set on both sides — never tests a set that differs between runs |
| `excluded_before_only` / `excluded_after_only` | A shifting qualifying-player set between runs | Not a test at all — a runtime count a human has to read and act on |

The case issue #2 will actually hit — availability shading moving a player across the GP/MPG qualification bar, so the set of ranked players itself differs between the before and after runs — isn't covered by either test above. It's covered *only* by the exclusion counters, which is why `print_paired_bootstrap_report` prints them as their own line (not folded into the header) and flags anything over 20% of the union for investigation. "Pairing is verified" (the shuffle test passing) does not mean "set-shift is handled" — those are separate claims backed by separate mechanisms, and future sessions extending this tooling shouldn't collapse them.

`compare_baselines.py --noise-floor` reports the unpaired bootstrap noise floor (Part A) for a single run, useful for sanity-checking how much a season's Spearman/MAE naturally wobbles from sample composition alone — see the 2026-08-13 baseline bands recorded against `durant_rankings_2025_26.csv` (5000 resamples, seed=42):

| Benchmark | n | Spearman mean (95% CI) | MAE mean (95% CI) |
|---|---|---|---|
| 2025-26 | 72 | 0.611 (0.438, 0.746) | 23.57 (19.18, 28.24) |
| 2024-25 | 87 | 0.629 (0.481, 0.753) | 21.45 (18.09, 24.95) |
| 2023-24 | 98 | 0.688 (0.567, 0.787) | 20.76 (17.61, 24.08) |

## Power check: verify the metric can detect the declared effect size (added 2026-08-14)

Issue #2 surfaced a bug in this ADR itself, in the opposite direction from the one issue #1 surfaced. Issue #1 gated a decision on a metric with no statistical power to detect a real family-level effect at n=6. Issue #2's 80% threshold gated a decision on a metric with no statistical power to detect a real *single-player* effect: one correct rank move in a 72–98-player pool cannot shift aggregate Spearman `pct_improved` past 80% regardless of correctness — that's arithmetic, not a tuning problem. Both are the same underlying mistake: using an underpowered instrument to make a ship/no-ship call. The fix is the same principle both times — check the instrument can detect the declared effect *before* trusting it, not after.

**Before any threshold is declared in a plan doc, three steps are now required:**

1. **State the expected effect size explicitly** — how many players are expected to move, and by roughly what rank magnitude. Not a vibe, a number, checked against real data where possible (issue #2's original "~5 affected players" estimate was a guess, not checked against the actual GP distribution — see below).
2. **Check whether the chosen metric can detect that effect at the chosen bar.** If a change is expected to move 1–2 players, aggregate pool-wide Spearman `pct_improved` cannot clear 80% no matter how correct the change is. This should be established at plan time, arithmetically, not discovered after implementation.
3. **If the metric is underpowered for the expected effect, the plan doc declares a different, equally pre-committed criterion instead** — not a looser version of the same one. See the narrow-change replacement criterion below for the pattern this ADR now recommends.

**This does not loosen the 80%/30% bar.** That threshold stands, unchanged, for changes with a broad expected effect (multiple players, meaningful aggregate movement) — issue #2's case doesn't call it into question, it just isn't the right instrument for issue #2's *particular* effect size.

### Replacement criterion for narrowly-scoped changes

For a change whose honest expected effect is a small, specific set of players (not a pool-wide shift), aggregate Spearman/MAE is the wrong instrument. Two-part replacement, developed for issue #2:

**Part A — Collateral damage floor.** No player outside the intended target set may move outside the pool's own noise floor. This formalizes what had been an ad hoc manual audit (issue #2's implementer caught 13-player collateral damage by hand at an earlier, looser threshold) into an automated, repeatable check — `compare_baselines.py --target-players "Name,Name"` flags any non-target player whose rank moved further than the target set's own reordering could mechanically explain (K target players bound any single non-target player's rank move to K, since each target player crossing them contributes at most ±1).

That mechanical bound catches reordering ripple but not the pipeline's *other* ripple source, found while building this: `compute_g_scores()` normalizes every category against pool-wide Box-Cox mean/std, so changing one player's raw stats shifts that normalization slightly for every other player too — confirmed directly on issue #2's real data (Josh Hart's rank moved 20→18 with `GP_FACTOR`/`DECLINE_FACTOR`/`AVAILABILITY_RISK_FACTOR` byte-identical before/after; `TOTAL_VALUE` moved only 2.0974→2.1051, ~0.4%). The report therefore also carries each flagged player's `TOTAL_VALUE` delta, so a human can tell a real change from renormalization noise — the tool narrows who to look at, it doesn't make the final call.

**Part B — Out-of-sample rule behavior.** Whether the mechanism is *correct* is not answerable on the season it was fitted against — checking that a rule built to catch a specific player's miss does in fact catch that miss is close to tautological (code written to move Embiid moves Embiid; that's not independent evidence). It's answerable on seasons that have their own instances of the pattern the rule targets, independent of what motivated the rule's design. Concretely for availability: does the rule fire on the real availability misses in the *other* exact-league benchmarks, using their own independently-computed `BREAKOUT_AVAILABILITY_LABEL` diagnostics as ground truth (not hand-picked examples)? Does it fire on anyone it shouldn't (particularly `availability undertrust` cases, where firing would actively hurt)? Unlike the targeted-player check, this can come back negative — and did (see below): it's a genuine test of generalization, not tuning.

### Issue #2 outcome, evaluated against the new criterion (2026-08-14)

The 80%/30% aggregate gate failed as designed and was correctly not overridden — `pct_improved` on Spearman came in at 67.6% / 42.1% / 22.5% across the three seasons, with all three deltas' 95% CIs straddling zero (noise, not signal, at the pool level). The original "~5 affected players" estimate behind 80% was wrong for what got built: `compute_availability_risk_factor` fires for exactly 1 player in the real 130-player pool (Embiid, `AVAILABILITY_RISK_FACTOR` 0.893, moving #17→#20 toward a true #91 finish).

Evaluated instead against the replacement criterion:

- **Exclusion counters:** 0 before-only / 0 after-only on all three benchmarks (72/87/98 matched, unchanged) — the qualifying player set did not shift, so the paired comparison above was measuring what it claimed to, cleanly.
- **Part A, collateral damage:** `--target-players "Joel Embiid"` flags exactly 1 non-target player across all three benchmarks — Josh Hart, rank 20→18, `TOTAL_VALUE` 2.0974→2.1051 (+0.4%). This is the Box-Cox renormalization ripple described above, not a real change to Hart's own evaluation (his own factors are unchanged). No genuine collateral damage found.
- **Part B, out-of-sample rule behavior:** checked directly against `identity.py`/`model.py` on the peer's branch (3509eef), not against the peer's own report of it. Pulled every `availability overtrust` (real chronic-miss pattern) and `availability undertrust` (firing here would hurt) player from the 2024-25 and 2023-24 benchmarks' own `BREAKOUT_AVAILABILITY_LABEL` diagnostics — seasons the rule was not fitted against — and ran `compute_availability_risk_factor` on each player's actual raw BBR games-played, independent of the model's own cached output:
  - 14 independently-diagnosed `availability overtrust` misses across the two seasons (Luka Dončić, Scottie Barnes, Kristaps Porziņģis, Andrew Wiggins, Anthony Davis, Julius Randle, Tyrese Maxey, Jimmy Butler, P.J. Washington, Bilal Coulibaly, Kawhi Leonard, RJ Barrett, Paul George, Kelly Oubre Jr.) — **the rule fired on 0 of them.** Several sit close to the threshold (Porziņģis 0.51/0.70, Kawhi 0.45/0.83, George exactly 0.50/0.90) but none has *both* loaded seasons under the 41/82 cutoff, which the rule requires by design (recurring, not one bad season).
  - 15 `availability undertrust` cases (where firing would actively hurt, including LaMelo Ball — the one false positive that drove the earlier, looser-threshold gate failure) — **the rule fired on 0 of them.** Zero false positives, confirmed against the full 130-player pool, not just this list.
  - Net: the mechanism is precise (no false positives anywhere in the pool) but does not generalize — it caught 1 of 15 real chronic-availability misses across the three exact-league seasons combined (Embiid only), missing the other 14 entirely.
- **Scope note:** this is not a temporal walk-forward backtest (re-projecting as of a date before 2023-24/2024-25 began) — the repo only holds 2 BBR season files, so a genuine "what would the model have said before that season started" test isn't currently possible without new historical GP data. What was checked is the rule's real, current output against independently-diagnosed misses in two seasons it wasn't fitted against, which answers the question this criterion was designed to ask (does it fire correctly outside the fitted case) without requiring new data ingestion.

No ship/no-ship call is recorded here — that's a decision for the repo owner, not something this ADR or the tooling decides for them.

## Consequences

- 2025-26 is no longer a virgin holdout — it was partially spent validating issue #1, and every future decision made while watching it spends more. All three exact-league seasons are a depleting resource; evaluating across all three (not just the freshest) is deliberate, not incidental.
- A plan doc that doesn't declare a numeric threshold before implementation isn't ready to implement against this criterion.
- Both bootstrap modes use a fixed default seed (42) for reproducibility; re-running `--noise-floor` or `--bootstrap` against unchanged inputs reproduces the same bands exactly.
