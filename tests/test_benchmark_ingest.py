import tempfile
import unittest
from pathlib import Path

import pandas as pd

from benchmark_ingest import (
    BENCHMARK_SNAPSHOT_COLUMNS,
    BENCHMARK_METADATA_COLUMNS,
    OCRBackendUnavailableError,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_TABLE_COLUMNS,
    assess_benchmark_readiness,
    available_ocr_backends,
    benchmark_metadata_filename,
    benchmark_metadata_path,
    benchmark_snapshot_filename,
    benchmark_snapshot_path,
    build_benchmark_snapshot,
    build_benchmark_metadata,
    build_review_table,
    build_review_table_from_ocr_batch,
    bootstrap_review_table_from_snapshot,
    extract_review_rows_from_ocr_batch,
    normalize_review_table,
    resolve_ocr_adapter,
    review_table_filename,
    review_table_path,
    summarize_review_table,
    write_benchmark_snapshot,
    write_benchmark_metadata,
    write_review_table,
)


class FakeOCRAdapter:
    def __init__(self,
                 backend_name: str,
                 rows: list[dict[str, object]] | None = None,
                 available: bool = True) -> None:
        self.backend_name = backend_name
        self._rows = rows or []
        self._available = available
        self.calls: list[dict[str, object]] = []

    def is_available(self) -> bool:
        return self._available

    def extract_rows(self,
                     image_paths: list[Path],
                     season: str,
                     source_batch: str) -> list[dict[str, object]]:
        self.calls.append(
            {
                "image_paths": list(image_paths),
                "season": season,
                "source_batch": source_batch,
            }
        )
        if not self._available:
            raise OCRBackendUnavailableError(f"{self.backend_name} backend is unavailable")
        return list(self._rows)


