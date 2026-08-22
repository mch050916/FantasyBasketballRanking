import unittest

import numpy as np
import pandas as pd

from config import LEAGUE_CONFIG, TRADE_CONFIG
from trade import BANK_COLUMNS, add_missed_weeks, apply_trade, build_week_bank, pooled_donor_bank, quantize_bank_counts, category_win_rates, evaluate_roster_vs_field, evaluate_trade, expected_categories_won, games_per_week_pool, pad_to_roster_size, player_rng, scale_bank_to_projection, simulate_team_totals, synthesize_bank, trim_to_roster_size


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

    def test_gp_factor_targets_the_true_rate_not_the_baked_in_projection(self) -> None:
        # model.py bakes GP_FACTOR into every projected rate. A gp_factor of
        # 0.5 means the passed-in projection is HALF the player's true
        # per-game rate, so the bank must scale to DOUBLE the projected number.
        bank = self._bank([30.0], [3.0])  # 10.0 per game historically
        scaled = scale_bank_to_projection(bank, {"PTS": 20.0}, gp_factor=0.5)
        pts = scaled[:, BANK_COLUMNS.index("PTS")]
        games = scaled[:, BANK_COLUMNS.index("GAMES")]
        self.assertAlmostEqual(pts.sum() / games.sum(), 40.0)

    def test_gp_factor_of_one_reproduces_prior_behaviour_exactly(self) -> None:
        bank = self._bank([30.0, 30.0], [3.0, 3.0])
        default = scale_bank_to_projection(bank, {"PTS": 20.0})
        explicit = scale_bank_to_projection(bank, {"PTS": 20.0}, gp_factor=1.0)
        np.testing.assert_array_equal(default, explicit)
        pts = explicit[:, BANK_COLUMNS.index("PTS")]
        games = explicit[:, BANK_COLUMNS.index("GAMES")]
        self.assertAlmostEqual(pts.sum() / games.sum(), 20.0)

    def test_missing_or_invalid_gp_factor_falls_back_to_one(self) -> None:
        bank = self._bank([30.0], [3.0])
        baseline = scale_bank_to_projection(bank, {"PTS": 20.0}, gp_factor=1.0)
        for bad in (None, 0.0, -1.0, float("nan"), float("inf")):
            scaled = scale_bank_to_projection(bank, {"PTS": 20.0}, gp_factor=bad)
            np.testing.assert_array_equal(scaled, baseline)


