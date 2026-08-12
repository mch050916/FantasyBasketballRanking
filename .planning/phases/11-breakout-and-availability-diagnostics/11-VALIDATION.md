---
phase: 11
slug: breakout-and-availability-diagnostics
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-03
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for breakout and availability diagnostics.

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
| 11-01-01 | 01 | 1 | BAV-01 | T-11-01 | Misses are classified into the locked breakout/availability label set with deterministic evidence rules | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 11-01-02 | 01 | 1 | BAV-02 | T-11-02 | Per-benchmark artifacts preserve richer context without replacing existing top-miss artifacts | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 11-02-01 | 02 | 2 | BAV-01 | T-11-03 | Cross-benchmark summary keeps exact-league snapshots primary and Yahoo secondary | unit + e2e | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |
| 11-02-02 | 02 | 2 | BAV-02 | T-11-04 | Console output adds compact breakout/availability reporting without removing existing diagnostics | unit + e2e | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing `unittest` coverage and diagnostic artifact conventions are sufficient.
- No model-side validation is required because Phase 11 is diagnostic only.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Normal `python main.py` output remains readable after adding the new diagnostic block | BAV-01, BAV-02 | Requires judging console clarity, not just file existence | Run `python main.py` and confirm the breakout/availability summary is compact, exact-league-first, and additive beside miss buckets, DD/TD contribution, and category-distortion sections |
| Saved artifacts provide enough context for Phase 12 and Phase 13 planning | BAV-02 | Requires judging usefulness of the columns and reason strings | Inspect `diagnostics/breakout_availability/` after a run and confirm the CSVs explain player labels clearly enough to guide later calibration |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or existing coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
