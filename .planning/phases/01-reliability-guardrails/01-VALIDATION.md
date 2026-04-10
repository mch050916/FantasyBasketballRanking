---
phase: 01
slug: reliability-guardrails
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | unittest |
| **Config file** | none — standard library discovery |
| **Quick run command** | `python -m unittest discover -s tests` |
| **Full suite command** | `python -m unittest discover -s tests` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m unittest discover -s tests`
- **After every plan wave:** Run `python -m unittest discover -s tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | DATA-01 | T-01-01 / T-01-02 | Invalid or stale caches rebuild automatically instead of being trusted | unit | `python -m unittest discover -s tests` | ✅ | ⬜ pending |
| 01-01-02 | 01 | 1 | DATA-01 | T-01-01 / T-01-02 | Game-log and TECH cache reads validate metadata and recover from malformed payloads | unit | `python -m unittest discover -s tests` | ✅ | ⬜ pending |
| 01-02-01 | 02 | 2 | DATA-02 | T-01-03 | Missing requested player-season logs produce an explicit degraded-run signal | unit | `python -m unittest discover -s tests` | ✅ | ⬜ pending |
| 01-02-02 | 02 | 2 | VAL-02 | T-01-04 | Validation returns explicit health state for no-match and weak-match outcomes | unit | `python -m unittest discover -s tests` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
