import tempfile
import unittest
from pathlib import Path

import pandas as pd

from main import build_extra_rows, derive_pool_size


def _qualified_pool(n_players: int) -> pd.DataFrame:
    """A MIN-ranked pool: Player 0 has the most minutes, Player N-1 the least."""
    return pd.DataFrame([
        {"PLAYER_NAME": f"Player {i}", "MIN": float(40 - i), "PTS": 10.0}
        for i in range(n_players)
    ])


class DerivePoolSizeTests(unittest.TestCase):
    def test_no_rosters_file_returns_the_flat_floor(self) -> None:
        config = {"num_teams": 10, "roster_size": 13}
        qualified_pool = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = str(Path(tmpdir) / "rosters.csv")
            result = derive_pool_size(config, qualified_pool, rosters_file=missing_path)

        self.assertEqual(result, 130)

    def test_rosters_file_with_all_players_inside_the_floor_still_returns_the_floor(self) -> None:
        config = {"num_teams": 10, "roster_size": 13}
        qualified_pool = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            # Both rostered players rank well inside the top 130 by MIN
            # (Player 0 is rank 1, Player 50 is rank 51) -- the buffer must
            # not inflate pool_size past the floor in this case.
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Player 50"},
            ]).to_csv(rosters_path, index=False)

            result = derive_pool_size(config, qualified_pool, rosters_file=str(rosters_path))

        self.assertEqual(result, 130)

    def test_a_deeply_rostered_player_widens_the_pool_by_rank_plus_buffer(self) -> None:
        config = {"num_teams": 10, "roster_size": 13}
        qualified_pool = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            # Player 219 is rank 220 (1-indexed) in qualified_pool.
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Player 219"},
            ]).to_csv(rosters_path, index=False)

            result = derive_pool_size(config, qualified_pool, rosters_file=str(rosters_path), buffer=30)

        self.assertEqual(result, 250)  # 220 + 30

    def test_an_unresolvable_rostered_name_is_silently_skipped(self) -> None:
        config = {"num_teams": 10, "roster_size": 13}
        qualified_pool = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Not A Real Player Name"},
            ]).to_csv(rosters_path, index=False)

            # Must not raise -- only the resolvable name (rank 1) counts,
            # so this stays at the floor.
            result = derive_pool_size(config, qualified_pool, rosters_file=str(rosters_path))

        self.assertEqual(result, 130)

    def test_a_rostered_name_matches_via_canonical_key_not_raw_equality(self) -> None:
        # rosters.csv commonly has suffixed/alternate spellings (e.g. "Jimmy
        # Butler III") that don't literally equal the projections' spelling
        # (e.g. "Jimmy Butler"). Every other roster<->projection join in this
        # repo goes through identity.canonical_player_key -- derive_pool_size
        # must too, or a deeply-rostered player silently falls out of the
        # depth calculation instead of widening the pool.
        config = {"num_teams": 10, "roster_size": 13}
        qualified_pool = _qualified_pool(300)
        qualified_pool.loc[219, "PLAYER_NAME"] = "Jimmy Butler"

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Jimmy Butler III"},
            ]).to_csv(rosters_path, index=False)

            result = derive_pool_size(config, qualified_pool, rosters_file=str(rosters_path), buffer=30)

        self.assertEqual(result, 250)  # rank 220 + 30, not silently skipped


class BuildExtraRowsTests(unittest.TestCase):
    def test_no_rosters_file_returns_empty(self) -> None:
        projected = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = str(Path(tmpdir) / "rosters.csv")
            result = build_extra_rows(projected, pool_size=130, rosters_file=missing_path)

        self.assertEqual(len(result), 0)
        self.assertEqual(list(result.columns), list(projected.columns))

    def test_rostered_players_already_inside_the_pool_produce_no_extra_rows(self) -> None:
        projected = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Player 50"},
            ]).to_csv(rosters_path, index=False)

            result = build_extra_rows(projected, pool_size=130, rosters_file=str(rosters_path))

        self.assertEqual(len(result), 0)

    def test_a_rostered_player_outside_the_pool_is_returned(self) -> None:
        projected = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            # Player 219 (rank 220) sits outside a 130-player pool.
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Player 0"},
                {"TEAM": "Chester", "PLAYER_NAME": "Player 219"},
            ]).to_csv(rosters_path, index=False)

            result = build_extra_rows(projected, pool_size=130, rosters_file=str(rosters_path))

        self.assertEqual(list(result["PLAYER_NAME"]), ["Player 219"])

    def test_matches_via_canonical_key_not_raw_equality(self) -> None:
        projected = _qualified_pool(300)
        projected.loc[219, "PLAYER_NAME"] = "Jimmy Butler"

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Jimmy Butler III"},
            ]).to_csv(rosters_path, index=False)

            result = build_extra_rows(projected, pool_size=130, rosters_file=str(rosters_path))

        self.assertEqual(list(result["PLAYER_NAME"]), ["Jimmy Butler"])

    def test_an_unresolvable_rostered_name_is_silently_skipped(self) -> None:
        projected = _qualified_pool(300)

        with tempfile.TemporaryDirectory() as tmpdir:
            rosters_path = Path(tmpdir) / "rosters.csv"
            pd.DataFrame([
                {"TEAM": "Chester", "PLAYER_NAME": "Not A Real Player Name"},
            ]).to_csv(rosters_path, index=False)

            result = build_extra_rows(projected, pool_size=130, rosters_file=str(rosters_path))

        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
