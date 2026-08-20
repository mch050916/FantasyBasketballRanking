import unittest

import numpy as np
import pandas as pd

from trade import BANK_COLUMNS, build_week_bank, games_per_week_pool, player_rng, scale_bank_to_projection, synthesize_bank


def make_log(dates: list[str], **stats) -> pd.DataFrame:
    """Build a minimal NBA-API-shaped game log for testing."""
    n = len(dates)
    base = {"GAME_DATE": dates, "FGM": [0] * n, "FGA": [0] * n, "FG3M": [0] * n,
            "FTM": [0] * n, "PTS": [0] * n, "REB": [0] * n, "AST": [0] * n,
            "STL": [0] * n, "BLK": [0] * n, "TOV": [0] * n, "PF": [0] * n,
            "DD2": [0] * n, "TD3": [0] * n}
    base.update(stats)
    return pd.DataFrame(base)


class BuildWeekBankTests(unittest.TestCase):
    def test_sums_games_within_a_week_and_splits_across_weeks(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(
            ["2026-01-05", "2026-01-07", "2026-01-12"],
            PTS=[10, 20, 30], REB=[1, 2, 3])}}
        bank = build_week_bank(logs)["Test Player"]
        pts = bank[:, BANK_COLUMNS.index("PTS")]
        games = bank[:, BANK_COLUMNS.index("GAMES")]
        self.assertEqual(bank.shape[0], 2)
        self.assertEqual(sorted(pts.tolist()), [30.0, 30.0])
        self.assertEqual(sorted(games.tolist()), [1.0, 2.0])

    def test_renames_api_columns_to_league_category_names(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(
            ["2026-01-05"], STL=[3], TOV=[4], FG3M=[5], DD2=[1], TD3=[1])}}
        bank = build_week_bank(logs)["Test Player"]
        self.assertEqual(bank[0, BANK_COLUMNS.index("ST")], 3.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("TO")], 4.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("3PTM")], 5.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("DD")], 1.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("TD")], 1.0)

    def test_tech_is_proxied_from_personal_fouls(self) -> None:
        logs = {"2025-26": {"Test Player": make_log(["2026-01-05"], PF=[5])}}
        bank = build_week_bank(logs)["Test Player"]
        self.assertAlmostEqual(bank[0, BANK_COLUMNS.index("TECH")], 5 * 0.012)

    def test_stacks_weeks_from_every_season(self) -> None:
        logs = {"2025-26": {"P": make_log(["2026-01-05"], PTS=[10])},
                "2024-25": {"P": make_log(["2025-01-06"], PTS=[20])}}
        self.assertEqual(build_week_bank(logs)["P"].shape[0], 2)

    def test_skips_players_with_empty_logs(self) -> None:
        logs = {"2025-26": {"P": pd.DataFrame()}}
        self.assertNotIn("P", build_week_bank(logs))

    def test_a_missing_column_reads_as_zero_rather_than_dropping_the_player(self) -> None:
        log = make_log(["2026-01-05"], PTS=[10]).drop(columns=["DD2"])
        bank = build_week_bank({"2025-26": {"P": log}})["P"]
        self.assertEqual(bank[0, BANK_COLUMNS.index("PTS")], 10.0)
        self.assertEqual(bank[0, BANK_COLUMNS.index("DD")], 0.0)


