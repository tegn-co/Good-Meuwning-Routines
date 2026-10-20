import unittest

from tests import env  # noqa: F401
import weather

SAMPLE = {"current": {"temperature_2m": 7.5, "weather_code": 61, "is_day": 1},
          "daily": {"weather_code": [63], "temperature_2m_min": [3.2], "temperature_2m_max": [9.6],
                    "precipitation_probability_max": [80]}}


class WeatherTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(weather.parse(SAMPLE), {"temp": 8, "kind": "rain", "day_kind": "rain",
                                                 "min": 3, "max": 10, "rain": 80})

    def test_kinds(self):
        self.assertEqual(weather.kind(0), "clear")
        self.assertEqual(weather.kind(0, is_day=False), "night")
        self.assertEqual(weather.kind(2), "partly")
        self.assertEqual(weather.kind(75), "snow")
        self.assertEqual(weather.kind(95), "thunder")
        self.assertEqual(weather.kind(12345), "cloudy")

    def test_remark(self):
        self.assertEqual(weather.remark(weather.parse(SAMPLE)), "take an umbrella! ☔")
        self.assertEqual(weather.remark({"day_kind": "clear", "max": 22, "rain": 0}), "nice day! ☀")
        self.assertIsNone(weather.remark({"day_kind": "cloudy", "max": 10, "rain": 10}))

    def test_icons_are_rectangular(self):
        for name, icon in weather.ICONS.items():
            self.assertEqual(len({len(r) for r in icon}), 1, name)
            self.assertTrue(set("".join(icon)) <= set(weather.COLORS) | {"."}, name)


if __name__ == "__main__":
    unittest.main()
