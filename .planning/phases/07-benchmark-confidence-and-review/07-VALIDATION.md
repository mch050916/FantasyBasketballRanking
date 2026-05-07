---
phase: 07
slug: benchmark-confidence-and-review
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-07
---

# Phase 07 — Validation Strategy

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
| 07-01-01 | 01 | 1 | INGEST-03 | T-07-01 | Screenshot-derived rows carry explicit correction and confidence fields instead of implicit freeform cleanup | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 07-01-02 | 01 | 1 | INGEST-03, BTRUST-01 | T-07-02 | File-level readiness requires complete review, required fields, and sufficient confidence before a benchmark can be treated as ready | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 07-02-01 | 02 | 2 | BTRUST-01 | T-07-03 | Not-ready screenshot-derived benchmarks are skipped explicitly rather than validated silently | unit + rerun | `python -m unittest discover -s tests` and `python main.py` | ✅ | ✅ green |
| 07-02-02 | 02 | 2 | BTRUST-02 | T-07-04 | Generated benchmark artifacts carry maintainable provenance and confidence summary data season by season | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 07-02-03 | 02 | 2 | BTRUST-01, BTRUST-02 | T-07-03 | Validation/reporting distinguishes screenshot benchmark readiness/skip reasons from ordinary missing-file skips | unit + rerun | `python -m unittest discover -s tests` and `python main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A user can review a screenshot-derived season file with explicit correction/confidence columns and understand whether it is ready | INGEST-03, BTRUST-01 | Requires checking the human-facing CSV workflow rather than only unit behavior | Open a generated review table, inspect the correction/confidence fields, and confirm the readiness contract feels understandable and complete |
| A not-ready screenshot benchmark is skipped clearly without making the whole ranking pipeline feel broken | BTRUST-01 | Trust and messaging quality are partly UX behaviors | Run the pipeline with one intentionally not-ready screenshot benchmark and confirm the skip reason is explicit and distinct from a missing-file skip |

---

## Validation Sign-Off

- [x] All tasks have automated verification or explicit Wave 0/manual coverage
- [x] Sampling continuity remains under 15s feedback latency
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
