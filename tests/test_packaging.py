"""Every module of the app must be shipped in every package (a missing file only shows up at start-up)."""
import re
import unittest

from tests import env

MODULES = sorted(p.name for p in env.ROOT.glob("*.py"))


class PackagingTest(unittest.TestCase):
    def test_deb_ships_every_module(self):
        files = re.search(r"for f in (.*?); do", (env.ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8"))
        self.assertEqual(sorted(files.group(1).split()), MODULES)

    def test_flatpak_ships_every_module(self):
        manifest = (env.ROOT / "packaging" / "flatpak" / "no.zivid.MorgenTodo.yml").read_text(encoding="utf-8")
        line = re.search(r"install -Dm644 -t /app/share/morgen-todo (.*)", manifest)
        self.assertEqual(sorted(line.group(1).split()), MODULES)

    def test_windows_ships_every_module(self):
        spec = (env.ROOT / "packaging" / "windows" / "morning-routine.spec").read_text(encoding="utf-8")
        listed = re.search(r"modules = \[(.*?)\]", spec, re.S).group(1)
        names = sorted(n + ".py" for n in re.findall(r'"(\w+)"', listed))
        self.assertEqual(names, sorted(m for m in MODULES if m != "app.py"))


if __name__ == "__main__":
    unittest.main()
