import unittest

from pipeline.eia import normalize


class NormalizeTest(unittest.TestCase):
    def test_maps_metrics_labels_quality_and_skips_junk(self):
        rows = [
            {"period": "2026-10-24T16", "type": "D", "value": "1000"},
            {"period": "2026-10-24T16", "type": "DF", "value": "1100"},
            {"period": "2026-10-24T16", "fueltype": "SUN", "value": "50.5"},
            {"period": "2026-10-24T16", "fueltype": "BAT", "value": "-3"},   # unmapped: skipped
            {"period": "2026-10-24T16", "fueltype": "WND", "value": None},   # null: skipped
        ]
        got = normalize("PJM", rows)
        self.assertEqual([(r[2], r[3], r[5]) for r in got],
                         [("demand_mw", 1000.0, "measured"), ("demand_forecast_mw", 1100.0, "estimate"), ("gen_solar_mw", 50.5, "measured")])
        self.assertEqual(got[0][1], "2026-10-24T16:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
