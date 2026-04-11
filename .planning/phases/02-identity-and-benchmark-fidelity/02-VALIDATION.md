---
phase: 02
slug: identity-and-benchmark-fidelity
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 02 — Validation Strategy

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
| 02-01-01 | 01 | 1 | DATA-03 | T-02-01 / T-02-02 | Identity resolution uses a deterministic override-first rule instead of ambiguous fuzzy matching | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | DATA-03 | T-02-03 | Expected-missing older seasons do not create degraded-run noise for players who were not yet in the NBA | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | VAL-01 | T-02-04 | Benchmark targets carry explicit trust tiers and normalize direct-export vs snapshot handling in one path | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | VAL-01 | T-02-04 | Validation output remains deterministic and clearly labeled across exact-league and Yahoo-style benchmarks | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Benchmark trust labels read clearly in the CLI output | VAL-01 | Human judgment on wording/clarity | Verified with `python -u main.py`: exact-league snapshots print as `historical_snapshot / snapshot_derived` and Yahoo exports print as direct-export classes |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
