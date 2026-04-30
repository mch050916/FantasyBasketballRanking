---
phase: 03
slug: miss-diagnostics
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-28
---

# Phase 03 — Validation Strategy

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
| 03-01-01 | 01 | 1 | PROJ-04 | T-03-01 | Current benchmark metrics are compared only against the most recent baseline for the same target | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 03-01-02 | 01 | 1 | PROJ-04 | T-03-02 | Baseline artifacts are saved deterministically and do not silently disappear between runs | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 03-02-01 | 02 | 2 | VAL-03 | T-03-03 | Biggest-miss artifacts contain compact explanatory context rather than opaque rank-only output | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 03-02-02 | 02 | 2 | VAL-03 | T-03-04 | Miss buckets remain deterministic and interpretable rather than fuzzy or overfit | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CLI diagnostics remain readable while richer details move to saved artifacts | VAL-03 / PROJ-04 | Human judgment on readability | Verified with `python -u main.py`: console output stayed compact while richer details were saved to `diagnostics/benchmark_history.csv` and `diagnostics/top_misses/*.csv` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
