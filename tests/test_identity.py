import unittest

from identity import (
    build_nba_player_lookups,
    canonical_player_key,
    normalize_player_name,
    resolve_player_id,
    resolve_source_player_name,
)


class IdentityTests(unittest.TestCase):
    def test_normalize_player_name_removes_accents(self):
        self.assertEqual(normalize_player_name("Nikola Jokić"), "nikolajokic")

    def test_canonical_player_key_collapses_suffix_variants(self):
        self.assertEqual(canonical_player_key("Jimmy Butler"), canonical_player_key("Jimmy Butler III"))

    def test_resolve_source_player_name_uses_manual_overrides(self):
        self.assertEqual(resolve_source_player_name("Jimmy Butler", "nba_api"), "Jimmy Butler III")

    def test_resolve_player_id_prefers_override_backed_exact_match(self):
        players = [
            {"id": 1, "full_name": "Jimmy Butler III"},
            {"id": 2, "full_name": "Nikola Jokic"},
        ]
        exact_lookup, canonical_lookup = build_nba_player_lookups(players)
        self.assertEqual(resolve_player_id("Jimmy Butler", exact_lookup, canonical_lookup), 1)

    def test_resolve_player_id_returns_none_for_unknown_player(self):
        players = [{"id": 2, "full_name": "Nikola Jokic"}]
        exact_lookup, canonical_lookup = build_nba_player_lookups(players)
        self.assertIsNone(resolve_player_id("Unknown Player", exact_lookup, canonical_lookup))


if __name__ == "__main__":
    unittest.main()
