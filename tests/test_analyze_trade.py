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


def _rates(**cats) -> dict:
    return {c: {"win": w, "tie": t, "loss": 1.0 - w - t} for c, (w, t) in cats.items()}


class FormatReportTests(unittest.TestCase):
    """
    The per-category table must use the same convention as the headline it
    explains. Reporting raw win rates while the headline counted a tie as half
    a win left the two disagreeing with no way to see where the gap went.
    """

    def _result(self) -> dict:
        before = _rates(PTS=(0.60, 0.00), DD=(0.40, 0.20))
        after = _rates(PTS=(0.50, 0.00), DD=(0.55, 0.20))
        exp = lambda r: sum(v["win"] + 0.5 * v["tie"] for v in r.values())
        return {
            "before": {"Me": {"expected": exp(before), "rates": before},
                       "You": {"expected": 0.0, "rates": before}},
            "after": {"Me": {"expected": exp(after), "rates": after},
                      "You": {"expected": 0.0, "rates": after}},
            "delta": {}, "roster_sizes_after": {},
        }

    def test_the_category_column_sums_to_the_headline(self) -> None:
        text = analyze_trade.format_report(self._result(), "Me", "You", ["X"], ["Y"])
        line = [l for l in text.splitlines() if "(column sum)" in l][0]
        column_sum = float(line.split()[2])
        headline = float(line.split("headline")[1])
        self.assertAlmostEqual(column_sum, headline, places=3)

    def test_a_tie_heavy_category_counts_half_a_win(self) -> None:
        # DD: win .40 tie .20 -> .50 before, win .55 tie .20 -> .65 after.
        text = analyze_trade.format_report(self._result(), "Me", "You", [], [])
        dd = [l for l in text.splitlines() if l.strip().startswith("DD")][0].split()
        self.assertAlmostEqual(float(dd[1]), 0.50, places=3)
        self.assertAlmostEqual(float(dd[2]), 0.65, places=3)

    def test_the_tie_percentage_is_still_shown(self) -> None:
        text = analyze_trade.format_report(self._result(), "Me", "You", [], [])
        dd = [l for l in text.splitlines() if l.strip().startswith("DD")][0]
        self.assertIn("20.0", dd)


class LeagueShapeWarningTests(unittest.TestCase):
    """A roster file whose shape disagrees with the league must say so."""

    def _full_league(self) -> dict:
        size = analyze_trade.LEAGUE_CONFIG["roster_size"]
        return {f"T{t}": [f"P{t}_{p}" for p in range(size)]
                for t in range(analyze_trade.LEAGUE_CONFIG["num_teams"])}

    def test_a_correctly_shaped_league_warns_about_nothing(self) -> None:
        self.assertEqual(analyze_trade.warn_league_shape(self._full_league()), [])

    def test_too_few_teams_is_flagged(self) -> None:
        league = self._full_league()
        trimmed = {k: league[k] for k in list(league)[:2]}
        warnings = analyze_trade.warn_league_shape(trimmed)
        self.assertTrue(any("2 teams" in w for w in warnings))

    def test_an_odd_roster_size_is_flagged_with_the_team_name(self) -> None:
        league = self._full_league()
        league["T3"] = league["T3"][:-2]
        warnings = analyze_trade.warn_league_shape(league)
        self.assertTrue(any("T3" in w for w in warnings))


class DataQualityWarningTests(unittest.TestCase):
    """DATA_AVAILABILITY_NOTE already exists upstream; it must reach the user."""

    def test_a_rostered_player_with_a_note_is_surfaced(self) -> None:
        proj = _projections([
            {"PLAYER_NAME": "Flagged", "DATA_AVAILABILITY_NOTE": "projected from 2024-25"},
            {"PLAYER_NAME": "Clean", "DATA_AVAILABILITY_NOTE": ""},
        ])
        out = analyze_trade.warn_data_quality(proj, {"A": ["Flagged", "Clean"]})
        self.assertEqual(len(out), 1)
        self.assertIn("Flagged", out[0])
        self.assertIn("projected from 2024-25", out[0])

    def test_an_unrostered_flagged_player_is_not_surfaced(self) -> None:
        proj = _projections([
            {"PLAYER_NAME": "Flagged", "DATA_AVAILABILITY_NOTE": "stale"},
            {"PLAYER_NAME": "Clean", "DATA_AVAILABILITY_NOTE": ""},
        ])
        self.assertEqual(analyze_trade.warn_data_quality(proj, {"A": ["Clean"]}), [])

    def test_a_frame_without_the_column_is_handled(self) -> None:
        proj = _projections([{"PLAYER_NAME": "Clean"}]).drop(columns=["DATA_AVAILABILITY_NOTE"],
                                                             errors="ignore")
        self.assertEqual(analyze_trade.warn_data_quality(proj, {"A": ["Clean"]}), [])
