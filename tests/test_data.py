import unittest

from data import (
    _empty_game_log_result,
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


if __name__ == "__main__":
    unittest.main()
