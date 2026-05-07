# Phase 05 Discussion Log

## 2026-04-30

### Topic: Calibration target

- Decision: Optimize for exact-league 14-cat historical snapshots first.
- Rationale: The tool exists to beat generic Yahoo ordering for this specific league, so league-specific validation should be the primary judge.

### Topic: Adjustment shape

- Decision: Use weight + scaling calibration.
- Rationale: Lowering the weights alone may not fix how strongly extreme `DD`/`TD` producers separate from the field.

### Topic: DD vs TD treatment

- Decision: Calibrate `DD` and `TD` separately.
- Rationale: `TD` is rarer and likely needs a different compression/weight behavior than `DD`.

### Topic: Success criteria

- Decision: Exact-league benchmark improvement is the primary success criterion.
- Rationale: Yahoo-based benchmarks remain useful sanity checks, but they are not the product target.
