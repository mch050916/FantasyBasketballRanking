---
phase: 06
slug: screenshot-benchmark-ingestion
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-07
---

# Phase 06 — Validation Strategy

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
| 06-01-01 | 01 | 1 | INGEST-01 | T-06-01 | Screenshot-derived rows land in one explicit review-table schema instead of ad hoc CSV shape drift | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 06-01-02 | 01 | 1 | INGEST-01 | T-06-02 | One screenshot batch maps deterministically to one season-specific review table | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 06-02-01 | 02 | 2 | INGEST-02 | T-06-04 | Reviewed rows normalize into validation-ready seasonal benchmark CSVs that fit the existing validation path | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 06-02-02 | 02 | 2 | INGEST-02 | T-06-03 | Pending rows cannot silently generate trusted benchmark files | unit | `python -m unittest discover -s tests` | ✅ | ✅ green |
| 06-02-03 | 02 | 2 | INGEST-02 | T-06-04 | Historical snapshot targets in the main pipeline stay compatible with the canonical season filename convention | unit + rerun | `python -m unittest discover -s tests` and `python main.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A screenshot batch can be traced cleanly from source extraction through reviewed intermediate rows into one season-specific benchmark CSV | INGEST-01, INGEST-02 | Requires checking the human-facing review-table flow and file lineage | Run the ingestion path on a known screenshot batch and confirm the reviewed table and generated benchmark file both preserve the expected season and rank ordering |
| The workflow refuses to treat unreviewed screenshot rows as benchmark truth | INGEST-03 | Review-state enforcement is partly a workflow/UX behavior | Attempt benchmark generation from an unreviewed intermediate file and confirm the flow blocks or warns clearly |

---

## Validation Sign-Off

- [x] All tasks have automated verification or explicit Wave 0/manual coverage
- [x] Sampling continuity remains under 15s feedback latency
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
