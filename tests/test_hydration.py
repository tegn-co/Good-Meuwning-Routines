import unittest
from datetime import datetime, timedelta

from tests import env  # noqa: F401
import hydration

NOON = datetime(2026, 10, 22, 12, 0)


class HydrationTest(unittest.TestCase):
    def test_thirsty_after_the_interval(self):
        hour_ago = NOON - timedelta(minutes=60)
        self.assertTrue(hydration.is_thirsty(NOON, hour_ago, 60, 2, 8))
        self.assertFalse(hydration.is_thirsty(NOON, hour_ago + timedelta(minutes=1), 60, 2, 8))
        self.assertFalse(hydration.is_thirsty(NOON, hour_ago, 0, 2, 8))  # reminder off
        self.assertFalse(hydration.is_thirsty(NOON, hour_ago, 60, 8, 8))  # goal reached

    def test_litres(self):
        self.assertEqual(hydration.litres(3, 250), "0.75 L")
        self.assertEqual(hydration.litres(8, 250), "2 L")
        self.assertEqual(hydration.litres(0, 300), "0 L")


if __name__ == "__main__":
    unittest.main()
