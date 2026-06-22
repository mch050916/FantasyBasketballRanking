# Phase 10 Discussion Log

### Topic: Verification artifact format

- Decision: Use markdown-first verification artifacts.
- Rationale: The repo already uses readable planning documents heavily, and this phase is about durable human-auditable evidence more than machine-driven analytics.

### Topic: Non-actionable suppression registry

- Decision: Store non-actionable suppressions in one explicit on-disk registry.
- Rationale: Future seasonal review should not require rediscovering policy from code branches and console output.

### Topic: Suppression expiration

- Decision: Make suppressions season-scoped and require reaffirmation in later seasons.
- Rationale: These cases are inherently season-specific and should not become permanent behavior accidentally.

### Topic: Review surface

- Decision: Surface maintenance needs in both normal run health and a dedicated maintenance artifact.
- Rationale: The user should see relevant reminders during normal runs, but also have a more deliberate long-term review surface on disk.

### Topic: Evidence scope

- Decision: Backfill current milestone debt in a reusable pattern for future phases too.
- Rationale: The highest-value outcome is fixing today’s missing evidence while improving the workflow permanently.
