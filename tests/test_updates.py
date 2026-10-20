import unittest

from tests import env  # noqa: F401
import updates


class UpdatesTest(unittest.TestCase):
    def test_version_compare(self):
        self.assertGreater(updates.parse("v1.10.0"), updates.parse("1.9.3"))
        self.assertEqual(updates.parse("v1.1.1"), (1, 1, 1))

    def test_newer_available(self):
        orig_inst, orig_latest = updates.installed_version, updates.latest_version
        try:
            updates.installed_version = lambda: "1.1.1"
            updates.latest_version = lambda: "1.2.0"
            self.assertEqual(updates.newer_available(), ("1.1.1", "1.2.0"))
            updates.latest_version = lambda: "1.1.1"
            self.assertIsNone(updates.newer_available())
            updates.installed_version = lambda: None  # fra kildekoden: aldri sjekk
            self.assertIsNone(updates.newer_available())
        finally:
            updates.installed_version, updates.latest_version = orig_inst, orig_latest


if __name__ == "__main__":
    unittest.main()
