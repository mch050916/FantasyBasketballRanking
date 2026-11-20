# Rookie board implementation handoff

**Date:** 2026-11-15
**Status:** Measurements complete, implementation not started

## What's done

1. **Part 1 measurements** (Parts 1a/1b/1c): complete, output at
   `/private/tmp/claude-501/-Users-chesterman-FantasyBasketballRanking/e9a97047-58c1-4c1d-9297-9b4071fb2884/scratchpad/measurement_output.txt`

2. **M1-M4 measurements**: complete, output at
   `/private/tmp/claude-501/-Users-chesterman-FantasyBasketballRanking/e9a97047-58c1-4c1d-9297-9b4071fb2884/scratchpad/m1_m4_output.txt`

3. **Spec updated** with M1-M4 results and decision rules:
   `docs/superpowers/specs/2026-11-15-rookies-on-the-draft-board.md`

4. **Measurement scripts** in scratchpad (need to move to `scripts/`):
   - `scratchpad/rookie_measurement.py` → `scripts/rookie_measurement.py`
   - `scratchpad/rookie_measurement_m1_m4.py` → `scripts/rookie_measurement_m1_m4.py`

## Decision rules that fired

- **R1**: Method (iv) — market places rookies with ADP, model places the rest
  - M1 excl 2024-25: Market TOT MARE=28.2 < Model TOT MARE=36.3 on ADP rookies
- **R2**: Veteran gp_shrink (0.5) for rookie GP_FACTOR; no cap
  - M4: all three GP rules give identical TOT MARE=24.9
- **R3**: DD/TD stay at 0
- **R4**: No pick curve change; M3 recorded (picks 1-5 placed +17 PG / +28 TOT too low)

## What remains: implementation

### Critical detail: value scale

Veteran `projected` category values = `per_game_rate * GP_FACTOR` (verified empirically).
Rookie extra_rows need: `cat_value = predicted_per_game_rate * shrunk_GP_FACTOR`
where `shrunk_gpf = (1 - 0.5) * predicted_gpf + 0.5 * pool_mean_gpf`

### main.py changes needed

1. Add `build_rookie_extra_rows(projected, draft_history, combine_stats, fitted_model, config)`:
   - For each rookie (picks 1-60, not in projected): predict stats, apply gp_shrink to GP_FACTOR
   - Scale counting cats: `value = per_game_rate * shrunk_gpf`
   - FG% as-is; DD=0, TD=0, TECH=TECH_DEFAULT
   - Return DataFrame matching projected schema (PLAYER_NAME, cats, GP_FACTOR, MIN, FGA)

2. After `run_projection()`, before `add_market_blend`:
   - Build rookie extra_rows + roster extra_rows
   - Call compute_g_scores with combined extra_rows
   - BOARD_RANK = RANK from combined output
   - Restore veteran RANK from original rankings; rookie RANK = NaN
   - Add ROOKIE flag, OVERALL_PICK

3. Modify `add_market_blend` for method (iv):
   - Use BOARD_RANK instead of RANK for blend base
   - Rookies with ADP: BLEND_RANK = MARKET_RANK alone
   - Others: BLEND_RANK = 0.5 * BOARD_RANK + 0.5 * MARKET_RANK

4. Keep separate rookie file (user's call to retire)
5. `--per-game`: leave rookies out
6. Save current file as `_before_rookies.csv` before overwriting

### Tests needed (tests/test_rookie_integration.py)

1. Veteran rows unchanged: TOTAL_VALUE and *_G columns identical with/without rookie extra_rows
2. Rookie G-score equivalence: same stat line → same G-scores
3. Method (iv) fixture: rookie with ADP gets BLEND_RANK from market alone

### Acceptance criterion

Walk-forward via measurement script reproduces M2 method (iv) numbers within 0.01 Spearman / 1 rank MARE, veteran rows byte-identical.

### Final output to report

- Run `python main.py` once after implementation
- Report 2026 class placements (Boozer, Dybantsa, Wilson, Peterson, rest of lottery)
- Count veteran BLEND_RANK changes vs current file

## Constraints

- No git commit/push; write files + hand over commit summary
- No edits to config.py, model.py, backtest.py, CLAUDE.md, permissions
- 2026-27 outcomes untouched
