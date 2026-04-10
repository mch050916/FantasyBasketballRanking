# Testing Patterns

**Analysis Date:** 2026-04-10

## Test Layout

- Tests live under `tests/` and follow the `test_*.py` naming pattern:
  - `tests/test_data.py`
  - `tests/test_model.py`
  - `tests/test_validate.py`
- The suite uses the standard library `unittest` framework.
- Each test module ends with `if __name__ == "__main__": unittest.main()` so the file can run directly.
- There is no repo-local `pytest` or `unittest` config file detected.

## Test Style

- Group related assertions inside `unittest.TestCase` subclasses.
- Import the target functions directly from the module under test.
- Keep tests focused on small helpers or deterministic transformation logic.
- Use in-memory fixtures instead of long setup chains when possible.

## Assertion Patterns

- Use exact equality for deterministic helpers and simple collections.
- Use `assertAlmostEqual` for floating-point projections and rank metrics.
- Use `assertIn`, `assertGreaterEqual`, and `assertLessEqual` for range and membership checks.
- Use `assertEqual` on lists when order matters, especially for normalized or ranked outputs.

## Fixture Patterns

- Build `pandas` DataFrames inline for model and validation tests.
- Use dictionaries of DataFrames to mimic `game_logs` input without hitting the NBA API.
- Use `tempfile.TemporaryDirectory()` for CSV-based validation tests that need a real file path.
- Keep fixtures minimal and domain-specific, with a single sample player or a small list of players.

## Coverage by Module

- `tests/test_data.py` covers:
  - accent and punctuation normalization
  - player ID resolution through exact and normalized lookups
  - missing cache/backfill pair detection
- `tests/test_model.py` covers:
  - `project_stats` handling of FG% as a true percentage
  - `compute_tau` derivation of TECH variance from PF-based weekly data
- `tests/test_validate.py` covers:
  - name normalization
  - CSV rank validation against normalized player keys
  - split-name column joining
  - metric-based rank construction

## Behavioral Themes

- Prefer pure-function testing where the input and output can be fully controlled.
- Test normalization and matching logic with accented player names because that is a core integration point across the repo.
- Test percentage math carefully so projections do not silently drift into totals or raw attempts.
- Test derived-stat behavior with narrow fixtures so the relationship is obvious in the assertion.

## What the Suite Avoids

- No tests hit the live NBA API.
- No tests depend on the Basketball Reference CSVs in the repo root.
- No tests rely on the generated cache pickles.
- No tests exercise the full `main.py` pipeline end to end.
- No tests currently cover console formatting in `output.py`.

## Practical Guidance For New Tests

- Add tests beside the existing modules in `tests/` and keep the file names aligned with the source file being covered.
- Prefer deterministic inputs and tiny fixtures over broad integration scaffolding.
- When a change touches file I/O, use temporary files or temporary directories instead of the real project artifacts.
- When a change touches ranking math, assert both the exact computed value and a sanity range.
- When a change touches name matching, include accented and punctuation-heavy names in the fixture set.
