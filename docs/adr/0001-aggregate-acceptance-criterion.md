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

## Issue #2 threshold (availability calibration)

Declared before implementation starts:

- No season shows `pct_improved` below 30% on Spearman.
- At least two of the three seasons show `pct_improved` at or above 80%.

**Reasoning:**

- 80% rather than the conventional 95% is deliberate. Availability calibration's realistic ceiling is ~0.01–0.03 aggregate Spearman, because only about five of 72–98 matched players per season are availability misses (Embiid, Luka, Scottie Barnes, P.J. Washington, Porzingis). Demanding 95% would reject a genuine improvement of the size this issue can actually produce, and the predictable consequence is loosening the threshold after seeing results — the exact failure mode this ADR exists to prevent. 80% means "comfortably more likely real than not."
- The 30% floor is a regression guard. It catches the case where availability misses are fixed by systematically shading everyone else downward.
- This threshold is specific to issue #2's expected effect size. Issues with larger expected effects should declare a higher bar.

## Consequences

- 2025-26 is no longer a virgin holdout — it was partially spent validating issue #1, and every future decision made while watching it spends more. All three exact-league seasons are a depleting resource; evaluating across all three (not just the freshest) is deliberate, not incidental.
- A plan doc that doesn't declare a numeric threshold before implementation isn't ready to implement against this criterion.
- Both bootstrap modes use a fixed default seed (42) for reproducibility; re-running `--noise-floor` or `--bootstrap` against unchanged inputs reproduces the same bands exactly.
