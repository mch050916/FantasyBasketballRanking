---
phase: 04
slug: projection-signal-upgrades
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-30
---

# Phase 04 — Validation Strategy

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
| 04-01-01 | 01 | 1 | PROJ-01 | T-04-01 | Composite trend scoring reflects broader multicategory change instead of points-only movement | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 04-01-02 | 01 | 1 | PROJ-01 | T-04-02 | Extra role-change boost is bounded and does not allow one recent season to dominate weights fully | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 04-02-01 | 02 | 2 | PROJ-02 | T-04-03 | Older players are discounted through a modest decline path only when age and negative trend align | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 04-02-02 | 02 | 2 | PROJ-01 / PROJ-02 | T-04-04 | Projection-signal changes preserve measurable benchmark rerun comparisons through Phase 3 diagnostics | unit + rerun | `python -m unittest discover -s tests` and `python -u main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Projection changes improve at least some benchmark deltas without making the output obviously unstable | PROJ-01 / PROJ-02 | Requires judgment across multiple benchmark outputs | Run `python -u main.py` and inspect the Phase 3 delta blocks plus top-miss artifacts to confirm the new signal behavior appears directionally sensible |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
