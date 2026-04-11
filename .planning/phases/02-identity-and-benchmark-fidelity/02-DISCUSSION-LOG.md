# Phase 2: Identity And Benchmark Fidelity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 02-identity-and-benchmark-fidelity
**Areas discussed:** Player identity source of truth, Missing-season benchmark policy, Historical benchmark trust rules, Benchmark matching strictness

---

## Player identity source of truth

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic normalization + manual override map | Keep normalized-name matching but add a small explicit mapping layer for edge cases and known cross-source mismatches. | ✓ |
| Player-ID-first matching where available | Carry provider IDs when available, with name fallback only when IDs are missing. | |
| Name-only matching with stronger fuzzy heuristics | Stay name-based but add more aggressive heuristics for suffixes, punctuation, and near-matches. | |

**User's choice:** Deterministic normalization + manual override map  
**Notes:** Chosen as the best balance between correctness and complexity for the current codebase.

---

## Missing-season benchmark policy

| Option | Description | Selected |
|--------|-------------|----------|
| Expected-missing allowlist by player profile | Treat older-season absence as expected when the player was not yet in the league, and exclude those cases from degraded-run warnings. | ✓ |
| Always count missing seasons as degraded | Keep every missing requested pair in degraded-run output, even if the player could not have data for that season. | |
| Silence all older-season misses automatically | Suppress older-season misses whenever the player appears in the recent season. | |

**User's choice:** Expected-missing allowlist by player profile  
**Notes:** The user wants honest degraded-run reporting, but not noisy warnings for players who simply were not in the NBA yet.

---

## Historical benchmark trust rules

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered benchmark trust labels | Keep both snapshot and direct-export benchmarks, but label them as different trust tiers. | ✓ |
| Treat all benchmarks equally | Present all benchmark files as equivalent in trust. | |
| Disable screenshot-derived benchmarks | Remove lower-confidence historical snapshots until direct exports exist. | |

**User's choice:** Tiered benchmark trust labels  
**Notes:** Historical snapshots remain useful, but they should be presented as lower-trust than direct CSV exports.

---

## Benchmark matching strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic only, explicit fallback order | Match in a strict order: override map, then normalized-name match, otherwise no match. | ✓ |
| Add fuzzy fallback for unmatched names | Use fuzzy matching after deterministic attempts fail. | |
| Strict exact override only | Only trust explicit overrides and fail everything else unmatched. | |

**User's choice:** Deterministic only, explicit fallback order  
**Notes:** The user preferred trust and explainability over squeezing out more match count via fuzzy heuristics.

---

## the agent's Discretion

- Exact implementation structure for the override map and benchmark trust-tier metadata.
- How to present trust-tier labels as long as snapshot vs direct-export confidence stays explicit.

## Deferred Ideas

- Full provider-ID unification across all sources.
- Fuzzy benchmark matching.
