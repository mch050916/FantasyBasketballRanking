import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rosters import (load_projections, load_rosters, player_value_percentiles,
                    resolve_roster_players)


class RostersTestBase(unittest.TestCase):
    def write_csv(self, text: str) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.write(text)
        handle.close()
        path = handle.name
        self.addCleanup(os.unlink, path)
        return path


class LoadRostersTests(RostersTestBase):
    def test_groups_players_under_their_team(self) -> None:
        path = self.write_csv("TEAM,PLAYER_NAME\nA,Player One\nA,Player Two\nB,Player Three\n")
        rosters = load_rosters(path)
        self.assertEqual(rosters["A"], ["Player One", "Player Two"])
        self.assertEqual(rosters["B"], ["Player Three"])

    def test_strips_surrounding_whitespace(self) -> None:
        path = self.write_csv("TEAM,PLAYER_NAME\n  A  ,  Player One  \n")
        self.assertEqual(load_rosters(path), {"A": ["Player One"]})

    def test_rejects_a_file_missing_the_required_columns(self) -> None:
        path = self.write_csv("SQUAD,GUY\nA,Player One\n")
        with self.assertRaises(ValueError) as ctx:
            load_rosters(path)
        self.assertIn("TEAM", str(ctx.exception))

    def test_rejects_the_same_player_rostered_twice(self) -> None:
        path = self.write_csv("TEAM,PLAYER_NAME\nA,Player One\nB,Player One\n")
        with self.assertRaises(ValueError) as ctx:
            load_rosters(path)
        self.assertIn("Player One", str(ctx.exception))

    def test_rejects_the_same_player_rostered_twice_with_accent_differences(self) -> None:
        path = self.write_csv("TEAM,PLAYER_NAME\nA,Nikola Jokic\nB,Nikola Jokić\n")
        with self.assertRaises(ValueError) as ctx:
            load_rosters(path)
        message = str(ctx.exception)
        self.assertIn("Nikola Jokic", message)
        self.assertIn("Nikola Jokić", message)


class ResolveRosterPlayersTests(RostersTestBase):
    def _projections(self) -> pd.DataFrame:
        return pd.DataFrame({"PLAYER_NAME": ["Nikola Jokić", "Luka Dončić"],
                             "PTS": [25.0, 30.0]})

    def test_matches_across_accent_differences(self) -> None:
        resolved = resolve_roster_players({"A": ["Nikola Jokic"]}, self._projections())
        self.assertEqual(resolved["A"], ["Nikola Jokić"])

    def test_error_names_the_unresolved_player_and_suggests_near_misses(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_roster_players({"A": ["Nikola Jokicc"]}, self._projections())
        message = str(ctx.exception)
        self.assertIn("Nikola Jokicc", message)
        self.assertIn("Nikola Jokić", message)


class LoadProjectionsTests(RostersTestBase):
    def test_concatenates_the_rookie_file_when_supplied(self) -> None:
        main = self.write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        rookies = self.write_csv("PLAYER_NAME,PTS\nRookie,10\n")
        combined = load_projections(main, rookies)
        self.assertEqual(sorted(combined["PLAYER_NAME"]), ["Rookie", "Veteran"])

    def test_works_without_a_rookie_file(self) -> None:
        main = self.write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        self.assertEqual(len(load_projections(main)), 1)

    def test_tags_rows_with_their_source(self) -> None:
        main = self.write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        rookies = self.write_csv("PLAYER_NAME,PTS\nRookie,10\n")
        combined = load_projections(main, rookies)
        by_name = combined.set_index("PLAYER_NAME")["SOURCE"]
        self.assertEqual(by_name["Veteran"], "veteran")
        self.assertEqual(by_name["Rookie"], "rookie")

    def test_source_is_veteran_only_without_a_rookie_file(self) -> None:
        main = self.write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        combined = load_projections(main)
        self.assertEqual(combined["SOURCE"].tolist(), ["veteran"])


class PlayerValuePercentilesTests(RostersTestBase):
    def test_within_source_percentile_puts_a_top_rookie_near_a_top_veteran(self) -> None:
        # The bug this replaces: sorting raw TOTAL_VALUE puts every rookie
        # below the worst veteran, because the two populations are scored
        # against different pools and are not on the same scale. Ranking
        # each SOURCE group separately fixes that -- the best rookie and the
        # best veteran should both land near 1.0, not the rookie near 0.0.
        projections = pd.DataFrame([
            {"PLAYER_NAME": "TopVet", "SOURCE": "veteran", "TOTAL_VALUE": 5.0},
            {"PLAYER_NAME": "MidVet", "SOURCE": "veteran", "TOTAL_VALUE": 0.0},
            {"PLAYER_NAME": "WorstVet", "SOURCE": "veteran", "TOTAL_VALUE": -7.0},
            {"PLAYER_NAME": "TopRookie", "SOURCE": "rookie", "TOTAL_VALUE": -1.9},
            {"PLAYER_NAME": "WorstRookie", "SOURCE": "rookie", "TOTAL_VALUE": -5.0},
        ])
        percentiles = player_value_percentiles(projections)

        # Both "best in their population" -- close together, not the rookie
        # buried under the worst veteran.
        self.assertAlmostEqual(percentiles["TopVet"], percentiles["TopRookie"], delta=0.01)
        self.assertEqual(percentiles["TopVet"], 1.0)
        self.assertEqual(percentiles["TopRookie"], 1.0)

        # Ordering is preserved within each source.
        self.assertGreater(percentiles["TopVet"], percentiles["MidVet"])
        self.assertGreater(percentiles["MidVet"], percentiles["WorstVet"])
        self.assertGreater(percentiles["TopRookie"], percentiles["WorstRookie"])

        # And critically: the worst veteran does NOT read as catastrophically
        # far below the worst rookie the way raw TOTAL_VALUE would (-7.0 vs
        # -5.0 masks that WorstVet is merely "last of 3" while WorstRookie is
        # "last of 2" -- both are legitimately near the bottom of their own
        # population, not one artificially crushed by the other's scale).
        self.assertGreater(percentiles["WorstVet"], 0.0)
        self.assertGreater(percentiles["WorstRookie"], 0.0)
