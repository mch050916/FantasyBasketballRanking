import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rosters import load_projections, load_rosters, resolve_roster_players


def write_csv(text: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class LoadRostersTests(unittest.TestCase):
    def test_groups_players_under_their_team(self) -> None:
        path = write_csv("TEAM,PLAYER_NAME\nA,Player One\nA,Player Two\nB,Player Three\n")
        rosters = load_rosters(path)
        self.assertEqual(rosters["A"], ["Player One", "Player Two"])
        self.assertEqual(rosters["B"], ["Player Three"])

    def test_strips_surrounding_whitespace(self) -> None:
        path = write_csv("TEAM,PLAYER_NAME\n  A  ,  Player One  \n")
        self.assertEqual(load_rosters(path), {"A": ["Player One"]})

    def test_rejects_a_file_missing_the_required_columns(self) -> None:
        path = write_csv("SQUAD,GUY\nA,Player One\n")
        with self.assertRaises(ValueError) as ctx:
            load_rosters(path)
        self.assertIn("TEAM", str(ctx.exception))

    def test_rejects_the_same_player_rostered_twice(self) -> None:
        path = write_csv("TEAM,PLAYER_NAME\nA,Player One\nB,Player One\n")
        with self.assertRaises(ValueError) as ctx:
            load_rosters(path)
        self.assertIn("Player One", str(ctx.exception))


class ResolveRosterPlayersTests(unittest.TestCase):
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


class LoadProjectionsTests(unittest.TestCase):
    def test_concatenates_the_rookie_file_when_supplied(self) -> None:
        main = write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        rookies = write_csv("PLAYER_NAME,PTS\nRookie,10\n")
        combined = load_projections(main, rookies)
        self.assertEqual(sorted(combined["PLAYER_NAME"]), ["Rookie", "Veteran"])

    def test_works_without_a_rookie_file(self) -> None:
        main = write_csv("PLAYER_NAME,PTS\nVeteran,20\n")
        self.assertEqual(len(load_projections(main)), 1)
