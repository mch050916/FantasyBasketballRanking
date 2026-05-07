---
phase: 08
slug: nba-api-resolution-hardening
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-07
---

# Phase 08 — Validation Strategy

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

## Wave 0 Requirements

- Existing infrastructure covers this phase’s initial testing needs.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | DRES-01 | T-08-01 | Remaining stubborn players flow through one explicit deterministic resolution/classification path instead of ad hoc fetch-loop behavior | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | DRES-01, DRES-02 | T-08-02 | Only narrowly classified non-actionable misses are suppressed; current-season failures remain prominent by default | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 08-02-01 | 02 | 2 | DRES-02 | T-08-03 | Run health distinguishes current-season unresolved misses from older-season or explicitly non-actionable cases | unit + rerun | `python -m unittest discover -s tests` and `python main.py` | ✅ | ✅ green |
| 08-02-02 | 02 | 2 | DRES-03 | T-08-04 | Reruns show whether true degraded current-season misses improved after resolution changes without masking real failures | unit + rerun | `python -m unittest discover -s tests` and `python main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The run-health summary feels more honest and more actionable after the resolution changes | DRES-02, DRES-03 | Severity and classification messaging are partly UX behaviors | Run `python main.py` and confirm current-season unresolved misses stand out clearly from suppressed or expected historical gaps |
| A known stubborn player is either deterministically resolved or explicitly classified with a narrow reason instead of disappearing silently | DRES-01 | Requires reasoning about the user-facing data-path outcome | Inspect the rerun summary and relevant test fixtures for a stubborn case like `Jimmy Butler`, `Bojan Bogdanovic`, or `Saddiq Bey` |

---

## Validation Sign-Off

- [x] All tasks have automated verification or explicit Wave 0/manual coverage
- [x] Sampling continuity remains under 15s feedback latency
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
