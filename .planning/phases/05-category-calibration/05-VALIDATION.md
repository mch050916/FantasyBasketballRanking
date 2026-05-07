---
phase: 05
slug: category-calibration
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-30
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | unittest |
| **Config file** | none — standard library discovery |
| **Quick run command** | `python -m unittest discover -s tests` |
| **Full suite command** | `python -m unittest discover -s tests` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m unittest discover -s tests`
- **After every plan wave:** Run `python -m unittest discover -s tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PROJ-03 | T-05-01 | `DD` and `TD` contribution can be inspected explicitly against current misses instead of inferred from raw category totals | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | PROJ-03 | T-05-02 | Exact-league benchmark diagnostics can surface `DD`/`TD` distortion evidence without rewriting the whole validation loop | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 05-02-01 | 02 | 2 | PROJ-03 | T-05-03 | `DD` and `TD` are calibrated separately with bounded scaling/weight changes rather than one blunt joint reduction | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 05-02-02 | 02 | 2 | PROJ-03 | T-05-04 | Calibration stays measurable through the benchmark rerun loop and exact-league historical snapshots remain the primary decision surface | unit + rerun | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Exact-league benchmarks improve in a way consistent with reduced `DD`/`TD` distortion, even if Yahoo-style benchmarks only move sideways | PROJ-03 | Requires judging primary vs secondary benchmark tradeoffs | Run `python -u main.py` and compare the exact-league 14-cat delta blocks plus updated top-miss artifacts before accepting the calibration |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
