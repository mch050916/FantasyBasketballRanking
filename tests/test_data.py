import pickle
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data import (
    _build_cache_envelope,
    _classify_missing_game_log_pairs,
    _empty_game_log_result,
    _build_game_log_fetch_health,
    _load_cached_current_teams,
    _load_cached_draft_history,
    _load_cached_game_logs,
    _load_cached_season_schedule,
    _load_cached_tech_per_game,
    _missing_game_log_pairs,
    _normalize_bbr_team,
    _partition_missing_pairs,
    build_non_actionable_suppression_report,
    classify_injury_tier_with_carryover,
    detect_team_changes,
    games_per_team_for_week,
    load_bbr_csv,
    load_non_actionable_suppression_registry,
    MULTI_TEAM_LABEL,
    summarize_non_actionable_suppression_registry,
)
from identity import build_nba_player_lookups, normalize_player_name, resolve_player_id


class DataTests(unittest.TestCase):
    def test_normalize_player_name_removes_accents(self) -> None:
        self.assertEqual(normalize_player_name("Alperen Şengün"), "alperensengun")
        self.assertEqual(normalize_player_name("Kristaps Porziņģis"), "kristapsporzingis")

    def test_normalize_bbr_team_handles_legacy_tot_marker(self) -> None:
        self.assertEqual(_normalize_bbr_team("TOT"), MULTI_TEAM_LABEL)

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

    def test_load_cached_season_schedule_rejects_season_mismatch(self) -> None:
        envelope = _build_cache_envelope(
            "season_schedule",
            pd.DataFrame([{"GAME_DATE": "2026-10-21", "TEAM": "LAL"}]),
            {"season": "2026-27"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "season_schedule_cache.pkl"
            with open(cache_path, "wb") as f:
                pickle.dump(envelope, f)

            result, cache_status = _load_cached_season_schedule(cache_path, "2027-28")

        self.assertIsNone(result)
        self.assertFalse(cache_status["valid"])
        self.assertEqual(cache_status["reason"], "season-schedule cache metadata mismatch")

    def test_games_per_team_for_week_counts_only_games_in_that_iso_week(self) -> None:
        # Monday 2026-01-05 through Sunday 2026-01-11 is one ISO week.
        # LAL plays 3 games inside it, BOS plays 1 inside + 1 just after
        # (Mon 2026-01-12, the next ISO week) -- the next-week game must not
        # be counted.
        schedule = pd.DataFrame([
            {"GAME_DATE": "2026-01-05", "TEAM": "LAL"},
            {"GAME_DATE": "2026-01-07", "TEAM": "LAL"},
            {"GAME_DATE": "2026-01-10", "TEAM": "LAL"},
            {"GAME_DATE": "2026-01-06", "TEAM": "BOS"},
            {"GAME_DATE": "2026-01-12", "TEAM": "BOS"},
        ])

        counts = games_per_team_for_week(schedule, week_of="2026-01-08")

        self.assertEqual(counts["LAL"], 3)
        self.assertEqual(counts["BOS"], 1)

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

    def test_load_bbr_csv_keeps_multi_team_aggregate_row_regardless_of_file_order(self) -> None:
        # Deliberately reversed order: the real per-team rows come BEFORE the
        # aggregate "2TM" row in the file, the opposite of every real BBR CSV
        # today (per docs/superpowers/research/2026-10-09-causal-attribution-
        # layer-research.md section 2) -- this is the exact ordering that
        # would silently break if BBR ever reorders a player's rows.
        rows = [
            {"Player": "Traded Guy", "Team": "LAL", "Age": 25, "G": 20, "MP": 400,
             "FG": 80, "FGA": 160, "FG%": 0.500, "3P": 10, "FT": 20,
             "TRB": 60, "AST": 40, "STL": 10, "BLK": 5, "TOV": 20, "PF": 30, "PTS": 190},
            {"Player": "Traded Guy", "Team": "BOS", "Age": 25, "G": 25, "MP": 500,
             "FG": 100, "FGA": 200, "FG%": 0.500, "3P": 12, "FT": 25,
             "TRB": 75, "AST": 50, "STL": 12, "BLK": 6, "TOV": 25, "PF": 35, "PTS": 237},
            {"Player": "Traded Guy", "Team": "2TM", "Age": 25, "G": 45, "MP": 900,
             "FG": 180, "FGA": 360, "FG%": 0.500, "3P": 22, "FT": 45,
             "TRB": 135, "AST": 90, "STL": 22, "BLK": 11, "TOV": 45, "PF": 65, "PTS": 427},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "reversed_order.csv"
            pd.DataFrame(rows).to_csv(path, index=False)

            result = load_bbr_csv(str(path))

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["BBR_TEAM"], "2TM")
        self.assertEqual(result.iloc[0]["GP"], 45)

    def test_load_bbr_csv_carries_primary_position_through(self) -> None:
        # Needed for compute_positional_value (model.py) to know each
        # player's position. BBR occasionally writes a multi-position
        # string ("PG-SG") for dual-eligible players -- only the primary
        # (first) position is kept, same convention
        # scripts/build_draft_board.py's own pos_lookup already uses.
        rows = [
            {"Player": "Single Pos", "Team": "LAL", "Pos": "C", "Age": 25, "G": 20,
             "MP": 400, "FG": 80, "FGA": 160, "FG%": 0.500, "3P": 10, "FT": 20,
             "TRB": 60, "AST": 40, "STL": 10, "BLK": 5, "TOV": 20, "PF": 30, "PTS": 190},
            {"Player": "Dual Pos", "Team": "BOS", "Pos": "PG-SG", "Age": 25, "G": 20,
             "MP": 400, "FG": 80, "FGA": 160, "FG%": 0.500, "3P": 10, "FT": 20,
             "TRB": 60, "AST": 40, "STL": 10, "BLK": 5, "TOV": 20, "PF": 30, "PTS": 190},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "positions.csv"
            pd.DataFrame(rows).to_csv(path, index=False)

            result = load_bbr_csv(str(path))

        by_name = result.set_index("PLAYER_NAME")["POSITION"]
        self.assertEqual(by_name["Single Pos"], "C")
        self.assertEqual(by_name["Dual Pos"], "PG")

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

    def test_injury_tier_carryover_recovers_tier_from_matching_location(self) -> None:
        # Kyrie Irving shape: current season genericizes a continuing ACL
        # tear as "Surgery"; the prior season's diagnosis report named it.
        current = ["Injury/Illness - Left Knee; Surgery"]
        prior = ["Injury/Illness - Left Knee; Sprain/ACL tear",
                 "Injury/Illness - Left Knee; Surgery"]
        self.assertEqual(classify_injury_tier_with_carryover(current, prior), "acl")

    def test_injury_tier_carryover_ignores_mismatched_location(self) -> None:
        # Trae Young shape: current season's knee injury is unrelated to a
        # resolved prior-season Achilles issue -- must not carry over.
        current = ["Injury/Illness - Right Knee; MCL Sprain"]
        prior = ["Injury/Illness - Right Achilles; Tendinitis"]
        self.assertIsNone(classify_injury_tier_with_carryover(current, prior))

    def test_injury_tier_carryover_not_needed_when_current_already_classifies(self) -> None:
        current = ["Injury/Illness - Right Achilles; Rupture"]
        prior = ["Injury/Illness - Left Ankle; Sprain"]
        self.assertEqual(classify_injury_tier_with_carryover(current, prior), "achilles")

    def test_fetch_draft_history_extended_fields_invalidate_old_cache_shape(self) -> None:
        from data import _draft_history_cache_metadata
        old_shape_metadata = {"draft_years": ["2025"]}
        new_shape_metadata = _draft_history_cache_metadata(["2025"])
        self.assertNotEqual(old_shape_metadata, new_shape_metadata)

    def test_rookie_season_stats_cache_metadata_keys_on_draft_years(self) -> None:
        from data import _rookie_season_stats_cache_metadata
        self.assertEqual(
            _rookie_season_stats_cache_metadata(["2024", "2023"]),
            {"draft_years": ["2023", "2024"]},
        )

    def test_fetch_rookie_season_stats_prefers_tot_row_for_mid_season_trade(self) -> None:
        from unittest.mock import patch, MagicMock
        from data import fetch_rookie_season_stats
        import pandas as pd

        # Create synthetic career stats data: a player traded mid-season with both
        # team rows and a TOT aggregate row
        team_row = {
            "SEASON_ID": "20262027",
            "TEAM_ABBREVIATION": "BOS",
            "GP": 20.0,
            "MIN": 25.0,
            "PTS": 15.0,
            "REB": 5.0,
            "AST": 3.0,
            "STL": 1.0,
            "BLK": 0.5,
            "TOV": 1.5,
            "PF": 2.0,
            "FGM": 6.0,
            "FGA": 12.0,
            "FG_PCT": 0.500,
            "FG3M": 1.0,
            "FTM": 2.0,
        }
        tot_row = {
            "SEASON_ID": "20262027",
            "TEAM_ABBREVIATION": "TOT",
            "GP": 60.0,  # Full-season GP
            "MIN": 28.0,
            "PTS": 18.0,
            "REB": 6.0,
            "AST": 4.0,
            "STL": 1.2,
            "BLK": 0.7,
            "TOV": 2.0,
            "PF": 2.5,
            "FGM": 7.0,
            "FGA": 14.0,
            "FG_PCT": 0.500,
            "FG3M": 1.5,
            "FTM": 2.5,
        }
        career_df = pd.DataFrame([team_row, tot_row])

        draft_history = {
            "Test Player": {
                "overall_pick": 10,
                "round_number": 1,
                "person_id": 123456,
                "draft_year": "2026",
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = str(Path(tmpdir) / "test_rookie_stats.pkl")

            # Mock PlayerCareerStats to return our synthetic data
            # Patch at the location where it's imported (nba_api.stats.endpoints)
            with patch("nba_api.stats.endpoints.PlayerCareerStats") as mock_pcs:
                mock_instance = MagicMock()
                mock_instance.get_data_frames.return_value = [career_df]
                mock_pcs.return_value = mock_instance

                result = fetch_rookie_season_stats(draft_history, cache_file)

            # Verify that the TOT row was selected (GP=60.0, not 20.0)
            from identity import canonical_player_key
            player_key = canonical_player_key("Test Player")
            self.assertIn(player_key, result)
            self.assertEqual(result[player_key]["GP"], 60.0)  # TOT row's GP
            self.assertEqual(result[player_key]["PTS"], 18.0)  # TOT row's PTS


    def test_combine_stats_cache_metadata_is_a_fixed_all_time_marker(self) -> None:
        from data import _combine_stats_cache_metadata
        self.assertEqual(_combine_stats_cache_metadata(), {"season_all_time": "All Time"})


if __name__ == "__main__":
    unittest.main()
