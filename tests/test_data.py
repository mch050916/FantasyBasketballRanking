import pickle
import tempfile
import unittest
from pathlib import Path

from data import (
    _build_game_log_fetch_health,
    _build_cache_envelope,
    _empty_game_log_result,
    _load_cached_game_logs,
    _load_cached_tech_per_game,
    _missing_game_log_pairs,
    build_nba_player_lookups,
    normalize_player_name,
    resolve_player_id,
)


class DataTests(unittest.TestCase):
    def test_normalize_player_name_removes_accents(self) -> None:
        self.assertEqual(normalize_player_name("Alperen Şengün"), "alperensengun")
        self.assertEqual(normalize_player_name("Kristaps Porziņģis"), "kristapsporzingis")

    def test_resolve_player_id_matches_normalized_name(self) -> None:
        players = [
            {"full_name": "Alperen Sengun", "id": 1},
            {"full_name": "Nikola Jokić", "id": 2},
        ]
        exact, normalized = build_nba_player_lookups(players)

        self.assertEqual(resolve_player_id("Alperen Şengün", exact, normalized), 1)
        self.assertEqual(resolve_player_id("Nikola Jokic", exact, normalized), 2)

    def test_missing_game_log_pairs_only_returns_unfetched_entries(self) -> None:
        result = _empty_game_log_result(["2024-25", "2023-24"])
        result["2024-25"]["Nikola Jokić"] = object()

        missing = _missing_game_log_pairs(
            game_logs=result,
            player_names=["Nikola Jokić", "Alperen Şengün"],
            seasons=["2024-25", "2023-24"],
        )

        self.assertEqual(
            missing,
            [
                ("Nikola Jokić", "2023-24"),
                ("Alperen Şengün", "2024-25"),
                ("Alperen Şengün", "2023-24"),
            ],
        )

    def test_load_cached_game_logs_rejects_legacy_cache_without_metadata(self) -> None:
        legacy_payload = {"2024-25": {"Nikola Jokić": object()}}

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "game_log_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(legacy_payload, f)

            result, cache_status = _load_cached_game_logs(cache_path, ["2024-25"])

        self.assertEqual(result, {"2024-25": {}})
        self.assertFalse(cache_status["valid"])
        self.assertIn("cache", str(cache_status["reason"]))

    def test_load_cached_game_logs_rejects_mismatched_seasons(self) -> None:
        payload = {"2024-25": {"Nikola Jokić": object()}}
        envelope = _build_cache_envelope(
            "game_logs",
            payload,
            {"seasons": ["2023-24"]},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "game_log_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(envelope, f)

            result, cache_status = _load_cached_game_logs(cache_path, ["2024-25"])

        self.assertEqual(result, {"2024-25": {}})
        self.assertFalse(cache_status["valid"])
        self.assertEqual(cache_status["reason"], "game-log cache metadata mismatch")

    def test_load_cached_tech_per_game_rejects_weight_mismatch(self) -> None:
        envelope = _build_cache_envelope(
            "tech_per_game",
            {"Nikola Jokić": 0.02},
            {
                "seasons": ["2024-25", "2023-24"],
                "season_weights": [0.625, 0.375],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "tech_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(envelope, f)

            result, cache_status = _load_cached_tech_per_game(
                cache_path,
                ["2024-25", "2023-24"],
                [0.5, 0.5],
            )

        self.assertIsNone(result)
        self.assertFalse(cache_status["valid"])
        self.assertEqual(cache_status["reason"], "TECH cache metadata mismatch")

    def test_load_cached_game_logs_rejects_unreadable_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "game_log_cache.pkl"
            cache_path.write_bytes(b"not-a-pickle")

            result, cache_status = _load_cached_game_logs(cache_path, ["2024-25"])

        self.assertEqual(result, {"2024-25": {}})
        self.assertFalse(cache_status["valid"])
        self.assertIn("unreadable cache payload", str(cache_status["reason"]))

    def test_build_game_log_fetch_health_marks_requested_pool_misses_as_degraded(self) -> None:
        health = _build_game_log_fetch_health(
            ["Nikola Jokić", "Alperen Şengün"],
            ["2024-25", "2023-24"],
            [("Alperen Şengün", "2024-25")],
        )

        self.assertTrue(health["degraded"])
        self.assertEqual(health["requested_pair_count"], 4)
        self.assertEqual(health["missing_pair_count"], 1)


if __name__ == "__main__":
    unittest.main()
