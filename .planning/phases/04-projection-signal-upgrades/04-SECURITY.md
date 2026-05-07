---
phase: 04
slug: projection-signal-upgrades
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-30
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| player season stats → composite trend score | Multiple season-level box-score signals are combined into one bounded trend profile without silently reverting to a points-only heuristic | Local Basketball Reference per-player season data |
| role growth signal → recent-season weight | Minutes/role growth can increase recent-season trust, but the extra boost must stay capped and auditable | Derived local projection metadata |
| age signal + recent trend → decline adjustment | Veteran decline logic must distinguish true decline alignment from simple player age | Local age column plus derived trend score |
| projection-signal changes → benchmark delta interpretation | Benchmark rerun output must remain trustworthy enough to judge whether the phase helped or hurt | Local diagnostics history and validation artifacts |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-04-01 | I | `compute_trend_profile()` composite logic | mitigate | [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) now uses an explicit approved stat set with clipped relative changes and returns one normalized weight path; covered by [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) non-points-growth regression | closed |
| T-04-02 | T | role-change breakout adjustment | mitigate | [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) caps `role_boost` and `RECENT_WEIGHT_MAX`; covered by bounded-responsiveness tests in [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) | closed |
| T-04-03 | I | decline adjustment path | mitigate | [model.py](/Users/chesterman/FantasyBasketballRanking/model.py) gates stronger decline on both age and negative composite trend, keeping age-only fade light; covered by decline-alignment regression tests in [tests/test_model.py](/Users/chesterman/FantasyBasketballRanking/tests/test_model.py) | closed |
| T-04-04 | T | benchmark rerun interpretation | mitigate | [main.py](/Users/chesterman/FantasyBasketballRanking/main.py) and [validate.py](/Users/chesterman/FantasyBasketballRanking/validate.py) retain Phase 3 baseline-delta reporting and updated miss artifacts; verified by rerunning `python -u main.py` and recorded in [04-02-SUMMARY.md](/Users/chesterman/FantasyBasketballRanking/.planning/phases/04-projection-signal-upgrades/04-02-SUMMARY.md) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

No accepted risks.

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-30 | 4 | 4 | 0 | Codex |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-30
