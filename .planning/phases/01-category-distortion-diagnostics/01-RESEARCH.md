## User Constraints

### Implementation Decisions

- **D-01:** Diagnose category distortion from the exact-league 14-cat snapshots first, with Yahoo as secondary context.
- **D-02:** Attribute distortion through broad category families first, with raw category evidence underneath.
- **D-03:** Produce both a console summary and a saved diagnostic artifact.
- **D-04:** Only treat a distortion family as real when it repeats across the exact-league snapshot surface or shows strongly in one with directional support in the other.
- **D-05:** Keep representative player context compact because deeper detail already exists in current miss and milestone artifacts.

### The Agent's Discretion

- Exact family names and how many top families to surface.
- Exact saved artifact format, as long as it stays compact and comparable across runs.
- Whether the family-level summary is built directly from validation details, top-miss artifacts, or a hybrid of both.

### Deferred Ideas

- Actual category recalibration or weight changes.
- A full redesign of the current miss-bucket system.
- New benchmark sources or new ingestion flows.

## Project Constraints (from AGENTS.md)

- Stay in the current Python CLI architecture.
- Preserve the existing benchmark and diagnostics loop instead of creating a parallel evaluation surface.
- Keep exact-league 14-cat usefulness as the primary acceptance target.
- Prefer small explicit helpers and compact artifacts over sprawling output dumps.

## Standard Stack

- Python 3.12 remains the runtime target. [VERIFIED]
- `pandas`, `pathlib`, and `unittest` remain sufficient for artifact derivation and regression coverage. [VERIFIED]
- Existing diagnostics artifacts already live under `diagnostics/` and current validation logic already runs through `validate.py` and `main.py`. [VERIFIED]

## Architecture Patterns

- [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) already computes top-miss artifacts, miss-bucket summaries, and milestone-contribution summaries. [VERIFIED]
- [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) already persists benchmark-history, top-miss, and milestone-contribution artifacts as part of the normal run loop. [VERIFIED]
- Exact-league-first tuning is an established pattern from Phase 5, so this phase should reuse the same acceptance hierarchy rather than broadening the surface. [VERIFIED from `.planning/phases/05-category-calibration/05-CONTEXT.md`]

## Current Gaps

- There is no family-level diagnostic artifact for category-balance distortion today. [VERIFIED]
- The current `category-weight distortion` bucket is too coarse to tell which category families are actually driving repeated exact-league misses. [VERIFIED]
- The current console output shows miss buckets and DD/TD contribution, but not a broader category-family diagnosis that can directly inform the next calibration phase. [VERIFIED]

## Don't Hand-Roll

- Do not recalibrate weights or scoring logic in this phase.
- Do not treat Yahoo benchmarks as co-equal to the exact-league snapshots for deciding what counts as distortion.
- Do not replace the existing miss artifacts; layer the new diagnosis on top of them.
- Do not produce a verbose full-category dump in the main console surface.

## Common Pitfalls

- If distortion families are too raw-category-specific, the next calibration phase will inherit a noisy target instead of an interpretable one.
- If the evidence threshold is too weak, single-snapshot noise will look like a systemic distortion family.
- If the artifact is only human-readable console output, the next phase loses the durable evidence loop it needs.
- If the family summary is disconnected from current top-miss and contribution artifacts, it will be harder to trust and maintain.

## Validation Architecture

- Plan 1 should define the distortion-family taxonomy and produce a saved artifact from the existing validation details and miss outputs.
- Plan 2 should integrate the family-level summary into the normal CLI validation surface and lock the behavior with regression coverage.
- Continue automated verification with `python -m unittest discover -s tests`.
- Keep at least one manual phase check centered on whether repeated exact-league distortion families are now visible and understandable without opening raw CSV internals.

## Planning Notes

- The cleanest split is:
  1. derive and persist the category-distortion family artifact from existing validation evidence;
  2. surface the family summary in the run output and regression-test the repeat-signal behavior.
- This phase should make the next calibration phase easier to target, not change ranking outputs directly.