class AddMissedWeeksTests(unittest.TestCase):
    def _bank(self, n_rows: int, to_per_game: float = 4.0, games: float = 4.0) -> np.ndarray:
        bank = np.zeros((n_rows, len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("GAMES")] = games
        bank[:, BANK_COLUMNS.index("TO")] = to_per_game * games
        bank[:, BANK_COLUMNS.index("PTS")] = 25.0
        return bank

    def test_availability_of_one_returns_the_bank_unchanged(self) -> None:
        bank = self._bank(10)
        result = add_missed_weeks(bank, 1.0)
        np.testing.assert_array_equal(result, bank)

    def test_missing_or_non_finite_availability_returns_the_bank_unchanged(self) -> None:
        bank = self._bank(10)
        for value in (None, float("nan"), float("inf")):
            np.testing.assert_array_equal(add_missed_weeks(bank, value), bank)

    def test_appends_the_right_proportion_of_zero_rows(self) -> None:
        # availability = 0.5 -> Z = N * (1 - 0.5) / 0.5 = N: doubles the bank.
        bank = self._bank(10)
        result = add_missed_weeks(bank, 0.5)
        self.assertEqual(result.shape[0], 20)

        # availability = 0.8 -> Z = 10 * 0.2 / 0.8 = 2.5 -> round to 2 (banker's
        # rounding on .5 ties, but this lands cleanly regardless).
        result_80 = add_missed_weeks(bank, 0.8)
        expected_zero_rows = round(10 * (1 - 0.8) / 0.8)
        self.assertEqual(result_80.shape[0], 10 + expected_zero_rows)

    def test_a_uniform_draw_hits_a_zero_row_with_probability_one_minus_availability(self) -> None:
        bank = self._bank(10)
        result = add_missed_weeks(bank, 0.5)
        games_idx = BANK_COLUMNS.index("GAMES")
        zero_rows = (result[:, games_idx] == 0.0).sum()
        self.assertAlmostEqual(zero_rows / result.shape[0], 0.5)

    def test_a_zero_row_is_zero_in_every_column_including_games(self) -> None:
        bank = self._bank(4, to_per_game=8.0)
        result = add_missed_weeks(bank, 0.5)
        zero_rows = result[result[:, BANK_COLUMNS.index("GAMES")] == 0.0]
        self.assertTrue((zero_rows == 0.0).all())
        # And there actually are zero rows to check, not a vacuous pass.
        self.assertGreater(zero_rows.shape[0], 0)

    def test_availability_is_clamped_so_z_cannot_explode(self) -> None:
        bank = self._bank(5)
        result = add_missed_weeks(bank, 1e-9)
        # Clamped to MIN_AVAILABILITY_FOR_MISSED_WEEKS (0.05): Z = 5*0.95/0.05 = 95.
        self.assertEqual(result.shape[0], 100)

    def test_an_empty_bank_is_returned_unchanged(self) -> None:
        bank = np.zeros((0, len(BANK_COLUMNS)))
        result = add_missed_weeks(bank, 0.5)
        self.assertEqual(result.shape[0], 0)

    def test_does_not_mutate_the_input_bank(self) -> None:
        bank = self._bank(5)
        original = bank.copy()
        add_missed_weeks(bank, 0.5)
        np.testing.assert_array_equal(bank, original)


class GpFactorDoubleDiscountTests(unittest.TestCase):
    """
    Regression coverage for the critical whole-branch-review finding: model.py
    bakes GP_FACTOR into every projected rate, and the bank's GAMES column is
    already empirical availability, so rescaling straight to the projected
    rate double-discounted fragile players -- catastrophically for low-is-
    better categories like TO, where it made them look artificially clean
    (e.g. Embiid's simulated TO ratio vs real per-game rate was 0.485).
    """

    def _true_rate_bank(self, per_game_to: float, n_weeks: int = 20,
                        games_per_week: float = 4.0) -> np.ndarray:
        bank = np.zeros((n_weeks, len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("GAMES")] = games_per_week
        bank[:, BANK_COLUMNS.index("TO")] = per_game_to * games_per_week
        return bank

    def _per_game_played_to(self, bank: np.ndarray, n_weeks: int = 20_000,
                            seed: int = 5) -> float:
        totals = simulate_team_totals({"P": bank}, n_weeks=n_weeks, seed=seed)
        to_total = totals[:, BANK_COLUMNS.index("TO")].sum()
        games_total = totals[:, BANK_COLUMNS.index("GAMES")].sum()
        return to_total / games_total

    def test_fragile_high_turnover_player_still_reads_worse_than_a_durable_low_turnover_one(self) -> None:
        # Fragile: genuinely turnover-prone (6.0/game true rate), discounted
        # by a harsh GP_FACTOR (0.5) in the projection file -- the exact
        # shape (Embiid/Anthony Davis) that motivated this fix.
        fragile_true_rate, fragile_gp_factor = 6.0, 0.5
        fragile_bank = self._true_rate_bank(fragile_true_rate)
        fragile_projected = {"TO": fragile_true_rate * fragile_gp_factor}  # baked, like model.py

        # Durable: genuinely cleaner (4.0/game true rate), full availability.
        durable_true_rate, durable_gp_factor = 4.0, 1.0
        durable_bank = self._true_rate_bank(durable_true_rate)
        durable_projected = {"TO": durable_true_rate * durable_gp_factor}

        fragile_final = add_missed_weeks(
            scale_bank_to_projection(fragile_bank, fragile_projected, gp_factor=fragile_gp_factor),
            fragile_gp_factor)
        durable_final = add_missed_weeks(
            scale_bank_to_projection(durable_bank, durable_projected, gp_factor=durable_gp_factor),
            durable_gp_factor)

        fragile_rate = self._per_game_played_to(fragile_final)
        durable_rate = self._per_game_played_to(durable_final)

        self.assertGreater(fragile_rate, durable_rate)
        self.assertAlmostEqual(fragile_rate, fragile_true_rate, delta=0.05)
        self.assertAlmostEqual(durable_rate, durable_true_rate, delta=0.05)

    def test_the_old_double_counted_scaling_would_have_reversed_the_ordering(self) -> None:
        # Confirms this scenario really does exercise the bug: scaling straight
        # to the already-GP_FACTOR-baked projected rate (gp_factor omitted,
        # the pre-fix call shape) makes the fragile player's simulated TO/game
        # LOWER than the durable player's, even though fragile's true rate is
        # higher -- exactly the defect this fix corrects.
        fragile_true_rate, fragile_gp_factor = 6.0, 0.5
        fragile_bank = self._true_rate_bank(fragile_true_rate)
        fragile_projected = {"TO": fragile_true_rate * fragile_gp_factor}

        durable_true_rate, durable_gp_factor = 4.0, 1.0
        durable_bank = self._true_rate_bank(durable_true_rate)
        durable_projected = {"TO": durable_true_rate * durable_gp_factor}

        old_fragile = scale_bank_to_projection(fragile_bank, fragile_projected)
        old_durable = scale_bank_to_projection(durable_bank, durable_projected)

        games_idx, to_idx = BANK_COLUMNS.index("GAMES"), BANK_COLUMNS.index("TO")
        fragile_rate = old_fragile[:, to_idx].sum() / old_fragile[:, games_idx].sum()
        durable_rate = old_durable[:, to_idx].sum() / old_durable[:, games_idx].sum()

        self.assertLess(fragile_rate, durable_rate)

    def test_the_exact_zero_null_trade_survives_gp_factor_scaling_and_missed_weeks(self) -> None:
        # End-to-end re-confirmation of the invariant the whole
        # common-random-numbers design rests on, now that banks are built
        # through scale_bank_to_projection(gp_factor=...) + add_missed_weeks
        # rather than raw constant banks.
        rng = np.random.default_rng(11)
        raw_banks = {}
        gp_factors = {}
        for name in ("a1", "a2", "b1", "b2", "c1", "c2"):
            n = 15
            bank = np.zeros((n, len(BANK_COLUMNS)))
            bank[:, BANK_COLUMNS.index("GAMES")] = rng.integers(2, 5, size=n)
            for col in ("PTS", "REB", "TO"):
                bank[:, BANK_COLUMNS.index(col)] = rng.uniform(5, 40, size=n)
            raw_banks[name] = bank
            gp_factors[name] = float(rng.uniform(0.5, 1.0))

        banks = {}
        for name, bank in raw_banks.items():
            gp_factor = gp_factors[name]
            historical_pts = bank[:, BANK_COLUMNS.index("PTS")].sum() / bank[:, BANK_COLUMNS.index("GAMES")].sum()
            projected = {"PTS": historical_pts * gp_factor}
            scaled = scale_bank_to_projection(bank, projected, gp_factor=gp_factor)
            banks[name] = add_missed_weeks(scaled, gp_factor)

        rosters = {"A": ["a1", "a2"], "B": ["b1", "b2"], "C": ["c1", "c2"]}
        result = evaluate_trade(rosters, banks, "A", "B", [], [],
                                LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                                {**TRADE_CONFIG, "weeks_per_opponent": 500},
                                replacement_bank=np.zeros((1, len(BANK_COLUMNS))))
        for team in rosters:
            self.assertEqual(result["delta"][team]["expected"], 0.0)


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


def constant_bank(**stats) -> np.ndarray:
    """A one-row bank, so simulation results are exactly predictable."""
    bank = np.zeros((1, len(BANK_COLUMNS)))
    bank[0, BANK_COLUMNS.index("GAMES")] = 3.0
    for col, value in stats.items():
        bank[0, BANK_COLUMNS.index(col)] = value
    return bank


class SimulateTeamTotalsTests(unittest.TestCase):
    def test_sums_every_player_on_the_roster(self) -> None:
        roster = {"A": constant_bank(PTS=100.0), "B": constant_bank(PTS=50.0)}
        totals = simulate_team_totals(roster, n_weeks=10, seed=1)
        self.assertEqual(totals.shape, (10, len(BANK_COLUMNS)))
        self.assertTrue((totals[:, BANK_COLUMNS.index("PTS")] == 150.0).all())

    def test_a_player_draws_the_same_weeks_regardless_of_roster_order(self) -> None:
        bank = np.zeros((50, len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("PTS")] = np.arange(50)
        first = simulate_team_totals({"A": bank, "Z": constant_bank()}, 200, seed=3)
        second = simulate_team_totals({"Z": constant_bank(), "A": bank}, 200, seed=3)
        np.testing.assert_array_equal(first, second)


class CategoryWinRatesTests(unittest.TestCase):
    def _totals(self, n: int, **stats) -> np.ndarray:
        out = np.zeros((n, len(BANK_COLUMNS)))
        for col, value in stats.items():
            out[:, BANK_COLUMNS.index(col)] = value
        return out

    def test_higher_is_better_for_a_high_category(self) -> None:
        rates = category_win_rates(self._totals(10, PTS=100.0),
                                   self._totals(10, PTS=50.0),
                                   LEAGUE_CONFIG["categories"])
        self.assertEqual(rates["PTS"]["win"], 1.0)

    def test_lower_is_better_for_turnovers(self) -> None:
        rates = category_win_rates(self._totals(10, TO=5.0),
                                   self._totals(10, TO=20.0),
                                   LEAGUE_CONFIG["categories"])
        self.assertEqual(rates["TO"]["win"], 1.0)

    def test_equal_totals_are_ties_not_wins(self) -> None:
        rates = category_win_rates(self._totals(10, TD=0.0),
                                   self._totals(10, TD=0.0),
                                   LEAGUE_CONFIG["categories"])
        self.assertEqual(rates["TD"]["tie"], 1.0)
        self.assertEqual(rates["TD"]["win"], 0.0)

    def test_field_goal_pct_aggregates_makes_over_attempts(self) -> None:
        # A: 6/10 = .600. B: 5/6 = .833. Summing ratios naively would favour A.
        a = self._totals(5, FGM=6.0, FGA=10.0)
        b = self._totals(5, FGM=5.0, FGA=6.0)
        rates = category_win_rates(a, b, LEAGUE_CONFIG["categories"])
        self.assertEqual(rates["FG%"]["win"], 0.0)

    def test_zero_attempts_does_not_divide_by_zero(self) -> None:
        rates = category_win_rates(self._totals(5, FGM=0.0, FGA=0.0),
                                   self._totals(5, FGM=1.0, FGA=2.0),
                                   LEAGUE_CONFIG["categories"])
        self.assertEqual(rates["FG%"]["loss"], 1.0)


class ExpectedCategoriesWonTests(unittest.TestCase):
    def test_counts_a_tie_as_half_a_win(self) -> None:
        rates = {"PTS": {"win": 1.0, "tie": 0.0, "loss": 0.0},
                 "REB": {"win": 0.0, "tie": 1.0, "loss": 0.0},
                 "AST": {"win": 0.0, "tie": 0.0, "loss": 1.0}}
        self.assertAlmostEqual(expected_categories_won(rates), 1.5)


class EvaluateRosterVsFieldTests(unittest.TestCase):
    def _league(self) -> tuple[dict, dict]:
        rosters = {"Strong": ["S1"], "Middle": ["M1"], "Weak": ["W1"]}
        banks = {"S1": constant_bank(PTS=300.0, FGM=100.0, FGA=150.0),
                 "M1": constant_bank(PTS=200.0, FGM=70.0, FGA=150.0),
                 "W1": constant_bank(PTS=100.0, FGM=40.0, FGA=150.0)}
        return rosters, banks

    def test_the_best_roster_wins_a_category_against_the_whole_field(self) -> None:
        rosters, banks = self._league()
        _, rates = evaluate_roster_vs_field("Strong", rosters, banks,
                                            LEAGUE_CONFIG["categories"],
                                            n_weeks=50, seed=1)
        self.assertEqual(rates["PTS"]["win"], 1.0)

    def test_the_middle_roster_splits_the_field(self) -> None:
        rosters, banks = self._league()
        _, rates = evaluate_roster_vs_field("Middle", rosters, banks,
                                            LEAGUE_CONFIG["categories"],
                                            n_weeks=50, seed=1)
        self.assertAlmostEqual(rates["PTS"]["win"], 0.5)

    def test_expected_categories_won_averages_to_half_the_field(self) -> None:
        # Across every team, average expected categories won must be half of
        # the category count -- one team's win is another's loss.
        rosters, banks = self._league()
        n_cats = len(LEAGUE_CONFIG["categories"])
        scores = [evaluate_roster_vs_field(t, rosters, banks,
                                           LEAGUE_CONFIG["categories"],
                                           n_weeks=50, seed=1)[0]
                  for t in rosters]
        self.assertAlmostEqual(sum(scores) / len(scores), n_cats / 2, delta=0.01)

    def test_raises_when_the_team_is_not_in_the_league(self) -> None:
        rosters, banks = self._league()
        with self.assertRaises(KeyError):
            evaluate_roster_vs_field("Ghost", rosters, banks,
                                     LEAGUE_CONFIG["categories"], 10, 1)


class ApplyTradeTests(unittest.TestCase):
    def test_swaps_the_named_players_between_the_two_rosters(self) -> None:
        rosters = {"A": ["a1", "a2"], "B": ["b1", "b2"]}
        result = apply_trade(rosters, "A", "B", ["a1"], ["b1"])
        self.assertEqual(sorted(result["A"]), ["a2", "b1"])
        self.assertEqual(sorted(result["B"]), ["a1", "b2"])

    def test_leaves_uninvolved_rosters_alone(self) -> None:
        rosters = {"A": ["a1"], "B": ["b1"], "C": ["c1"]}
        self.assertEqual(apply_trade(rosters, "A", "B", ["a1"], ["b1"])["C"], ["c1"])

    def test_rejects_giving_a_player_you_do_not_have(self) -> None:
        rosters = {"A": ["a1"], "B": ["b1"]}
        with self.assertRaises(ValueError) as ctx:
            apply_trade(rosters, "A", "B", ["b1"], ["b1"])
        self.assertIn("b1", str(ctx.exception))

    def test_rejects_receiving_a_player_the_partner_does_not_have(self) -> None:
        rosters = {"A": ["a1"], "B": ["b1"]}
        with self.assertRaises(ValueError):
            apply_trade(rosters, "A", "B", ["a1"], ["a1"])

    def test_does_not_mutate_the_input(self) -> None:
        rosters = {"A": ["a1"], "B": ["b1"]}
        apply_trade(rosters, "A", "B", ["a1"], ["b1"])
        self.assertEqual(rosters["A"], ["a1"])


class EvaluateTradeTests(unittest.TestCase):
    def _league(self) -> tuple[dict, dict]:
        rosters = {"A": ["a1", "a2"], "B": ["b1", "b2"], "C": ["c1", "c2"]}
        banks = {"a1": constant_bank(PTS=200.0, REB=10.0),
                 "a2": constant_bank(PTS=100.0, REB=90.0),
                 "b1": constant_bank(PTS=190.0, REB=20.0),
                 "b2": constant_bank(PTS=110.0, REB=80.0),
                 "c1": constant_bank(PTS=150.0, REB=50.0),
                 "c2": constant_bank(PTS=150.0, REB=50.0)}
        return rosters, banks

    def _run(self, rosters, banks, give, get):
        return evaluate_trade(rosters, banks, "A", "B", give, get,
                              LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                              {**TRADE_CONFIG, "weeks_per_opponent": 500},
                              replacement_bank=constant_bank(PTS=1.0, REB=1.0))

    def test_a_null_trade_moves_nothing_at_all(self) -> None:
        # The strongest test in the suite. Catches seed leakage, broken common
        # random numbers, and padding that fires when it should not.
        rosters, banks = self._league()
        result = self._run(rosters, banks, [], [])
        for team in rosters:
            self.assertEqual(result["delta"][team]["expected"], 0.0)

    def test_a_trade_is_zero_sum_between_the_two_sides_on_a_symmetric_swap(self) -> None:
        rosters, banks = self._league()
        result = self._run(rosters, banks, ["a1"], ["b1"])
        self.assertAlmostEqual(result["delta"]["A"]["expected"],
                               -result["delta"]["B"]["expected"], delta=0.35)

    def test_reports_before_after_and_delta_for_every_team(self) -> None:
        rosters, banks = self._league()
        result = self._run(rosters, banks, ["a1"], ["b1"])
        for section in ("before", "after", "delta"):
            self.assertEqual(sorted(result[section]), ["A", "B", "C"])

    def test_an_uneven_trade_leaves_the_roster_short_before_padding(self) -> None:
        # roster_sizes_after reports the traded rosters, before padding.
        rosters, banks = self._league()
        result = self._run(rosters, banks, ["a1", "a2"], ["b1"])
        self.assertEqual(result["roster_sizes_after"]["A"], 1)

    def test_is_deterministic_across_repeated_runs(self) -> None:
        rosters, banks = self._league()
        first = self._run(rosters, banks, ["a1"], ["b1"])
        second = self._run(rosters, banks, ["a1"], ["b1"])
        self.assertEqual(first["delta"]["A"]["expected"],
                         second["delta"]["A"]["expected"])


class PadToRosterSizeTests(unittest.TestCase):
    def test_fills_a_short_roster_up_to_the_league_size(self) -> None:
        rosters, banks = pad_to_roster_size(
            {"A": ["a1"]}, {"a1": constant_bank(PTS=10.0)}, 3,
            replacement_bank=constant_bank(PTS=1.0))
        self.assertEqual(len(rosters["A"]), 3)
        self.assertEqual(len(banks), 3)

    def test_leaves_a_full_roster_untouched(self) -> None:
        rosters, _ = pad_to_roster_size(
            {"A": ["a1", "a2"]},
            {"a1": constant_bank(), "a2": constant_bank()}, 2,
            replacement_bank=constant_bank())
        self.assertEqual(rosters["A"], ["a1", "a2"])

    def test_replacement_slot_names_are_stable_across_calls(self) -> None:
        args = ({"A": ["a1"]}, {"a1": constant_bank()}, 3, constant_bank())
        self.assertEqual(pad_to_roster_size(*args)[0], pad_to_roster_size(*args)[0])

    def test_does_not_mutate_the_input_roster(self) -> None:
        rosters = {"A": ["a1"]}
        pad_to_roster_size(rosters, {"a1": constant_bank()}, 3, constant_bank())
        self.assertEqual(rosters["A"], ["a1"])


class TrimToRosterSizeTests(unittest.TestCase):
    def test_drops_the_correct_number_of_lowest_valued_players(self) -> None:
        rosters = {"A": ["a1", "a2", "a3", "a4"]}
        banks = {p: constant_bank() for p in rosters["A"]}
        values = {"a1": 0.9, "a2": 0.1, "a3": 0.5, "a4": 0.7}
        trimmed_rosters, _ = trim_to_roster_size(rosters, banks, 2, values)
        self.assertEqual(len(trimmed_rosters["A"]), 2)
        self.assertEqual(sorted(trimmed_rosters["A"]), ["a1", "a4"])

    def test_leaves_an_at_or_under_size_roster_untouched(self) -> None:
        rosters = {"A": ["a1", "a2"]}
        banks = {p: constant_bank() for p in rosters["A"]}
        values = {"a1": 0.9, "a2": 0.1}
        trimmed_rosters, _ = trim_to_roster_size(rosters, banks, 3, values)
        self.assertEqual(trimmed_rosters["A"], ["a1", "a2"])

    def test_does_not_mutate_inputs(self) -> None:
        rosters = {"A": ["a1", "a2", "a3"]}
        banks = {p: constant_bank() for p in rosters["A"]}
        original_roster = list(rosters["A"])
        original_banks = dict(banks)
        trim_to_roster_size(rosters, banks, 1, {"a1": 0.9, "a2": 0.1, "a3": 0.5})
        self.assertEqual(rosters["A"], original_roster)
        self.assertEqual(banks, original_banks)

    def test_players_missing_from_player_values_are_dropped_before_ranked_players(self) -> None:
        # "b" has no entry in player_values at all -- it should be dropped
        # before "a2", even though a2 is the lowest RANKED player.
        rosters = {"A": ["a1", "a2", "b"]}
        banks = {p: constant_bank() for p in rosters["A"]}
        values = {"a1": 0.9, "a2": 0.1}
        trimmed_rosters, _ = trim_to_roster_size(rosters, banks, 2, values)
        self.assertEqual(sorted(trimmed_rosters["A"]), ["a1", "a2"])


class EvenTradeZeroSumLeakTests(unittest.TestCase):
    """
    Proves Fix 3 with hand-verified, deterministic arithmetic (single-row
    constant banks: no Monte Carlo noise, so every number below is exact,
    not estimated).

    League: A, B, C, D, roster_size=2. Every player's PTS is the only
    informative category -- every other category is 0 for every player,
    which makes every other category a permanent, roster-size-independent
    0-0 tie (0 * N players = 0), isolating the roster-size effect to PTS
    alone so the arithmetic below is checkable by hand.

      A = [a1(100), a2(100)]   B = [b1(100), b2(20)]
      C = [c1(100), c2(100)]   D = [d1(100), d2(100)]  (untouched field)

    Trade: A gives [a1, a2] (both 100) to B, gets [b1] (100) back --
    a 2-for-1. Replacement level is also PTS=100, so A's post-trade pad
    ([b1(100)] + one replacement(100)) always totals 200, whichever run.
    A is never trimmed (it is short, not over), but A's OWN delta still
    depends on the run: A's opponents include B, so B's post-trim size
    changes what A faces in the field, not just what B itself faces.

    Untrimmed, B keeps all 3 players ([b2(20), a1(100), a2(100)] = 220,
    an illegal roster) and beats every legal 200-PTS opponent (A/C/D)
    outright. Trimmed, B drops its lowest-value player (b2, PTS=20) back
    to a legal 2-player, 200-PTS roster and only ties them. Hand-computed
    (and confirmed against the real evaluate_trade output):

      PTS contribution to expected categories won (win + 0.5*tie, averaged
      over the 3 opponents each side faces):
        B before:                       0/3 win           -> 0.0
        B after, untrimmed (vs 200s):   3/3 win            -> 1.0   (delta +1.0)
        B after, trimmed (vs 200s):     3/3 tie            -> 0.5   (delta +0.5)
        A before (vs B=120,C=200,D=200): 1/3 win, 2/3 tie  -> 0.667
        A after, untrimmed (vs B=220):   0/3 win, 2/3 tie  -> 0.333 (delta -0.333)
        A after, trimmed (vs B=200):     0/3 win, 3/3 tie  -> 0.5   (delta -0.167)

      leak = delta_A + delta_B:
        untrimmed: -0.333 + 1.0 = +0.667
        trimmed:   -0.167 + 0.5 = +0.333

    All other categories are ties before AND after in both runs, so they
    contribute exactly 0 to every delta -- the PTS-only arithmetic above
    *is* the whole-category leak, not an approximation of it.
    """

    def _bank(self, pts: float) -> np.ndarray:
        bank = np.zeros((1, len(BANK_COLUMNS)))
        bank[0, BANK_COLUMNS.index("PTS")] = pts
        bank[0, BANK_COLUMNS.index("GAMES")] = 3.0
        return bank

    def _league(self):
        rosters = {"A": ["a1", "a2"], "B": ["b1", "b2"],
                  "C": ["c1", "c2"], "D": ["d1", "d2"]}
        banks = {"a1": self._bank(100), "a2": self._bank(100),
                 "b1": self._bank(100), "b2": self._bank(20),
                 "c1": self._bank(100), "c2": self._bank(100),
                 "d1": self._bank(100), "d2": self._bank(100)}
        return rosters, banks

    def test_an_uneven_trade_leaves_both_sides_at_the_legal_roster_size(self) -> None:
        rosters, banks = self._league()
        replacement = self._bank(100)
        player_values = {"a1": 0.9, "a2": 0.9, "b1": 0.9, "b2": 0.1}
        config = {**LEAGUE_CONFIG, "roster_size": 2}
        trade_config = {**TRADE_CONFIG, "weeks_per_opponent": 5}

        result = evaluate_trade(rosters, banks, "A", "B", ["a1", "a2"], ["b1"],
                                LEAGUE_CONFIG["categories"], config, trade_config,
                                replacement, player_values=player_values)

        # roster_sizes_after reports the raw post-trade sizes, before either
        # padding or trimming -- confirms the trade really is uneven here
        # (A short by one, B over by one), independent of trimming.
        self.assertEqual(result["roster_sizes_after"], {"A": 1, "B": 3, "C": 2, "D": 2})

    def test_zero_sum_leak_shrinks_sharply_once_trimmed(self) -> None:
        # Constructed so it would fail against the old, pad-only behaviour:
        # hand-verified above, the leak must roughly HALVE, not just nudge,
        # once B's illegal third player is trimmed away.
        rosters, banks = self._league()
        replacement = self._bank(100)
        player_values = {"a1": 0.9, "a2": 0.9, "b1": 0.9, "b2": 0.1}
        config = {**LEAGUE_CONFIG, "roster_size": 2}
        trade_config = {**TRADE_CONFIG, "weeks_per_opponent": 5}

        untrimmed = evaluate_trade(rosters, banks, "A", "B", ["a1", "a2"], ["b1"],
                                   LEAGUE_CONFIG["categories"], config, trade_config,
                                   replacement)
        trimmed = evaluate_trade(rosters, banks, "A", "B", ["a1", "a2"], ["b1"],
                                 LEAGUE_CONFIG["categories"], config, trade_config,
                                 replacement, player_values=player_values)

        # Hand-computed above: -1/3 and +1.0.
        self.assertAlmostEqual(untrimmed["delta"]["A"]["expected"], -1 / 3, places=6)
        self.assertAlmostEqual(untrimmed["delta"]["B"]["expected"], 1.0, places=6)
        # Hand-computed above: -1/6 and +0.5.
        self.assertAlmostEqual(trimmed["delta"]["A"]["expected"], -1 / 6, places=6)
        self.assertAlmostEqual(trimmed["delta"]["B"]["expected"], 0.5, places=6)

        untrimmed_leak = abs(untrimmed["delta"]["A"]["expected"]
                             + untrimmed["delta"]["B"]["expected"])
        trimmed_leak = abs(trimmed["delta"]["A"]["expected"]
                           + trimmed["delta"]["B"]["expected"])

        self.assertAlmostEqual(untrimmed_leak, 2 / 3, places=6)
        self.assertAlmostEqual(trimmed_leak, 1 / 3, places=6)
        self.assertLess(trimmed_leak, untrimmed_leak * 0.6)


class FullLeagueIntegrationTests(unittest.TestCase):
    """A synthetic 10-team, 13-player league exercised end to end."""

    def _league(self, seed: int = 99) -> tuple[dict, dict]:
        rng = np.random.default_rng(seed)
        rosters, banks = {}, {}
        for t in range(10):
            team = f"Team{t}"
            rosters[team] = []
            for p in range(13):
                name = f"P{t}_{p}"
                bank = np.zeros((30, len(BANK_COLUMNS)))
                bank[:, BANK_COLUMNS.index("GAMES")] = rng.integers(2, 5, size=30)
                for col in ("FGM", "FGA", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF"):
                    bank[:, BANK_COLUMNS.index(col)] = rng.uniform(0, 60, size=30)
                rosters[team].append(name)
                banks[name] = bank

        # Deterministic best/worst players, injected on top of the random
        # roster. TO and PF are low-is-better categories, so a randomly
        # generated player with the highest PTS can simultaneously carry
        # the worst TO/PF and be a net-negative trade asset -- "highest
        # PTS" alone does not reliably identify "best player" (29/100 seeds
        # flipped the trade-direction assertion when selection was done
        # that way; see task-10 fix report). "Star"/"Scrub" dominate or
        # trail every category, including the low-is-better ones, so the
        # trade's direction is true by construction, not by luck of the
        # seed.
        star_bank = np.zeros((30, len(BANK_COLUMNS)))
        star_bank[:, BANK_COLUMNS.index("GAMES")] = rng.integers(2, 5, size=30)
        for col, val in (("FGM", 60), ("FGA", 100), ("PTS", 200), ("REB", 60),
                         ("AST", 60), ("ST", 20), ("BLK", 20), ("TO", 2), ("PF", 2)):
            star_bank[:, BANK_COLUMNS.index(col)] = val
        scrub_bank = np.zeros((30, len(BANK_COLUMNS)))
        scrub_bank[:, BANK_COLUMNS.index("GAMES")] = rng.integers(2, 5, size=30)
        for col, val in (("FGM", 10), ("FGA", 100), ("PTS", 20), ("REB", 5),
                         ("AST", 5), ("ST", 1), ("BLK", 1), ("TO", 40), ("PF", 40)):
            scrub_bank[:, BANK_COLUMNS.index(col)] = val

        rosters["Team0"][0] = "Star"
        banks["Star"] = star_bank
        rosters["Team1"][0] = "Scrub"
        banks["Scrub"] = scrub_bank
        return rosters, banks

    def _run(self, rosters, banks, give, get):
        return evaluate_trade(rosters, banks, "Team0", "Team1", give, get,
                              LEAGUE_CONFIG["categories"], LEAGUE_CONFIG,
                              {**TRADE_CONFIG, "weeks_per_opponent": 1_000},
                              replacement_bank=np.zeros((1, len(BANK_COLUMNS))))

    def test_the_field_averages_to_half_the_categories(self) -> None:
        rosters, banks = self._league()
        result = self._run(rosters, banks, [], [])
        scores = [v["expected"] for v in result["before"].values()]
        n_cats = len(LEAGUE_CONFIG["categories"])
        self.assertAlmostEqual(sum(scores) / len(scores), n_cats / 2, delta=0.05)

    def test_a_null_trade_across_a_full_league_is_exactly_zero(self) -> None:
        rosters, banks = self._league()
        result = self._run(rosters, banks, [], [])
        self.assertTrue(all(v["expected"] == 0.0 for v in result["delta"].values()))

    def test_trading_your_best_player_for_their_worst_hurts_you(self) -> None:
        # Trade the deliberately dominant/terrible pair by name -- domination
        # is by construction (see _league), not inferred from a single
        # random column, so the direction of the delta is guaranteed rather
        # than seed-dependent.
        rosters, banks = self._league()
        result = self._run(rosters, banks, ["Star"], ["Scrub"])
        self.assertLess(result["delta"]["Team0"]["expected"], 0.0)
        self.assertGreater(result["delta"]["Team1"]["expected"], 0.0)

    def test_untraded_teams_barely_move(self) -> None:
        # Not exactly zero: a one-for-one trade genuinely changes the field
        # every other team is measured against. But it should be small.
        rosters, banks = self._league()
        best = max(rosters["Team0"], key=lambda p: banks[p][:, BANK_COLUMNS.index("PTS")].sum())
        worst = min(rosters["Team1"], key=lambda p: banks[p][:, BANK_COLUMNS.index("PTS")].sum())
        result = self._run(rosters, banks, [best], [worst])
        for team in rosters:
            if team not in ("Team0", "Team1"):
                self.assertLess(abs(result["delta"][team]["expected"]), 0.35)


class QuantizeBankCountsTests(unittest.TestCase):
    """
    Rescaling turns integer weekly counts into floats, and two continuous team
    totals are essentially never equal -- which silently removed ties from
    every category. Ties are not wins, and the sparse categories are exactly
    where both teams realistically finish level.
    """

    def _bank(self, **stats) -> np.ndarray:
        n = 400
        bank = np.zeros((n, len(BANK_COLUMNS)))
        bank[:, BANK_COLUMNS.index("GAMES")] = 3.0
        for col, val in stats.items():
            bank[:, BANK_COLUMNS.index(col)] = val
        return bank

    def test_every_count_column_becomes_a_whole_number(self) -> None:
        out = quantize_bank_counts(self._bank(PTS=17.4, DD=0.6, TECH=0.04), "P", 1)
        for col in BANK_COLUMNS:
            if col == "GAMES":
                continue
            values = out[:, BANK_COLUMNS.index(col)]
            self.assertTrue(np.all(values == np.round(values)), f"{col} not integral")

    def test_games_column_is_left_alone(self) -> None:
        out = quantize_bank_counts(self._bank(PTS=10.5), "P", 1)
        self.assertTrue(np.all(out[:, BANK_COLUMNS.index("GAMES")] == 3.0))

    def test_rounding_is_stochastic_so_the_mean_survives(self) -> None:
        # Plain rounding would drive a 0.6-per-week rate to 1.0 (or to 0.0),
        # biasing every sparse category. Stochastic rounding keeps the mean.
        out = quantize_bank_counts(self._bank(DD=0.6), "P", 1)
        self.assertAlmostEqual(out[:, BANK_COLUMNS.index("DD")].mean(), 0.6, delta=0.06)

    def test_a_low_rate_produces_a_mix_of_zeros_and_ones(self) -> None:
        out = quantize_bank_counts(self._bank(TECH=0.3), "P", 1)
        seen = set(out[:, BANK_COLUMNS.index("TECH")].tolist())
        self.assertEqual(seen, {0.0, 1.0})

    def test_an_exact_integer_is_unchanged(self) -> None:
        out = quantize_bank_counts(self._bank(PTS=12.0), "P", 1)
        self.assertTrue(np.all(out[:, BANK_COLUMNS.index("PTS")] == 12.0))

    def test_a_zero_column_stays_zero(self) -> None:
        out = quantize_bank_counts(self._bank(PTS=10.0), "P", 1)
        self.assertTrue(np.all(out[:, BANK_COLUMNS.index("TD")] == 0.0))

    def test_is_deterministic_for_a_player_and_seed(self) -> None:
        bank = self._bank(PTS=17.4, DD=0.6)
        np.testing.assert_array_equal(quantize_bank_counts(bank, "P", 1),
                                      quantize_bank_counts(bank, "P", 1))

    def test_different_players_round_differently(self) -> None:
        bank = self._bank(DD=0.5)
        self.assertFalse(np.array_equal(quantize_bank_counts(bank, "A", 1),
                                        quantize_bank_counts(bank, "B", 1)))

    def test_does_not_mutate_the_input(self) -> None:
        bank = self._bank(PTS=17.4)
        quantize_bank_counts(bank, "P", 1)
        self.assertEqual(bank[0, BANK_COLUMNS.index("PTS")], 17.4)


class PooledDonorBankTests(unittest.TestCase):
    """A player with no game log borrows the shape of real weeks."""

    def _pool(self) -> dict[str, np.ndarray]:
        banks = {}
        for i, name in enumerate(("A", "B")):
            bank = np.zeros((20, len(BANK_COLUMNS)))
            bank[:, BANK_COLUMNS.index("GAMES")] = 3.0
            # PTS and FGM move together, as they do in real weeks.
            pts = np.linspace(10, 40, 20) + i
            bank[:, BANK_COLUMNS.index("PTS")] = pts
            bank[:, BANK_COLUMNS.index("FGM")] = pts / 2.0
            banks[name] = bank
        return banks

    def test_returns_the_requested_number_of_rows(self) -> None:
        out = pooled_donor_bank(self._pool(), "Rookie", seed=1, n_rows=50)
        self.assertEqual(out.shape, (50, len(BANK_COLUMNS)))

    def test_rows_are_real_observed_weeks_not_synthesised(self) -> None:
        pool = self._pool()
        real_rows = {tuple(r) for b in pool.values() for r in b}
        out = pooled_donor_bank(pool, "Rookie", seed=1, n_rows=50)
        self.assertTrue(all(tuple(r) in real_rows for r in out))

    def test_preserves_cross_category_correlation(self) -> None:
        # The whole reason for borrowing real weeks: independent draws would
        # give ~0 here, losing the structure the bootstrap exists to keep.
        out = pooled_donor_bank(self._pool(), "Rookie", seed=1, n_rows=200)
        corr = np.corrcoef(out[:, BANK_COLUMNS.index("PTS")],
                           out[:, BANK_COLUMNS.index("FGM")])[0, 1]
        self.assertGreater(corr, 0.9)

    def test_returns_none_when_there_is_nothing_to_borrow(self) -> None:
        self.assertIsNone(pooled_donor_bank({}, "Rookie", seed=1))

    def test_is_deterministic(self) -> None:
        pool = self._pool()
        np.testing.assert_array_equal(pooled_donor_bank(pool, "R", 1, 30),
                                      pooled_donor_bank(pool, "R", 1, 30))


class TechIsNotAFoulProxyTests(unittest.TestCase):
    """
    TECH proxied as PF * 0.012 makes it a fixed multiple of fouls, so at team
    level the two categories correlate at ~0.9999 and win or lose together --
    letting fouls quietly decide 2 of the league's 14 categories.
    """

    def test_a_supplied_rate_is_used_instead_of_the_foul_proxy(self) -> None:
        logs = {"2025-26": {"P": make_log(["2026-01-05", "2026-01-07"],
                                          PF=[5, 5], PTS=[10, 10])}}
        bank = build_week_bank(logs, tech_rates={"P": 0.25})["P"]
        # 2 games that week at 0.25/game = 0.5, not 10 fouls * 0.012 = 0.12
        self.assertAlmostEqual(bank[0, BANK_COLUMNS.index("TECH")], 0.5)

    def test_falls_back_to_the_foul_proxy_when_no_rate_is_known(self) -> None:
        logs = {"2025-26": {"P": make_log(["2026-01-05"], PF=[5])}}
        bank = build_week_bank(logs)["P"]
        self.assertAlmostEqual(bank[0, BANK_COLUMNS.index("TECH")], 5 * 0.012)

    def test_tech_no_longer_tracks_fouls_when_real_rates_differ(self) -> None:
        # Two players with identical fouls but different technical rates must
        # produce different TECH -- impossible under the proxy.
        logs = {"2025-26": {"A": make_log(["2026-01-05"], PF=[4]),
                            "B": make_log(["2026-01-05"], PF=[4])}}
        banks = build_week_bank(logs, tech_rates={"A": 0.5, "B": 0.01})
        self.assertNotAlmostEqual(banks["A"][0, BANK_COLUMNS.index("TECH")],
                                  banks["B"][0, BANK_COLUMNS.index("TECH")])
