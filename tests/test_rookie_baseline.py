import unittest

from rookie_baseline import get_rookie_baseline


class RookieBaselineTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "GP", "MIN", "PTS", "REB", "AST", "ST", "BLK", "TO", "PF",
        "FGM", "FGA", "FG%", "3PTM", "FTM", "DD", "TD", "TECH",
    }

    def test_bucket_boundaries_resolve_to_the_correct_bucket(self) -> None:
        # Top-5 bucket
        self.assertAlmostEqual(get_rookie_baseline(1)["PTS"], 13.547, places=3)
        self.assertAlmostEqual(get_rookie_baseline(5)["PTS"], 13.547, places=3)
        # 6-14 bucket
        self.assertAlmostEqual(get_rookie_baseline(6)["PTS"], 7.235, places=3)
        self.assertAlmostEqual(get_rookie_baseline(14)["PTS"], 7.235, places=3)
        # 15-30 bucket
        self.assertAlmostEqual(get_rookie_baseline(15)["PTS"], 6.417, places=3)
        self.assertAlmostEqual(get_rookie_baseline(30)["PTS"], 6.417, places=3)
        # 31-60 bucket
        self.assertAlmostEqual(get_rookie_baseline(31)["PTS"], 3.992, places=3)
        self.assertAlmostEqual(get_rookie_baseline(60)["PTS"], 3.992, places=3)

    def test_out_of_range_picks_return_none(self) -> None:
        self.assertIsNone(get_rookie_baseline(0))
        self.assertIsNone(get_rookie_baseline(-1))
        self.assertIsNone(get_rookie_baseline(61))
        self.assertIsNone(get_rookie_baseline(100))

    def test_baseline_has_every_category_the_pipeline_needs(self) -> None:
        baseline = get_rookie_baseline(1)
        self.assertEqual(set(baseline.keys()), self.EXPECTED_KEYS)
        for key in self.EXPECTED_KEYS:
            self.assertIsInstance(baseline[key], float)

    def test_baseline_production_declines_monotonically_across_buckets(self) -> None:
        # Sanity check on the real computed data: earlier picks should
        # average more production than later picks, for the pipeline's
        # primary counting stats.
        top5 = get_rookie_baseline(1)
        lottery = get_rookie_baseline(10)
        round1 = get_rookie_baseline(20)
        round2 = get_rookie_baseline(45)
        for cat in ("PTS", "REB", "AST", "MIN", "GP"):
            self.assertGreater(top5[cat], lottery[cat])
            self.assertGreater(lottery[cat], round1[cat])
            self.assertGreater(round1[cat], round2[cat])

    def test_returned_dict_is_a_copy_not_a_shared_reference(self) -> None:
        first = get_rookie_baseline(1)
        first["PTS"] = -999.0
        second = get_rookie_baseline(1)
        self.assertAlmostEqual(second["PTS"], 13.547, places=3)
