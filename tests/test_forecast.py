import unittest

import numpy as np
import pandas as pd

from forecast.features import sun_elevation
from forecast.train import fit_widening, widen


class SunTest(unittest.TestCase):
    def test_equinox_equator_noon_is_overhead_midnight_is_dark(self):
        e = sun_elevation(["2026-03-20T12:00", "2026-03-20T00:00"], 0.0, 0.0)
        self.assertGreater(e[0], 80)
        self.assertLess(e[1], -80)


class WideningTest(unittest.TestCase):
    def test_widened_band_covers_80_percent_of_fit_data(self):
        rng = np.random.default_rng(0)
        y = rng.normal(0.5, 0.2, 5000)
        df = pd.DataFrame({"label": y, "lead_bucket": rng.integers(0, 3, len(y)), "elev": 1.0})
        p = np.tile([0.45, 0.5, 0.55], (len(y), 1))  # deliberately too narrow
        k = fit_widening(p, df, "SUN")
        w = widen(p, df, k)
        self.assertAlmostEqual(((y >= w[:, 0]) & (y <= w[:, 2])).mean(), 0.8, delta=0.02)


class SplitTest(unittest.TestCase):
    def test_every_season_in_every_set_and_boundaries_buffered(self):
        from forecast.split import SEASON, seasonal_block_split
        issue = pd.date_range("2024-12-25", "2026-10-24", freq="6H")
        sp = seasonal_block_split(issue)
        season = pd.Series(issue.month).map(lambda m: SEASON.get(m, 3)).values
        for name in ("train", "val", "test"):
            self.assertEqual(set(season[sp == name]), {0, 1, 2, 3})
        kept = pd.Series(sp)
        for i in range(1, len(sp)):  # no train row sits next to a test row without the dropped buffer between
            if sp[i] is not None and sp[i - 1] is not None and sp[i] != sp[i - 1]:
                self.fail("adjacent rows in different sets: buffer missing")


class LeakageTest(unittest.TestCase):
    def test_features_ignore_actuals_newer_than_issue_minus_lag(self):
        from forecast import features as F
        idx = pd.date_range("2025-01-01", periods=24 * 120, freq="H")
        rng = np.random.default_rng(1)
        y = pd.Series(rng.uniform(0, 100, len(idx)), index=idx)
        names = [f"{c}_{s}" for c in F.WX for s in ("m", "s")]
        wx = {p: pd.DataFrame(rng.uniform(0, 1, (len(idx) + 100, len(names))), columns=names,
                              index=pd.date_range("2025-01-01", periods=len(idx) + 100, freq="H")) for p in F.PRODUCT_BY_BUCKET}
        T = pd.DatetimeIndex(["2025-04-10 06:00"])
        lag = 36
        a = F.rows(F.series_context(y), wx, names, T, 33.0, -112.0, lag)
        y2 = y.copy()
        y2[y2.index > T[0] - pd.Timedelta(hours=lag)] = 999.0  # rewrite everything the model must not see
        b = F.rows(F.series_context(y2), wx, names, T, 33.0, -112.0, lag)
        cols = ["last_share", "same_share", "mean24_share", "cap"]
        pd.testing.assert_frame_equal(a[cols], b[cols])


if __name__ == "__main__":
    unittest.main()
