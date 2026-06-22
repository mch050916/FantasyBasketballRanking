---
phase: 01
slug: category-distortion-diagnostics
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-09
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for category-distortion diagnostics.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | unittest |
| **Config file** | none — standard library discovery |
| **Quick run command** | `python -m unittest discover -s tests` |
| **Full suite command** | `python -m unittest discover -s tests` |
| **Estimated runtime** | ~10-15 seconds |

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
| 01-01-01 | 01 | 1 | CBAL-01 | T-01-01 | Repeated exact-league distortion evidence is grouped into durable family-level output instead of being left as scattered player rows | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 01-01-02 | 01 | 1 | CBAL-02 | T-01-02 | The saved family artifact stays compact and comparable to the current diagnostics surface | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 01-02-01 | 02 | 2 | CBAL-01 | T-01-03 | Console output surfaces interpretable distortion families without replacing existing miss artifacts | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 01-02-02 | 02 | 2 | CBAL-02 | T-01-04 | Only repeat-supported exact-league distortion families are elevated as “real” diagnostic signals | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing `unittest` coverage and current validation helpers are sufficient for this diagnostic phase.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A normal `python main.py` run now surfaces category-distortion families that read like actionable calibration targets | CBAL-01 | Requires judging whether the summary is understandable and useful, not only mechanically present | Run `python main.py` and inspect the exact-league validation blocks. Confirm the new family-level summary is readable, compact, and clearly tied to repeated exact-league miss patterns |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or existing coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
