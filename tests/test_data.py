import pickle
import tempfile
import unittest
from pathlib import Path

from data import (
    _build_cache_envelope,
    _classify_missing_game_log_pairs,
    _empty_game_log_result,
    _build_game_log_fetch_health,
    _load_cached_current_teams,
    _load_cached_draft_history,
    _load_cached_game_logs,
    _load_cached_tech_per_game,
    _missing_game_log_pairs,
    _partition_missing_pairs,
    build_non_actionable_suppression_report,
    detect_team_changes,
    load_non_actionable_suppression_registry,
    summarize_non_actionable_suppression_registry,
)
from identity import build_nba_player_lookups, normalize_player_name, resolve_player_id


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

    def test_resolve_player_id_uses_nba_api_source_override(self) -> None:
        players = [
            {"full_name": "Jimmy Butler III", "id": 22},
        ]
        exact, normalized = build_nba_player_lookups(players)

        self.assertEqual(resolve_player_id("Jimmy Butler", exact, normalized), 22)

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

    def test_load_cached_draft_history_rejects_year_mismatch(self) -> None:
        envelope = _build_cache_envelope(
            "draft_history",
            {"AJ Dybantsa": {"overall_pick": 1, "round_number": 1}},
            {"draft_years": ["2026"]},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "draft_history_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(envelope, f)

            result, cache_status = _load_cached_draft_history(
                cache_path,
                ["2025"],
            )

        self.assertIsNone(result)
        self.assertFalse(cache_status["valid"])
        self.assertEqual(cache_status["reason"], "draft-history cache metadata mismatch")

    def test_load_cached_current_teams_rejects_season_mismatch(self) -> None:
        envelope = _build_cache_envelope(
            "current_teams",
            {"LeBron James": "PHI"},
            {"season": "2026-27"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "current_teams_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(envelope, f)

            result, cache_status = _load_cached_current_teams(cache_path, "2027-28")

        self.assertIsNone(result)
        self.assertFalse(cache_status["valid"])
        self.assertEqual(cache_status["reason"], "current-teams cache metadata mismatch")

    def test_detect_team_changes_flags_a_real_move(self) -> None:
        changes = detect_team_changes(
            previous_team_by_player={"LeBron James": "LAL", "Julius Randle": "MIN"},
            current_team_by_player={"LeBron James": "PHI", "Julius Randle": "BKN"},
        )
        self.assertEqual(changes, {
            "LeBron James": "LAL -> PHI",
            "Julius Randle": "MIN -> BKN",
        })

    def test_detect_team_changes_omits_players_who_stayed_put(self) -> None:
        changes = detect_team_changes(
            previous_team_by_player={"Nikola Jokic": "DEN"},
            current_team_by_player={"Nikola Jokic": "DEN"},
        )
        self.assertEqual(changes, {})

    def test_detect_team_changes_omits_players_missing_from_either_side(self) -> None:
        # Not in previous_team_by_player at all (e.g. a rookie -- handled by
        # rookie_baseline.py separately, not this function's concern) and not
        # in current_team_by_player (e.g. retired, or missing from the current
        # roster fetch) should both be silently skipped, not KeyError.
        changes = detect_team_changes(
            previous_team_by_player={"Only In Previous": "BOS"},
            current_team_by_player={"Only In Current": "MIA"},
        )
        self.assertEqual(changes, {})

    def test_detect_team_changes_matches_by_canonical_identity(self) -> None:
        # Accent/normalization differences between sources shouldn't produce
        # a false "team changed" -- same identity scheme every other cross-
        # source match in this pipeline already uses.
        changes = detect_team_changes(
            previous_team_by_player={"Alperen Sengun": "HOU"},
            current_team_by_player={"Alperen Şengün": "HOU"},
        )
        self.assertEqual(changes, {})

    def test_detect_team_changes_treats_bbr_nba_api_abbreviation_pairs_as_the_same_team(self) -> None:
        # Verified live against a real pipeline run: BBR spells 3 teams
        # differently than nba_api (BRK/BKN, CHO/CHA, PHO/PHX) -- a player
        # who never left one of these must not read as a false "change".
        changes = detect_team_changes(
            previous_team_by_player={
                "Devin Booker": "PHO",
                "Kon Knueppel": "CHO",
                "Michael Porter Jr.": "BRK",
            },
            current_team_by_player={
                "Devin Booker": "PHX",
                "Kon Knueppel": "CHA",
                "Michael Porter Jr.": "BKN",
            },
        )
        self.assertEqual(changes, {})

    def test_detect_team_changes_normalizes_multi_team_markers(self) -> None:
        # BBR's real 2025-26 export uses "2TM" (not just "TOT") as the
        # aggregate-row marker for players who played on exactly two teams
        # that season -- caught this live via James Harden/Nikola Vucevic
        # in the actual pipeline run. Neither raw code names a real team,
        # so both should read as a single, readable "Multiple Teams" label.
        changes = detect_team_changes(
            previous_team_by_player={"James Harden": "2TM"},
            current_team_by_player={"James Harden": "CLE"},
        )
        self.assertEqual(changes, {"James Harden": "Multiple Teams -> CLE"})

    def test_detect_team_changes_ignores_identical_tot_rows(self) -> None:
        # The mid-season-trade case load_bbr_csv documents: both sides
        # happen to read "TOT" (a genuinely uninformative non-change), not a
        # real signal -- must not be reported as a move.
        changes = detect_team_changes(
            previous_team_by_player={"Traded Midseason": "TOT"},
            current_team_by_player={"Traded Midseason": "TOT"},
        )
        self.assertEqual(changes, {})

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

    def test_partition_missing_pairs_separates_expected_older_seasons(self) -> None:
        missing_pairs = [
            ("Bub Carrington", "2023-24"),
            ("Jimmy Butler", "2024-25"),
        ]

        unresolved, expected = _partition_missing_pairs(
            missing_pairs,
            {("Bub Carrington", "2023-24")},
        )

        self.assertEqual(unresolved, [("Jimmy Butler", "2024-25")])
        self.assertEqual(expected, [("Bub Carrington", "2023-24")])

    def test_build_game_log_fetch_health_tracks_expected_missing_pairs_separately(self) -> None:
        health = _build_game_log_fetch_health(
            ["Bub Carrington", "Jimmy Butler"],
            ["2024-25", "2023-24"],
            [("Jimmy Butler", "2024-25")],
            [("Bub Carrington", "2023-24")],
        )

        self.assertTrue(health["degraded"])
        self.assertEqual(health["missing_pair_count"], 1)
        self.assertEqual(health["expected_missing_pair_count"], 1)

    def test_classify_missing_game_log_pairs_separates_current_historical_and_non_actionable(self) -> None:
        active_reasons = {
            ("bojanbogdanovic", "2024-25"): "inactive current-season returnee",
        }
        classified = _classify_missing_game_log_pairs(
            [
                ("Bojan Bogdanović", "2024-25"),
                ("Jimmy Butler", "2024-25"),
                ("Someone Else", "2023-24"),
                ("Bub Carrington", "2023-24"),
            ],
            ["2024-25", "2023-24"],
            {("Bub Carrington", "2023-24")},
            active_reasons,
        )

        self.assertEqual(classified["current_season_missing_pairs"], [("Jimmy Butler", "2024-25")])
        self.assertEqual(classified["historical_missing_pairs"], [("Someone Else", "2023-24")])
        self.assertEqual(classified["expected_missing_pairs"], [("Bub Carrington", "2023-24")])
        self.assertEqual(classified["non_actionable_pairs"], [("Bojan Bogdanović", "2024-25")])
        self.assertEqual(
            classified["non_actionable_reasons"][("Bojan Bogdanović", "2024-25")],
            "inactive current-season returnee",
        )

    def test_build_game_log_fetch_health_tracks_current_historical_and_non_actionable_counts(self) -> None:
        health = _build_game_log_fetch_health(
            ["Bojan Bogdanović", "Jimmy Butler", "Someone Else"],
            ["2024-25", "2023-24"],
            [("Jimmy Butler", "2024-25"), ("Someone Else", "2023-24")],
            [("Bub Carrington", "2023-24")],
            current_season_missing_pairs=[("Jimmy Butler", "2024-25")],
            historical_missing_pairs=[("Someone Else", "2023-24")],
            non_actionable_pairs=[("Bojan Bogdanović", "2024-25")],
            non_actionable_reasons={
                ("Bojan Bogdanović", "2024-25"): "inactive current-season returnee",
            },
            suppression_registry_review={
                "active_entry_count": 1,
                "expired_entry_count": 0,
                "retired_entry_count": 0,
                "active_entries": [
                    {
                        "Player Name": "Bojan Bogdanović",
                        "Season": "2024-25",
                        "Reason": "inactive current-season returnee",
                    }
                ],
                "expired_entries": [],
                "retired_entries": [],
                "registry_path": ".planning/non_actionable_suppressions.csv",
                "current_season": "2024-25",
            },
        )

        self.assertTrue(health["degraded"])
        self.assertEqual(health["current_season_missing_pair_count"], 1)
        self.assertEqual(health["historical_missing_pair_count"], 1)
        self.assertEqual(health["non_actionable_pair_count"], 1)
        self.assertEqual(
            health["non_actionable_reasons"][("Bojan Bogdanović", "2024-25")],
            "inactive current-season returnee",
        )
        self.assertEqual(health["suppression_registry_review"]["active_entry_count"], 1)

    def test_load_non_actionable_suppression_registry_preserves_contract(self) -> None:
        registry_csv = """Player Name,Season,Reason,Review Status,Review Notes
Bojan Bogdanović,2024-25,inactive current-season returnee,active,notes
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.csv"
            registry_path.write_text(registry_csv, encoding="utf-8")
            registry = load_non_actionable_suppression_registry(registry_path)

        self.assertEqual(
            registry.columns.tolist(),
            ["Player Name", "Season", "Reason", "Review Status", "Review Notes"],
        )
        self.assertEqual(registry.iloc[0]["Review Status"], "active")

    def test_summarize_non_actionable_suppression_registry_marks_expired_entries(self) -> None:
        registry_csv = """Player Name,Season,Reason,Review Status,Review Notes
Bojan Bogdanović,2024-25,inactive current-season returnee,active,notes
Saddiq Bey,2025-26,inactive current-season returnee,active,notes
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.csv"
            registry_path.write_text(registry_csv, encoding="utf-8")
            summary = summarize_non_actionable_suppression_registry(
                ["2025-26", "2024-25"],
                path=registry_path,
            )

        self.assertEqual(summary["active_entry_count"], 1)
        self.assertEqual(summary["expired_entry_count"], 1)
        self.assertEqual(summary["active_entries"][0]["Player Name"], "Saddiq Bey")
        self.assertEqual(summary["expired_entries"][0]["Player Name"], "Bojan Bogdanović")

    def test_expired_registry_entries_do_not_suppress_missing_pairs(self) -> None:
        registry_csv = """Player Name,Season,Reason,Review Status,Review Notes
Bojan Bogdanović,2024-25,inactive current-season returnee,active,notes
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.csv"
            registry_path.write_text(registry_csv, encoding="utf-8")
            summary = summarize_non_actionable_suppression_registry(
                ["2025-26", "2024-25"],
                path=registry_path,
            )
            classified = _classify_missing_game_log_pairs(
                [("Bojan Bogdanović", "2024-25")],
                ["2025-26", "2024-25"],
                set(),
                summary["active_reason_map"],
            )

        self.assertEqual(classified["non_actionable_pairs"], [])
        self.assertEqual(classified["historical_missing_pairs"], [("Bojan Bogdanović", "2024-25")])

    def test_build_non_actionable_suppression_report_includes_active_and_expired_sections(self) -> None:
        health = _build_game_log_fetch_health(
            ["Bojan Bogdanović", "Saddiq Bey"],
            ["2025-26", "2024-25"],
            [],
            [],
            current_season_missing_pairs=[],
            historical_missing_pairs=[],
            non_actionable_pairs=[("Saddiq Bey", "2025-26")],
            non_actionable_reasons={
                ("Saddiq Bey", "2025-26"): "inactive current-season returnee",
            },
            suppression_registry_review={
                "registry_path": ".planning/non_actionable_suppressions.csv",
                "current_season": "2025-26",
                "active_entries": [
                    {
                        "Player Name": "Saddiq Bey",
                        "Season": "2025-26",
                        "Reason": "inactive current-season returnee",
                    }
                ],
                "expired_entries": [
                    {
                        "Player Name": "Bojan Bogdanović",
                        "Season": "2024-25",
                        "Reason": "inactive current-season returnee",
                    }
                ],
                "retired_entries": [],
                "active_entry_count": 1,
                "expired_entry_count": 1,
                "retired_entry_count": 0,
            },
        )

        report = build_non_actionable_suppression_report(health)

        self.assertIn("# Non-Actionable Suppression Maintenance", report)
        self.assertIn("## Active Entries", report)
        self.assertIn("Saddiq Bey (2025-26): inactive current-season returnee [used this run]", report)
        self.assertIn("## Expired Entries Requiring Reaffirmation", report)
        self.assertIn("Bojan Bogdanović (2024-25): inactive current-season returnee", report)


if __name__ == "__main__":
    unittest.main()
