import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from trade import BANK_COLUMNS  # noqa: E402

import analyze_trade  # noqa: E402


def _projections(rows: list[dict]) -> pd.DataFrame:
    """A minimal projections frame with the SOURCE column build_replacement_bank needs."""
    defaults = {"GP_FACTOR": 1.0}
    for col in BANK_COLUMNS:
        if col == "GAMES":
            continue
        defaults.setdefault(col, 0.0)
    return pd.DataFrame([{**defaults, **row} for row in rows])


class BuildReplacementBankTests(unittest.TestCase):
    def test_selects_a_veteran_not_a_rookie(self) -> None:
        # Mirrors the real bug: a rookie can rank above a low veteran on
        # TOTAL_VALUE (incomparable scales), but replacement level must
        # still land on the pool_size-th VETERAN.
        rows = [
            {"PLAYER_NAME": f"Vet{i}", "SOURCE": "veteran",
             "TOTAL_VALUE": 10.0 - i, "PTS": 20.0 - i, "GP_FACTOR": 1.0}
            for i in range(5)
        ]
        rows += [
            {"PLAYER_NAME": f"Rookie{i}", "SOURCE": "rookie",
             "TOTAL_VALUE": 5.0 - i, "PTS": 4.0, "GP_FACTOR": 1.0}
            for i in range(3)
        ]
        projections = _projections(rows)

        games_pool = np.array([2.0, 3.0, 3.0, 4.0])
        # pool_size (LEAGUE_CONFIG num_teams * roster_size) is much larger
        # than 5 veterans, so min(pool_size, len(veterans)) - 1 lands on the
        # LAST (worst) veteran -- Vet4, PTS=16.0 -- never a rookie, even
        # though several rookies out-rank several veterans on raw TOTAL_VALUE.
        bank = analyze_trade.build_replacement_bank(
            projections, None, {}, games_pool,
            {"seed": 1, "synthetic_bank_rows": 5_000})

        pts = bank[:, BANK_COLUMNS.index("PTS")]
        games = bank[:, BANK_COLUMNS.index("GAMES")]
        avg_pts = pts.sum() / games.sum()

        # Vet4's true rate (PTS / GP_FACTOR, both 16.0/1.0) -- nowhere near
        # a rookie's 4.0 PTS.
        self.assertAlmostEqual(avg_pts, 16.0, delta=1.5)
        self.assertGreater(avg_pts, 10.0)

    def test_real_rankings_file_selects_aj_green_not_a_rookie(self) -> None:
        # End-to-end check against the real data: the 130th-ranked veteran
        # is A.J. Green (PTS ~8.6), not the incomparable-scale rookie that
        # a naive concatenated sort would pick (Braden Smith, PTS ~4.0).
        from rosters import load_projections
        projections = load_projections(
            "durant_rankings_2026_27.csv", "durant_rankings_rookies_2026_27.csv")
        games_pool = np.array([2.0, 3.0, 3.0, 4.0])
        bank = analyze_trade.build_replacement_bank(
            projections, None, {}, games_pool,
            {"seed": 1, "synthetic_bank_rows": 5_000})
        pts = bank[:, BANK_COLUMNS.index("PTS")]
        games = bank[:, BANK_COLUMNS.index("GAMES")]
        avg_pts = pts.sum() / games.sum()
        # A.J. Green's true (GP_FACTOR-undone) rate is ~9.4; well above any
        # rookie-bucket baseline (max ~5.5 PTS in durant_rankings_rookies).
        self.assertGreater(avg_pts, 6.0)


if __name__ == "__main__":
    unittest.main()
