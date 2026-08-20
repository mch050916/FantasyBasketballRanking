import unittest

import numpy as np
import pandas as pd

from config import LEAGUE_CONFIG, TRADE_CONFIG
from trade import BANK_COLUMNS, apply_trade, build_week_bank, category_win_rates, evaluate_roster_vs_field, evaluate_trade, expected_categories_won, games_per_week_pool, pad_to_roster_size, player_rng, scale_bank_to_projection, simulate_team_totals, synthesize_bank


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
