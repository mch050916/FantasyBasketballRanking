# Technology Stack

**Analysis Date:** 2026-04-10

## Languages

**Primary:**
- Python 3.12 - the entire application pipeline, tests, and utility scripts in `main.py`, `config.py`, `data.py`, `model.py`, `output.py`, and `validate.py`.

**Secondary:**
- CSV - season totals, validation snapshots, and exported rankings in the repo root.
- Pickle - cached NBA API responses in `game_log_cache.pkl` and `tech_cache.pkl`.

## Runtime

**Environment:**
- CPython 3.12 - the local virtual environment metadata in `.venv/pyvenv.cfg` points to Python 3.12.

**Package Manager:**
- `pip` with a project virtual environment created via `python3 -m venv .venv`.
- Lockfile: missing.

## Frameworks

**Core:**
- No web framework detected.
- `pandas>=2.0.0` - tabular data loading, cleaning, projection assembly, and CSV output in `data.py`, `model.py`, `output.py`, and `validate.py`.
- `numpy>=1.24.0` - numeric operations, clipping, and weighted calculations in `data.py` and `model.py`.
- `scipy>=1.10.0` - statistical helpers for ranking validation and distribution transforms in `model.py` and `validate.py`.

**Testing:**
- `unittest` - the suite in `tests/test_data.py`, `tests/test_model.py`, and `tests/test_validate.py`.

**Build/Dev:**
- `tabulate>=0.9.0` - console table formatting in `output.py`.
- `nba_api>=1.4.0` - external NBA data access in `data.py`.

## Key Dependencies

**Critical:**
- `nba_api>=1.4.0` - fetches player game logs and league-wide foul statistics from the NBA stats service.
- `pandas>=2.0.0` - reads Basketball Reference exports, manipulates season tables, and writes rankings CSVs.
- `numpy>=1.24.0` - supports projection math and statistical transforms.
- `scipy>=1.10.0` - provides Spearman correlation for validation and Box-Cox support in `model.py`.

**Infrastructure:**
- `tabulate>=0.9.0` - renders the top-30 rankings table for terminal output.
- Standard library modules - `pathlib`, `pickle`, `time`, `re`, and `unicodedata` are used for file handling, caching, retries, and name normalization.

## Execution Surface

- `main.py` is the entry point and orchestrates loading, fetching, projection, scoring, validation, and CSV export.
- `config.py` centralizes league settings, category weights, thresholds, and cache file names.
- `data.py` owns all external data ingestion and cache management.
- `model.py` contains the projection math and DURANT scoring logic.
- `output.py` formats the top rankings table and saves the final CSV.
- `validate.py` compares produced rankings against known ranking files.

## Data Model

- Season totals are stored as raw Basketball Reference CSVs in the repo root, then normalized to per-game features in `data.py`.
- Game logs are cached locally as pickle files keyed by season and player name.
- Final rankings are written as `durant_rankings_2025_26.csv` in the repo root.

## Operational Notes

- The project is designed to run from a local checkout with no deploy target detected.
- There is no package metadata file such as `pyproject.toml` or `package.json`; dependency management is explicit in `requirements.txt`.
