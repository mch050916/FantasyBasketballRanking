"""
benchmark_ingest.py — Screenshot-derived benchmark ingestion
============================================================
Helpers for turning semi-automatic screenshot extraction output into
reviewable intermediate tables, then into validation-ready benchmark CSVs.

Phase 6 intentionally stops short of raw OCR. The public entry points here
accept parsed rows from any extraction path, preserve the noisy text for
review, and enforce that only reviewed rows can become benchmark truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
import re

import pandas as pd


REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
VALID_REVIEW_STATUSES = {
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_REJECTED,
}
REVIEW_READY_MIN_CONFIDENCE = 0.80
CONFIDENCE_SUMMARY_HIGH = "high"
CONFIDENCE_SUMMARY_MIXED = "mixed"
CONFIDENCE_SUMMARY_LOW = "low"

REVIEW_TABLE_COLUMNS = [
    "SEASON",
    "SOURCE_BATCH",
    "SOURCE_ORDER",
    "RANK",
    "PLAYER_NAME",
    "RAW_OCR_NAME",
    "TEAM_TEXT",
    "REVIEW_STATUS",
    "CORRECTED_PLAYER_NAME",
    "CORRECTED_RANK",
    "ROW_CONFIDENCE",
    "REVIEW_NOTES",
    "OCR_CONFIDENCE",
]

BENCHMARK_SNAPSHOT_COLUMNS = [
    "Rank",
    "Player Name",
    "Season",
    "Source Batch",
]

BENCHMARK_METADATA_COLUMNS = [
    "Season",
    "Source Batch",
    "Review Total Rows",
    "Review Approved Rows",
    "Review Rejected Rows",
    "Review Pending Rows",
    "Missing Required Rows",
    "Low Confidence Rows",
    "File Confidence",
    "Confidence Summary",
    "Ready",
    "Ready Blockers",
    "Generated At",
]

REVIEW_TABLE_DEFAULTS = {
    "CORRECTED_PLAYER_NAME": "",
    "CORRECTED_RANK": pd.NA,
    "ROW_CONFIDENCE": pd.NA,
}


def season_to_snapshot_slug(season: str) -> str:
    """Convert season text like `2024-25` into `24_25` for filenames."""
    season = str(season).strip()
    if not season:
        raise ValueError("season is required")

    normalized = season.replace("/", "-").replace("_", "-")
    parts = [part for part in normalized.split("-") if part]
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"season must look like '2024-25' or '24-25', got {season!r}")

    left, right = parts
    return f"{left[-2:]}_{right[-2:]}"


def review_table_filename(season: str) -> str:
    """Return the canonical review-table filename for one season snapshot."""
    return f"actual_14cat_{season_to_snapshot_slug(season)}_review.csv"


def benchmark_snapshot_filename(season: str) -> str:
    """Return the canonical benchmark filename for one season snapshot."""
    return f"actual_14cat_{season_to_snapshot_slug(season)}_snapshot.csv"


def benchmark_metadata_filename(season: str) -> str:
    """Return the canonical benchmark metadata filename for one season snapshot."""
    return f"actual_14cat_{season_to_snapshot_slug(season)}_snapshot_metadata.csv"


def review_table_path(season: str,
                      directory: str | Path = "benchmarks/review_tables") -> Path:
    """Return the canonical review-table path for one season snapshot."""
    return Path(directory) / review_table_filename(season)


def benchmark_snapshot_path(season: str,
                            directory: str | Path = ".") -> Path:
    """Return the canonical generated benchmark path for one season snapshot."""
    return Path(directory) / benchmark_snapshot_filename(season)


def benchmark_metadata_path(season: str,
                            directory: str | Path = ".") -> Path:
    """Return the canonical benchmark metadata path for one season snapshot."""
    return Path(directory) / benchmark_metadata_filename(season)


def _coerce_optional_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _coerce_confidence(value: object) -> float | None:
    if value is None or value == "":
        return None
    confidence = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(confidence):
        return None
    return float(confidence)


def _coerce_optional_rank(value: object) -> int | None:
    if value is None or value == "" or pd.isna(value):
        return None
    return _coerce_rank(value)


def _coerce_rank(value: object) -> int:
    rank = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(rank):
        raise ValueError(f"rank is required, got {value!r}")
    return int(rank)


def _coerce_review_status(value: object) -> str:
    status = _coerce_optional_text(value).lower() or REVIEW_STATUS_PENDING
    if status not in VALID_REVIEW_STATUSES:
        raise ValueError(
            f"review_status must be one of {sorted(VALID_REVIEW_STATUSES)}, got {status!r}"
        )
    return status


def _coerce_review_row(row: Mapping[str, object],
                       season: str,
                       source_batch: str,
                       source_order: int) -> dict[str, object]:
    """Coerce one parsed screenshot row into the canonical review-table shape."""
    player_name = _coerce_optional_text(row.get("PLAYER_NAME", row.get("player_name")))
    raw_ocr_name = _coerce_optional_text(row.get("RAW_OCR_NAME", row.get("raw_ocr_name")))
    if not player_name:
        player_name = raw_ocr_name
    if not player_name:
        raise ValueError("player_name or raw_ocr_name is required")

    review_status = _coerce_review_status(
        row.get("REVIEW_STATUS", row.get("review_status"))
    )
    ocr_confidence = _coerce_confidence(
        row.get("OCR_CONFIDENCE", row.get("ocr_confidence"))
    )
    row_confidence = _coerce_confidence(
        row.get("ROW_CONFIDENCE", row.get("row_confidence", row.get("review_confidence")))
    )
    if row_confidence is None and review_status == REVIEW_STATUS_APPROVED:
        row_confidence = 1.0
    elif row_confidence is None:
        row_confidence = ocr_confidence

    return {
        "SEASON": str(season).strip(),
        "SOURCE_BATCH": _coerce_optional_text(source_batch),
        "SOURCE_ORDER": int(row.get("SOURCE_ORDER", row.get("source_order", source_order))),
        "RANK": _coerce_rank(row.get("RANK", row.get("rank"))),
        "PLAYER_NAME": player_name,
        "RAW_OCR_NAME": raw_ocr_name or player_name,
        "TEAM_TEXT": _coerce_optional_text(row.get("TEAM_TEXT", row.get("team_text"))),
        "REVIEW_STATUS": review_status,
        "CORRECTED_PLAYER_NAME": _coerce_optional_text(
            row.get("CORRECTED_PLAYER_NAME", row.get("corrected_player_name"))
        ),
        "CORRECTED_RANK": _coerce_optional_rank(
            row.get("CORRECTED_RANK", row.get("corrected_rank"))
        ),
        "ROW_CONFIDENCE": row_confidence,
        "REVIEW_NOTES": _coerce_optional_text(
            row.get("REVIEW_NOTES", row.get("review_notes", row.get("notes")))
        ),
        "OCR_CONFIDENCE": ocr_confidence,
    }


def normalize_review_table(df: pd.DataFrame,
                           expected_season: str | None = None,
                           expected_source_batch: str | None = None) -> pd.DataFrame:
    """Normalize and validate one season-specific screenshot review table."""
    review_table = df.copy()
    for col, default in REVIEW_TABLE_DEFAULTS.items():
        if col not in review_table.columns:
            review_table[col] = default

    missing = [col for col in REVIEW_TABLE_COLUMNS if col not in review_table.columns]
    if missing:
        raise ValueError(f"review table missing required columns: {missing}")

    review_table = review_table[REVIEW_TABLE_COLUMNS].copy()

    for col in [
        "SEASON",
        "SOURCE_BATCH",
        "PLAYER_NAME",
        "RAW_OCR_NAME",
        "TEAM_TEXT",
        "CORRECTED_PLAYER_NAME",
        "REVIEW_NOTES",
    ]:
        review_table[col] = review_table[col].map(_coerce_optional_text)

    review_table["REVIEW_STATUS"] = review_table["REVIEW_STATUS"].map(_coerce_review_status)
    review_table["SOURCE_ORDER"] = pd.to_numeric(review_table["SOURCE_ORDER"], errors="raise").astype(int)
    review_table["RANK"] = pd.to_numeric(review_table["RANK"], errors="raise").astype(int)
    review_table["CORRECTED_RANK"] = pd.to_numeric(
        review_table["CORRECTED_RANK"], errors="coerce"
    )
    if review_table["CORRECTED_RANK"].notna().any():
        review_table.loc[review_table["CORRECTED_RANK"].notna(), "CORRECTED_RANK"] = (
            review_table.loc[review_table["CORRECTED_RANK"].notna(), "CORRECTED_RANK"].astype(int)
        )
    review_table["ROW_CONFIDENCE"] = pd.to_numeric(
        review_table["ROW_CONFIDENCE"], errors="coerce"
    )
    review_table["OCR_CONFIDENCE"] = pd.to_numeric(
        review_table["OCR_CONFIDENCE"], errors="coerce"
    )

    seasons = {season for season in review_table["SEASON"] if season}
    if len(seasons) != 1:
        raise ValueError("review table must contain exactly one season")
    source_batches = {batch for batch in review_table["SOURCE_BATCH"] if batch}
    if len(source_batches) != 1:
        raise ValueError("review table must contain exactly one source batch")

    season = next(iter(seasons))
    source_batch = next(iter(source_batches))
    if expected_season and season != expected_season:
        raise ValueError(f"review table season mismatch: expected {expected_season!r}, got {season!r}")
    if expected_source_batch and source_batch != expected_source_batch:
        raise ValueError(
            f"review table source batch mismatch: expected {expected_source_batch!r}, got {source_batch!r}"
        )

    return review_table.sort_values(["RANK", "SOURCE_ORDER"]).reset_index(drop=True)


def build_review_table(rows: Iterable[Mapping[str, object]],
                       season: str,
                       source_batch: str) -> pd.DataFrame:
    """Build the canonical intermediate review table for one screenshot batch."""
    batch = str(source_batch).strip()
    if not batch:
        raise ValueError("source_batch is required")

    records = [
        _coerce_review_row(row, season=season, source_batch=batch, source_order=index)
        for index, row in enumerate(rows, start=1)
    ]
    review_table = pd.DataFrame(records, columns=REVIEW_TABLE_COLUMNS)
    return normalize_review_table(
        review_table,
        expected_season=str(season).strip(),
        expected_source_batch=batch,
    )


def write_review_table(review_table: pd.DataFrame,
                       path: str | Path) -> Path:
    """Persist a normalized review table as CSV."""
    normalized = normalize_review_table(review_table)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False)
    return output_path


def _approved_rows(review_table: pd.DataFrame) -> pd.DataFrame:
    return review_table[review_table["REVIEW_STATUS"] == REVIEW_STATUS_APPROVED].copy()


def _effective_player_name(row: pd.Series) -> str:
    corrected = _coerce_optional_text(row.get("CORRECTED_PLAYER_NAME"))
    return corrected or _coerce_optional_text(row.get("PLAYER_NAME"))


def _effective_rank(row: pd.Series) -> int | None:
    corrected = row.get("CORRECTED_RANK")
    if corrected is not None and not pd.isna(corrected):
        return int(corrected)
    rank = row.get("RANK")
    if rank is None or pd.isna(rank):
        return None
    return int(rank)


def apply_review_corrections(review_table: pd.DataFrame) -> pd.DataFrame:
    """Return one normalized review table with explicit effective benchmark fields."""
    normalized = normalize_review_table(review_table)
    effective = normalized.copy()
    effective["EFFECTIVE_PLAYER_NAME"] = effective.apply(_effective_player_name, axis=1)
    effective["EFFECTIVE_RANK"] = effective.apply(_effective_rank, axis=1)
    return effective


def classify_confidence_summary(file_confidence: float | None,
                                low_confidence_rows: int) -> str:
    """Return a compact file-level confidence label."""
    if file_confidence is None or pd.isna(file_confidence):
        return CONFIDENCE_SUMMARY_LOW
    if low_confidence_rows == 0 and file_confidence >= 0.95:
        return CONFIDENCE_SUMMARY_HIGH
    if file_confidence >= REVIEW_READY_MIN_CONFIDENCE:
        return CONFIDENCE_SUMMARY_MIXED
    return CONFIDENCE_SUMMARY_LOW


def summarize_review_table(review_table: pd.DataFrame,
                           min_confidence: float = REVIEW_READY_MIN_CONFIDENCE) -> dict[str, object]:
    """Summarize one review table into readiness, completeness, and confidence."""
    effective = apply_review_corrections(review_table)
    approved = _approved_rows(effective)

    pending_rows = int((effective["REVIEW_STATUS"] == REVIEW_STATUS_PENDING).sum())
    rejected_rows = int((effective["REVIEW_STATUS"] == REVIEW_STATUS_REJECTED).sum())
    approved_rows = int(len(approved))

    missing_required_rows = 0
    low_confidence_rows = 0
    file_confidence: float | None = None
    blockers: list[str] = []

    if approved_rows == 0:
        blockers.append("no approved rows")
    else:
        missing_required_rows = int(
            approved["EFFECTIVE_PLAYER_NAME"].map(_coerce_optional_text).eq("").sum()
            + approved["EFFECTIVE_RANK"].isna().sum()
        )
        low_confidence_rows = int(
            approved["ROW_CONFIDENCE"].lt(min_confidence).fillna(False).sum()
        )
        file_confidence = None if approved["ROW_CONFIDENCE"].dropna().empty else float(
            approved["ROW_CONFIDENCE"].dropna().mean()
        )

    if pending_rows > 0:
        blockers.append(f"{pending_rows} pending row(s)")
    if missing_required_rows > 0:
        blockers.append(f"{missing_required_rows} row(s) missing corrected required fields")
    if low_confidence_rows > 0:
        blockers.append(f"{low_confidence_rows} low-confidence approved row(s)")
    if file_confidence is None and approved_rows > 0:
        blockers.append("missing file confidence")

    ready = len(blockers) == 0
    confidence_summary = classify_confidence_summary(file_confidence, low_confidence_rows)

    return {
        "season": effective.iloc[0]["SEASON"] if len(effective) else "",
        "source_batch": effective.iloc[0]["SOURCE_BATCH"] if len(effective) else "",
        "total_rows": int(len(effective)),
        "approved_rows": approved_rows,
        "rejected_rows": rejected_rows,
        "pending_rows": pending_rows,
        "missing_required_rows": missing_required_rows,
        "low_confidence_rows": low_confidence_rows,
        "file_confidence": file_confidence,
        "confidence_summary": confidence_summary,
        "ready": ready,
        "blocked_reasons": blockers,
    }


def require_review_complete(review_table: pd.DataFrame) -> pd.DataFrame:
    """Ensure no rows remain pending before benchmark generation."""
    effective = apply_review_corrections(review_table)
    summary = summarize_review_table(effective)
    if summary["pending_rows"] > 0:
        raise ValueError("cannot generate benchmark snapshot while review_status is still pending")
    approved = _approved_rows(effective)
    if len(approved) == 0:
        raise ValueError("cannot generate benchmark snapshot without at least one approved row")
    if summary["missing_required_rows"] > 0:
        raise ValueError("cannot generate benchmark snapshot while corrected required fields are missing")
    if summary["low_confidence_rows"] > 0 or not summary["ready"]:
        raise ValueError("cannot generate benchmark snapshot while file confidence is below the ready threshold")
    return effective


def build_benchmark_snapshot(review_table: pd.DataFrame,
                             require_reviewed: bool = True) -> pd.DataFrame:
    """Convert reviewed screenshot rows into a validation-ready benchmark CSV shape."""
    normalized = (
        require_review_complete(review_table)
        if require_reviewed
        else apply_review_corrections(review_table)
    )
    approved = _approved_rows(normalized)
    if approved["EFFECTIVE_RANK"].duplicated().any():
        raise ValueError("approved rows must not contain duplicate ranks")

    snapshot = pd.DataFrame(
        {
            "Rank": approved["EFFECTIVE_RANK"].astype(int),
            "Player Name": approved["EFFECTIVE_PLAYER_NAME"],
            "Season": approved["SEASON"],
            "Source Batch": approved["SOURCE_BATCH"],
        }
    )
    return snapshot.sort_values("Rank").reset_index(drop=True)


def write_benchmark_snapshot(review_table: pd.DataFrame,
                             season: str,
                             path: str | Path | None = None) -> Path:
    """Persist one reviewed season snapshot as a validation-ready benchmark CSV."""
    normalized = require_review_complete(review_table)
    normalized = normalize_review_table(normalized, expected_season=str(season).strip())
    snapshot = build_benchmark_snapshot(normalized, require_reviewed=False)
    output_path = Path(path) if path is not None else benchmark_snapshot_path(season)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_csv(output_path, index=False)
    metadata_path = benchmark_metadata_path(
        season,
        directory=output_path.parent,
    )
    write_benchmark_metadata(normalized, season=season, path=metadata_path)
    return output_path


def build_benchmark_metadata(review_table: pd.DataFrame,
                             generated_at: str | None = None) -> pd.DataFrame:
    """Build one-row benchmark provenance metadata from a reviewed season file."""
    summary = summarize_review_table(review_table)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    ready_blockers = "; ".join(summary["blocked_reasons"])
    row = {
        "Season": summary["season"],
        "Source Batch": summary["source_batch"],
        "Review Total Rows": summary["total_rows"],
        "Review Approved Rows": summary["approved_rows"],
        "Review Rejected Rows": summary["rejected_rows"],
        "Review Pending Rows": summary["pending_rows"],
        "Missing Required Rows": summary["missing_required_rows"],
        "Low Confidence Rows": summary["low_confidence_rows"],
        "File Confidence": summary["file_confidence"],
        "Confidence Summary": summary["confidence_summary"],
        "Ready": bool(summary["ready"]),
        "Ready Blockers": ready_blockers,
        "Generated At": timestamp,
    }
    return pd.DataFrame([row], columns=BENCHMARK_METADATA_COLUMNS)


def write_benchmark_metadata(review_table: pd.DataFrame,
                             season: str,
                             path: str | Path | None = None,
                             generated_at: str | None = None) -> Path:
    """Persist one season benchmark metadata sidecar as CSV."""
    normalized = normalize_review_table(review_table, expected_season=str(season).strip())
    metadata = build_benchmark_metadata(normalized, generated_at=generated_at)
    output_path = Path(path) if path is not None else benchmark_metadata_path(season)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata.to_csv(output_path, index=False)
    return output_path


def load_benchmark_metadata(path: str | Path) -> dict[str, object] | None:
    """Load one benchmark metadata sidecar if present."""
    metadata_path = Path(path)
    if not metadata_path.exists():
        return None
    metadata = pd.read_csv(metadata_path)
    if metadata.empty:
        return None
    row = metadata.iloc[0].to_dict()
    ready_value = row.get("Ready")
    if isinstance(ready_value, str):
        row["Ready"] = ready_value.strip().lower() == "true"
    else:
        row["Ready"] = bool(ready_value)
    blockers = _coerce_optional_text(row.get("Ready Blockers"))
    row["Ready Blockers"] = blockers
    return row


def season_from_snapshot_filename(filename: str) -> str | None:
    """Extract a season like `2024-25` from a canonical snapshot filename."""
    match = re.fullmatch(r"actual_14cat_(\d{2})_(\d{2})_snapshot\.csv", Path(filename).name)
    if not match:
        return None
    left, right = match.groups()
    return f"20{left}-{right}"


def assess_benchmark_readiness(snapshot_path: str | Path) -> dict[str, object] | None:
    """Return readiness/provenance info for one screenshot-derived benchmark target."""
    snapshot = Path(snapshot_path)
    season = season_from_snapshot_filename(snapshot.name)
    if season is None:
        return None

    metadata = load_benchmark_metadata(benchmark_metadata_path(season, directory=snapshot.parent))
    if metadata is not None:
        return {
            "season": metadata.get("Season"),
            "source_batch": metadata.get("Source Batch"),
            "ready": bool(metadata.get("Ready")),
            "confidence_summary": metadata.get("Confidence Summary"),
            "file_confidence": metadata.get("File Confidence"),
            "generated_at": metadata.get("Generated At"),
            "blocked_reasons": [
                reason for reason in _coerce_optional_text(metadata.get("Ready Blockers")).split("; ")
                if reason
            ],
            "review_counts": {
                "total": int(metadata.get("Review Total Rows", 0) or 0),
                "approved": int(metadata.get("Review Approved Rows", 0) or 0),
                "rejected": int(metadata.get("Review Rejected Rows", 0) or 0),
                "pending": int(metadata.get("Review Pending Rows", 0) or 0),
            },
        }

    review_path = review_table_path(season)
    if not review_path.exists():
        return None
    review_table = pd.read_csv(review_path)
    summary = summarize_review_table(review_table)
    return {
        "season": summary["season"],
        "source_batch": summary["source_batch"],
        "ready": bool(summary["ready"]),
        "confidence_summary": summary["confidence_summary"],
        "file_confidence": summary["file_confidence"],
        "generated_at": None,
        "blocked_reasons": list(summary["blocked_reasons"]),
        "review_counts": {
            "total": summary["total_rows"],
            "approved": summary["approved_rows"],
            "rejected": summary["rejected_rows"],
            "pending": summary["pending_rows"],
        },
    }


def bootstrap_review_table_from_snapshot(snapshot_path: str | Path,
                                         season: str,
                                         source_batch: str) -> pd.DataFrame:
    """Build a reviewed table from an existing legacy snapshot benchmark."""
    snapshot = pd.read_csv(snapshot_path)
    required = {"Rank", "Player Name"}
    missing = required - set(snapshot.columns)
    if missing:
        raise ValueError(f"legacy snapshot missing required columns: {sorted(missing)}")

    rows = []
    for _, row in snapshot.sort_values("Rank").iterrows():
        rows.append(
            {
                "rank": row["Rank"],
                "player_name": row["Player Name"],
                "raw_ocr_name": row["Player Name"],
                "review_status": REVIEW_STATUS_APPROVED,
                "review_notes": "bootstrapped from legacy snapshot benchmark",
                "row_confidence": 1.0,
            }
        )
    return build_review_table(rows=rows, season=season, source_batch=source_batch)
