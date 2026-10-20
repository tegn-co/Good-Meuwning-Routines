import unittest

from tests import env  # noqa: F401
import updater


class UpdatesTest(unittest.TestCase):
    def test_version_compare(self):
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("1.9.3"))
        self.assertEqual(updater.parse_version("v1.1.1"), (1, 1, 1))

    def test_newer_available(self):
        orig_inst, orig_latest = updater.installed_version, updater.latest_version
        try:
            updater.installed_version = lambda: "1.1.1"
            updater.latest_version = lambda: "1.2.0"
            self.assertEqual(updater.check_for_newer_version(), ("1.1.1", "1.2.0"))
            updater.latest_version = lambda: "1.1.1"
            self.assertIsNone(updater.check_for_newer_version())
            updater.installed_version = lambda: None  # from source: never check
            self.assertIsNone(updater.check_for_newer_version())
        finally:
            updater.installed_version, updater.latest_version = orig_inst, orig_latest


if __name__ == "__main__":
    unittest.main()
