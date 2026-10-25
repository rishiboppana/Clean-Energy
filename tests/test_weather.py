import unittest

from pipeline.weather import normalize


class NormalizeTest(unittest.TestCase):
    def test_maps_columns_and_skips_empty_hours(self):
        h = {"time": ["2026-10-24T16:00", "2026-10-24T17:00"], "ghi": [500.0, None], "dni": [700.0, None], "cloud": [10, None],
             "temp": [30.0, None], "wind100": [4.0, None], "wdir100": [180, None]}
        got = normalize("SRP", "phoenix", "previous_day1", h)
        self.assertEqual(got, [("SRP", "phoenix", "previous_day1", "2026-10-24T16:00:00+00", 500.0, 700.0, 10, 30.0, 4.0, 180)])


if __name__ == "__main__":
    unittest.main()
