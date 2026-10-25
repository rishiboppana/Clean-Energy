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


if __name__ == "__main__":
    unittest.main()