class BenchmarkIngestTests(unittest.TestCase):
    def test_build_review_table_uses_explicit_schema_and_defaults(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 2,
                    "raw_ocr_name": "Victor Wembanyama",
                    "player_name": "Victor Wembanyama",
                    "team_text": "SAS - PF,C",
                },
                {
                    "rank": 1,
                    "raw_ocr_name": "Nikola Jokic",
                    "player_name": "Nikola Jokic",
                    "review_status": "approved",
                },
            ],
            season="2024-25",
            source_batch="screens_24_25_batch_a",
        )

        self.assertEqual(review_table.columns.tolist(), REVIEW_TABLE_COLUMNS)
        self.assertEqual(review_table.iloc[0]["RANK"], 1)
        self.assertEqual(review_table.iloc[0]["SOURCE_BATCH"], "screens_24_25_batch_a")
        self.assertEqual(review_table.iloc[1]["REVIEW_STATUS"], REVIEW_STATUS_PENDING)
        self.assertEqual(review_table.iloc[1]["TEAM_TEXT"], "SAS - PF,C")
        self.assertEqual(review_table.iloc[0]["CORRECTED_PLAYER_NAME"], "")
        self.assertTrue(pd.isna(review_table.iloc[0]["CORRECTED_RANK"]))
        self.assertEqual(review_table.iloc[0]["ROW_CONFIDENCE"], 1.0)

    def test_normalize_review_table_requires_one_season_and_one_batch(self) -> None:
        review_table = pd.DataFrame(
            [
                {
                    "SEASON": "2024-25",
                    "SOURCE_BATCH": "batch_a",
                    "SOURCE_ORDER": 1,
                    "RANK": 1,
                    "PLAYER_NAME": "Nikola Jokic",
                    "RAW_OCR_NAME": "Nikola Jokic",
                    "TEAM_TEXT": "",
                    "REVIEW_STATUS": "approved",
                    "REVIEW_NOTES": "",
                    "OCR_CONFIDENCE": 0.95,
                },
                {
                    "SEASON": "2023-24",
                    "SOURCE_BATCH": "batch_a",
                    "SOURCE_ORDER": 2,
                    "RANK": 2,
                    "PLAYER_NAME": "Luka Doncic",
                    "RAW_OCR_NAME": "Luka Doncic",
                    "TEAM_TEXT": "",
                    "REVIEW_STATUS": "approved",
                    "REVIEW_NOTES": "",
                    "OCR_CONFIDENCE": 0.90,
                },
            ]
        )

        with self.assertRaisesRegex(ValueError, "exactly one season"):
            normalize_review_table(review_table)

    def test_filename_helpers_preserve_one_snapshot_per_season_convention(self) -> None:
        self.assertEqual(review_table_filename("2024-25"), "actual_14cat_24_25_review.csv")
        self.assertEqual(
            benchmark_snapshot_filename("2024-25"),
            "actual_14cat_24_25_snapshot.csv",
        )
        self.assertEqual(
            benchmark_metadata_filename("2024-25"),
            "actual_14cat_24_25_snapshot_metadata.csv",
        )
        self.assertEqual(
            str(review_table_path("2024-25")),
            "benchmarks/review_tables/actual_14cat_24_25_review.csv",
        )
        self.assertEqual(
            str(benchmark_snapshot_path("2024-25")),
            "actual_14cat_24_25_snapshot.csv",
        )
        self.assertEqual(
            str(benchmark_metadata_path("2024-25")),
            "actual_14cat_24_25_snapshot_metadata.csv",
        )

    def test_build_benchmark_snapshot_requires_review_completion(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                },
                {
                    "rank": 2,
                    "player_name": "Victor Wembanyama",
                    "raw_ocr_name": "Victor Wembanyama",
                    "review_status": REVIEW_STATUS_PENDING,
                },
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        with self.assertRaisesRegex(ValueError, "review_status is still pending"):
            build_benchmark_snapshot(review_table)

    def test_build_benchmark_snapshot_preserves_rank_order_and_shape(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 2,
                    "player_name": "Victor Wembanyama",
                    "raw_ocr_name": "Victor Wembanyama",
                    "review_status": REVIEW_STATUS_APPROVED,
                },
                {
                    "rank": 3,
                    "player_name": "Luka Doncic",
                    "raw_ocr_name": "Luka Doncic",
                    "review_status": "rejected",
                },
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "corrected_player_name": "Nikola Jokić",
                },
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        snapshot = build_benchmark_snapshot(review_table)

        self.assertEqual(snapshot.columns.tolist(), BENCHMARK_SNAPSHOT_COLUMNS)
        self.assertEqual(snapshot["Rank"].tolist(), [1, 2])
        self.assertEqual(snapshot["Player Name"].tolist(), ["Nikola Jokić", "Victor Wembanyama"])
        self.assertTrue((snapshot["Season"] == "2024-25").all())
        self.assertTrue((snapshot["Source Batch"] == "batch_a").all())

    def test_summarize_review_table_reports_ready_when_reviewed_and_confident(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 0.95,
                },
                {
                    "rank": 2,
                    "player_name": "Victor Wembanyama",
                    "raw_ocr_name": "Victor Wembanyama",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 0.90,
                },
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        summary = summarize_review_table(review_table)

        self.assertTrue(summary["ready"])
        self.assertEqual(summary["approved_rows"], 2)
        self.assertEqual(summary["pending_rows"], 0)
        self.assertEqual(summary["low_confidence_rows"], 0)
        self.assertAlmostEqual(summary["file_confidence"], 0.925)
        self.assertEqual(summary["confidence_summary"], "mixed")

    def test_summarize_review_table_blocks_low_confidence_rows(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 0.70,
                }
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        summary = summarize_review_table(review_table)

        self.assertFalse(summary["ready"])
        self.assertEqual(summary["low_confidence_rows"], 1)
        self.assertIn("low-confidence approved row", " ".join(summary["blocked_reasons"]))

    def test_write_review_table_and_snapshot_create_csvs(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 0.99,
                }
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            review_path = write_review_table(review_table, Path(tmpdir) / review_table_filename("2024-25"))
            snapshot_path = write_benchmark_snapshot(
                review_table,
                season="2024-25",
                path=Path(tmpdir) / benchmark_snapshot_filename("2024-25"),
            )
            metadata_path = benchmark_metadata_path("2024-25", directory=tmpdir)

            written_review = pd.read_csv(review_path)
            written_snapshot = pd.read_csv(snapshot_path)
            written_metadata = pd.read_csv(metadata_path)

        self.assertEqual(written_review.columns.tolist(), REVIEW_TABLE_COLUMNS)
        self.assertEqual(written_snapshot.columns.tolist(), BENCHMARK_SNAPSHOT_COLUMNS)
        self.assertEqual(written_metadata.columns.tolist(), BENCHMARK_METADATA_COLUMNS)
        self.assertTrue(bool(written_metadata.iloc[0]["Ready"]))

    def test_write_benchmark_snapshot_rejects_mismatched_season_argument(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                }
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "season mismatch"):
                write_benchmark_snapshot(
                    review_table,
                    season="2023-24",
                    path=Path(tmpdir) / benchmark_snapshot_filename("2023-24"),
                )

    def test_build_benchmark_metadata_persists_provenance_summary(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 1.0,
                }
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        metadata = build_benchmark_metadata(review_table, generated_at="2026-05-07T20:00:00+00:00")

        self.assertEqual(metadata.columns.tolist(), BENCHMARK_METADATA_COLUMNS)
        self.assertEqual(metadata.iloc[0]["Season"], "2024-25")
        self.assertEqual(metadata.iloc[0]["Source Batch"], "batch_a")
        self.assertEqual(metadata.iloc[0]["Generated At"], "2026-05-07T20:00:00+00:00")

    def test_assess_benchmark_readiness_reads_metadata_sidecar(self) -> None:
        review_table = build_review_table(
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Jokic",
                    "review_status": REVIEW_STATUS_APPROVED,
                    "row_confidence": 0.96,
                }
            ],
            season="2024-25",
            source_batch="batch_a",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            write_benchmark_snapshot(
                review_table,
                season="2024-25",
                path=Path(tmpdir) / benchmark_snapshot_filename("2024-25"),
            )
            readiness = assess_benchmark_readiness(
                Path(tmpdir) / benchmark_snapshot_filename("2024-25")
            )

        self.assertIsNotNone(readiness)
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["source_batch"], "batch_a")
        self.assertEqual(readiness["review_counts"]["approved"], 1)

    def test_bootstrap_review_table_from_snapshot_creates_ready_review_rows(self) -> None:
        snapshot = pd.DataFrame(
            [
                {"Rank": 1, "Player Name": "Nikola Jokic"},
                {"Rank": 2, "Player Name": "Victor Wembanyama"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / benchmark_snapshot_filename("2024-25")
            snapshot.to_csv(snapshot_path, index=False)
            review_table = bootstrap_review_table_from_snapshot(
                snapshot_path,
                season="2024-25",
                source_batch="legacy_24_25_snapshot",
            )

        self.assertEqual(review_table["REVIEW_STATUS"].tolist(), [REVIEW_STATUS_APPROVED, REVIEW_STATUS_APPROVED])
        self.assertEqual(review_table["ROW_CONFIDENCE"].tolist(), [1.0, 1.0])
        self.assertTrue(summarize_review_table(review_table)["ready"])

    def test_resolve_ocr_adapter_uses_one_explicit_backend_boundary(self) -> None:
        first = FakeOCRAdapter("mock_a")
        second = FakeOCRAdapter("mock_b")

        resolved = resolve_ocr_adapter("mock_b", adapters=[first, second])

        self.assertIs(resolved, second)
        self.assertEqual(available_ocr_backends(adapters=[first, second]), ["mock_a", "mock_b"])

    def test_build_review_table_from_ocr_batch_preserves_one_season_batch_contract(self) -> None:
        adapter = FakeOCRAdapter(
            "mock",
            rows=[
                {"rank": 2, "player_name": "Victor Wembanyama", "raw_ocr_name": "Victor Wembanyama"},
                {"rank": 1, "player_name": "Nikola Jokic", "raw_ocr_name": "Nikola Jokic"},
            ],
        )

        review_table = build_review_table_from_ocr_batch(
            image_paths=[Path("screen_1.png"), Path("screen_2.png")],
            season="2024-25",
            source_batch="ocr_batch_24_25",
            adapter=adapter,
        )

        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0]["season"], "2024-25")
        self.assertEqual(adapter.calls[0]["source_batch"], "ocr_batch_24_25")
        self.assertEqual(review_table["SEASON"].unique().tolist(), ["2024-25"])
        self.assertEqual(review_table["SOURCE_BATCH"].unique().tolist(), ["ocr_batch_24_25"])
        self.assertEqual(review_table["RANK"].tolist(), [1, 2])

    def test_ocr_confidence_stays_separate_from_reviewed_row_confidence(self) -> None:
        adapter = FakeOCRAdapter(
            "mock",
            rows=[
                {
                    "rank": 1,
                    "player_name": "Nikola Jokic",
                    "raw_ocr_name": "Nikola Joklc",
                    "ocr_confidence": 0.42,
                }
            ],
        )

        review_table = build_review_table_from_ocr_batch(
            image_paths=[Path("screen_1.png")],
            season="2024-25",
            source_batch="ocr_batch_24_25",
            adapter=adapter,
        )

        self.assertTrue(pd.isna(review_table.iloc[0]["ROW_CONFIDENCE"]))
        self.assertAlmostEqual(review_table.iloc[0]["OCR_CONFIDENCE"], 0.42)
        self.assertEqual(review_table.iloc[0]["REVIEW_STATUS"], REVIEW_STATUS_PENDING)

    def test_partial_ocr_rows_are_preserved_for_review_instead_of_dropped(self) -> None:
        adapter = FakeOCRAdapter(
            "mock",
            rows=[
                {"raw_text": "Unreadable player fragment", "ocr_confidence": 0.18},
                {"rank": 2, "raw_ocr_name": "Victor Wembanyama", "ocr_confidence": 0.73},
            ],
        )

        rows = extract_review_rows_from_ocr_batch(
            image_paths=[Path("screen_1.png")],
            season="2024-25",
            source_batch="ocr_batch_24_25",
            adapter=adapter,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["raw_ocr_name"], "Unreadable player fragment")
        self.assertIn("rank inferred from OCR row order", rows[0]["review_notes"])
        self.assertIn("team text needs review", rows[0]["review_notes"])

    def test_unavailable_ocr_backend_surfaces_clear_error(self) -> None:
        adapter = FakeOCRAdapter("mock", available=False)

        with self.assertRaisesRegex(OCRBackendUnavailableError, "backend is unavailable"):
            build_review_table_from_ocr_batch(
                image_paths=[Path("screen_1.png")],
                season="2024-25",
                source_batch="ocr_batch_24_25",
                adapter=adapter,
            )


if __name__ == "__main__":
    unittest.main()
