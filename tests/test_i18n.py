import ast
import json
import os
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import env
import translations

MODULES = ["app.py", "cat.py", "cat_panel.py", "pomodoro_panel.py", "tutorial.py"]


class I18nTest(unittest.TestCase):
    def test_no_function_shadows_the_translate_function(self):
        """A parameter or variable named _ in a function that calls _("…") causes a TypeError."""
        problems = []
        for f in MODULES:
            tree = ast.parse((env.ROOT / f).read_text())
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.Lambda)):
                    continue
                params = [a.arg for a in fn.args.args + fn.args.posonlyargs + fn.args.kwonlyargs]
                comp = {id(t) for c in ast.walk(fn) if isinstance(c, (ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.SetComp))
                        for g in c.generators for t in ast.walk(g.target)}
                stores = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "_"
                          and isinstance(n.ctx, ast.Store) and id(n) not in comp]
                calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"]
                if calls and ("_" in params or stores):
                    problems.append(f"{f}:{fn.lineno}")
        self.assertEqual(problems, [])

    def test_placeholders_match(self):
        fields = lambda s: sorted(f for _t, f, _s, _c in string.Formatter().parse(s) if f)
        bad = [en for en, nb in translations.NB.items() if fields(en) != fields(nb)]
        self.assertEqual(bad, [])

    def test_app_starts_in_norwegian(self):
        tmp = Path(tempfile.mkdtemp(prefix="morgen-todo-nb-"))
        (tmp / "config" / "morgen-todo").mkdir(parents=True)
        (tmp / "config" / "morgen-todo" / "config.json").write_text(json.dumps({"language": "nb", "onboarded": True}))
        (tmp / "data" / "fonts").mkdir(parents=True)
        script = """
import sys; sys.path.insert(0, %r)
import app as W
from gi.repository import GLib
app = W.App(); app.set_application_id("no.zivid.MorgenTodoNb")
def check():
    w = app.window
    print("TITLE", w.title_cat.title); print("ITEM", w.titles["email"].get_label()); print("HOURS", w.today_diff.get_label())
    from gi.repository import Gtk
    w.streak_lbl.set_label("12 dager på rad"); w.streak_lbl.set_visible(True)
    print("LISTWIDTH", w.scroll.get_child().measure(Gtk.Orientation.HORIZONTAL, -1)[0])
    widths = [w.side_stack.get_child_by_name(n).measure(Gtk.Orientation.HORIZONTAL, -1)[0] for n in ("plan", "pomo", "cat", "settings")]
    print("SIDEPAGES", max(widths), W.SIDE_W - 36)
    app.quit()
GLib.timeout_add(2500, lambda: check() and False)
app.run(["x"])
""" % str(env.ROOT)
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, XDG_CONFIG_HOME=str(tmp / "config"), XDG_DATA_HOME=str(tmp / "data")))
        self.assertIn("TITLE god morgen", out.stdout, out.stderr[-2000:])
        self.assertIn("ITEM Sjekk e-post", out.stdout)
        self.assertIn("forventet", out.stdout)
        self.assertNotIn("Traceback", out.stderr, out.stderr[-2000:])
        width = int(out.stdout.split("LISTWIDTH ")[1].split()[0])
        self.assertLessEqual(width, 360, "the Norwegian list is wider than the window")
        need, room = (int(v) for v in out.stdout.split("SIDEPAGES ")[1].split()[:2])
        self.assertLessEqual(need, room, "a Norwegian side page is wider than the panel")


if __name__ == "__main__":
    unittest.main()
