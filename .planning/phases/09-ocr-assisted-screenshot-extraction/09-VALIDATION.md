---
phase: 09
slug: ocr-assisted-screenshot-extraction
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-07
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for OCR-assisted screenshot extraction.

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

## Wave 0 Requirements

- Existing `unittest` coverage is sufficient to protect the current ingestion contract while Phase 9 extends it.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-----------------|-----------|-------------------|--------|
| 09-01-01 | 01 | 1 | OCR batch input flows through one explicit adapter boundary instead of ad hoc per-backend logic | unit | `python -m unittest discover -s tests` | ✅ green |
| 09-01-02 | 01 | 1 | One season screenshot batch maps deterministically to one OCR ingestion result set and one review-table output path | unit | `python -m unittest discover -s tests` | ✅ green |
| 09-02-01 | 02 | 2 | OCR output lands in the existing review-table contract without creating a second schema | unit | `python -m unittest discover -s tests` | ✅ green |
| 09-02-02 | 02 | 2 | OCR confidence remains separate from reviewed row confidence | unit | `python -m unittest discover -s tests` | ✅ green |
| 09-02-03 | 02 | 2 | Partial OCR rows are preserved for review instead of being silently skipped | unit | `python -m unittest discover -s tests` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|------------|-------------------|
| A real season screenshot batch now lands in one review table with fewer manual prep steps than the pre-Phase-9 flow | Requires checking the user-facing ingestion ergonomics on real image inputs | Run the OCR-assisted ingestion flow on one season screenshot batch and confirm it creates one review table with season/source-batch context and reviewable partial rows |
| OCR uncertainty is visible but does not get promoted to benchmark trust automatically | Requires checking the human-facing trust semantics rather than only schema behavior | Inspect the produced review table and confirm OCR-side confidence fields exist while reviewed trust fields remain pending/unapproved until human confirmation |

---

## Validation Sign-Off

- [x] All planned tasks have automated verification or explicit manual coverage
- [x] Sampling continuity remains under 15s feedback latency
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
