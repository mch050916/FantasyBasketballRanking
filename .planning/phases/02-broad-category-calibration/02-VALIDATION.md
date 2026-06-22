---
phase: 02
slug: broad-category-calibration
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for broad category calibration.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | unittest |
| **Config file** | none — standard library discovery |
| **Quick run command** | `python -m unittest discover -s tests` |
| **Full suite command** | `python -m unittest discover -s tests` |
| **End-to-end command** | `python -u main.py` |
| **Estimated runtime** | ~10-20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m unittest discover -s tests`
- **After every plan wave:** Run `python -m unittest discover -s tests`
- **Before `/gsd-verify-work`:** Full suite and one end-to-end run must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | CCAL-01 | T-02-01 | Remaining milestone distortion is reduced through bounded, explainable calibration rather than a blunt rewrite | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | CCAL-01 | T-02-02 | `DD` and `TD` calibration stays bounded and regression-tested | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | CCAL-02 | T-02-03 | Exact-league snapshots remain the primary acceptance surface when rerun deltas are judged | unit + e2e | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | CCAL-03 | T-02-04 | Residual balanced-category follow-up is evidence-gated and leaves a measurable diagnostic trail | unit + e2e | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing `unittest` coverage, baseline-history support, and category-distortion artifacts are sufficient for this calibration phase.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A normal `python main.py` run still reads like an exact-league-first calibration judgment rather than generic benchmark noise | CCAL-02 | Requires evaluating the reporting emphasis and whether the rerun summary clearly prioritizes the right surface | Run `python main.py` and inspect the benchmark delta and category-distortion sections. Confirm the exact-league snapshots are still the primary acceptance story and Yahoo remains a secondary sanity check |
| Residual `balanced category carry` follow-up, if applied, feels targeted rather than like a broad opaque rebalance | CCAL-03 | Requires human judgment about calibration scope and explainability | Inspect the updated category-distortion summary and exact-league top misses after rerun. Confirm any second-pass adjustment is framed as a narrow evidence-backed follow-up |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or existing coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