class ScaleBankTests(unittest.TestCase):
    def _bank(self, pts: list[float], games: list[float]) -> np.ndarray:
        bank = np.zeros((len(pts), len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("PTS")] = pts
        bank[:, BANK_COLUMNS.index("GAMES")] = games
        return bank

    def test_scales_totals_to_hit_the_projected_per_game_rate(self) -> None:
        # 60 points over 6 games = 10.0 per game historically.
        bank = self._bank([30.0, 30.0], [3.0, 3.0])
        scaled = scale_bank_to_projection(bank, {"PTS": 20.0})
        pts = scaled[:, BANK_COLUMNS.index("PTS")]
        games = scaled[:, BANK_COLUMNS.index("GAMES")]
        self.assertAlmostEqual(pts.sum() / games.sum(), 20.0)

    def test_games_column_is_never_scaled(self) -> None:
        bank = self._bank([30.0], [3.0])
        scaled = scale_bank_to_projection(bank, {"PTS": 90.0})
        self.assertEqual(scaled[0, BANK_COLUMNS.index("GAMES")], 3.0)

    def test_zero_historical_rate_falls_back_to_scale_one(self) -> None:
        # A player who never recorded a triple-double keeps simulating zeros.
        bank = self._bank([30.0], [3.0])
        scaled = scale_bank_to_projection(bank, {"PTS": 10.0, "TD": 0.5})
        self.assertEqual(scaled[0, BANK_COLUMNS.index("TD")], 0.0)

    def test_scale_is_clipped_at_both_bounds(self) -> None:
        bank = self._bank([30.0], [3.0])  # 10.0 per game
        high = scale_bank_to_projection(bank, {"PTS": 1000.0})
        low = scale_bank_to_projection(bank, {"PTS": 0.5})
        self.assertAlmostEqual(high[0, BANK_COLUMNS.index("PTS")], 30.0 * 4.0)
        self.assertAlmostEqual(low[0, BANK_COLUMNS.index("PTS")], 30.0 * 0.25)

    def test_missing_projection_key_zeroes_the_category(self) -> None:
        # A zero projection means zero, not the 0.25 clip floor -- the clip
        # guards a tiny denominator, not a legitimate zero numerator.
        bank = self._bank([30.0], [3.0])
        scaled = scale_bank_to_projection(bank, {})
        self.assertEqual(scaled[0, BANK_COLUMNS.index("PTS")], 0.0)

    def test_does_not_mutate_the_input_bank(self) -> None:
        bank = self._bank([30.0], [3.0])
        scale_bank_to_projection(bank, {"PTS": 20.0})
        self.assertEqual(bank[0, BANK_COLUMNS.index("PTS")], 30.0)

    def test_nan_games_returns_unscaled_bank(self) -> None:
        # A bank with NaN in the GAMES column should return unscaled, not all-NaN.
        bank = self._bank([30.0], [np.nan])
        scaled = scale_bank_to_projection(bank, {"PTS": 20.0})
        self.assertEqual(scaled[0, BANK_COLUMNS.index("PTS")], 30.0)


class PlayerRngTests(unittest.TestCase):
    def test_same_name_and_seed_give_identical_draws(self) -> None:
        a = player_rng("Nikola Jokic", 7).integers(0, 100, size=20)
        b = player_rng("Nikola Jokic", 7).integers(0, 100, size=20)
        np.testing.assert_array_equal(a, b)

    def test_different_names_give_different_draws(self) -> None:
        a = player_rng("Nikola Jokic", 7).integers(0, 100, size=20)
        b = player_rng("Luka Doncic", 7).integers(0, 100, size=20)
        self.assertFalse(np.array_equal(a, b))

    def test_purpose_separates_streams_for_the_same_player(self) -> None:
        a = player_rng("P", 7, "draw").integers(0, 100, size=20)
        b = player_rng("P", 7, "synth").integers(0, 100, size=20)
        self.assertFalse(np.array_equal(a, b))


class SynthesizeBankTests(unittest.TestCase):
    def test_hits_the_projected_per_game_rate_on_average(self) -> None:
        pool = np.array([3.0, 4.0])
        bank = synthesize_bank("Rookie", {"PTS": 12.0}, {"PTS": 3.0}, pool,
                               seed=1, n_rows=20_000)
        pts = bank[:, BANK_COLUMNS.index("PTS")]
        games = bank[:, BANK_COLUMNS.index("GAMES")]
        self.assertAlmostEqual(pts.sum() / games.sum(), 12.0, delta=0.15)

    def test_never_produces_a_negative_stat_line(self) -> None:
        pool = np.array([3.0])
        bank = synthesize_bank("Rookie", {"PTS": 1.0}, {"PTS": 10.0}, pool,
                               seed=1, n_rows=2_000)
        self.assertTrue((bank >= 0).all())

    def test_games_are_drawn_from_the_supplied_pool(self) -> None:
        bank = synthesize_bank("Rookie", {"PTS": 10.0}, {"PTS": 1.0},
                               np.array([2.0, 5.0]), seed=1, n_rows=500)
        drawn = set(bank[:, BANK_COLUMNS.index("GAMES")].tolist())
        self.assertTrue(drawn.issubset({2.0, 5.0}))

    def test_is_deterministic_for_a_fixed_seed(self) -> None:
        args = ("Rookie", {"PTS": 10.0}, {"PTS": 2.0}, np.array([3.0]), 1, 100)
        np.testing.assert_array_equal(synthesize_bank(*args), synthesize_bank(*args))


class GamesPerWeekPoolTests(unittest.TestCase):
    def test_collects_every_observed_week_length(self) -> None:
        bank = np.zeros((3, len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("GAMES")] = [2.0, 3.0, 4.0]
        pool = games_per_week_pool({"P": bank})
        self.assertEqual(sorted(pool.tolist()), [2.0, 3.0, 4.0])

    def test_falls_back_to_a_nominal_week_when_no_banks_exist(self) -> None:
        self.assertTrue(len(games_per_week_pool({})) > 0)
