import unittest

from causes import (
    attribute_season_cause,
    build_player_cause_profile,
    summarize_cause_profile,
)


class AttributeSeasonCauseTests(unittest.TestCase):
    def test_near_full_season_returns_full_season_regardless_of_other_signals(self) -> None:
        # 70/82 clears the 0.78 ratio even with an injury reason present --
        # a confirmed injury on a season the player mostly played through
        # isn't a shortfall needing a cause at all.
        self.assertEqual(
            attribute_season_cause(70, 82, "LAL", ["Left Knee; ACL Tear"]),
            "full_season",
        )

    def test_confirmed_injury_wins_over_team_change_same_season(self) -> None:
        # Real data shape from docs/superpowers/research/2026-10-09-causal-
        # attribution-layer-research.md section 3: Kristaps Porzingis,
        # 2025-26, multi-team ("2TM") row with Achilles-keyword severe
        # reasons the same season.
        self.assertEqual(
            attribute_season_cause(
                gp=30,
                full_season_games=82,
                bbr_team="2TM",
                severe_reasons=[
                    "Right Achilles Tendon; Injury Management",
                    "Right Achilles; Tendinitis",
                ],
            ),
            "injury_confirmed",
        )

    def test_team_change_only_when_no_injury_match(self) -> None:
        self.assertEqual(
            attribute_season_cause(40, 82, "2TM", []),
            "team_change",
        )

    def test_unexplained_shortfall_with_no_cause_data(self) -> None:
        self.assertEqual(
            attribute_season_cause(35, 82, "LAL", []),
            "unexplained",
        )

    def test_unexplained_when_severe_reasons_do_not_match_a_known_tier(self) -> None:
        # A real severe-injury entry that isn't one of the 3 study-backed
        # tiers (achilles/acl/meniscus) stays unexplained for GP_FACTOR
        # purposes -- matches data.py's own classify_injury_tier contract.
        self.assertEqual(
            attribute_season_cause(35, 82, "LAL", ["Right Ankle; Sprain"]),
            "unexplained",
        )


class BuildPlayerCauseProfileTests(unittest.TestCase):
    def test_builds_per_player_per_season_labels_from_raw_name_keyed_inputs(self) -> None:
        seasons = ["2025-26", "2024-25"]
        gp_by_season = {
            "2025-26": {"Kristaps Porzingis": 30, "Healthy Guy": 80},
            "2024-25": {"Kristaps Porzingis": 65, "Healthy Guy": 78},
        }
        team_by_season = {
            "2025-26": {"Kristaps Porzingis": "2TM", "Healthy Guy": "LAL"},
            "2024-25": {"Kristaps Porzingis": "BOS", "Healthy Guy": "LAL"},
        }
        # Keyed by canonical_player_key, matching main.py's existing
        # severe_injury_by_key construction pattern.
        severe_reasons_by_season = {
            "2025-26": {
                "kristapsporzingis": [
                    "Right Achilles Tendon; Injury Management",
                    "Right Achilles; Tendinitis",
                ],
            },
            "2024-25": {},
        }

        profile = build_player_cause_profile(
            seasons, gp_by_season, team_by_season, severe_reasons_by_season,
        )

        self.assertEqual(profile["Kristaps Porzingis"]["2025-26"], "injury_confirmed")
        self.assertEqual(profile["Kristaps Porzingis"]["2024-25"], "full_season")
        self.assertEqual(profile["Healthy Guy"]["2025-26"], "full_season")
        self.assertEqual(profile["Healthy Guy"]["2024-25"], "full_season")

    def test_skips_players_with_nan_gp_for_a_season(self) -> None:
        import math

        profile = build_player_cause_profile(
            seasons=["2025-26"],
            gp_by_season={"2025-26": {"No Row": math.nan}},
            team_by_season={"2025-26": {}},
            severe_reasons_by_season={"2025-26": {}},
        )
        self.assertNotIn("2025-26", profile.get("No Row", {}))


class SummarizeCauseProfileTests(unittest.TestCase):
    def test_returns_most_recent_confirmed_cause(self) -> None:
        causes = {"2024-25": "injury_confirmed", "2023-24": "team_change"}
        self.assertEqual(
            summarize_cause_profile(causes, ["2025-26", "2024-25", "2023-24"]),
            "2024-25: injury_confirmed",
        )

    def test_returns_empty_string_when_nothing_confirmed(self) -> None:
        causes = {"2024-25": "full_season", "2023-24": "unexplained"}
        self.assertEqual(
            summarize_cause_profile(causes, ["2025-26", "2024-25", "2023-24"]),
            "",
        )
