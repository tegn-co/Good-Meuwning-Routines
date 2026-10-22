"""Every symbol in the UI (⚙, ▸, ☀, 🍅 …) can be drawn with the fonts the app asks for.

Runs on Windows, where GTK does not look for missing symbols in other fonts by itself (Linux does).
"""
import io
import re
import tokenize
import unicodedata
import unittest
from pathlib import Path

from tests import env  # noqa: F401
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

import platforms  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UI_MODULES = ["app.py", "cat.py", "cat_panel.py", "pomodoro_panel.py", "tutorial.py", "translations.py", "weather.py"]


def ui_symbols():
    """Non-letter characters outside ASCII in the string literals of the UI modules."""
    found = set()
    for name in UI_MODULES:
        source = (ROOT / name).read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
                found |= {ch for ch in tok.string if ord(ch) > 127 and unicodedata.category(ch)[0] not in "LMC"}
    return "".join(sorted(found))


def css_families():
    import app
    from pomodoro_panel import CSS as POMODORO_CSS
    css = platforms.with_symbol_fonts(app.CSS + POMODORO_CSS)
    return sorted(set(m.strip() for m in re.findall(r"font-family:\s*([^;]+);", css)))


@unittest.skipUnless(platforms.IS_WINDOWS, "Linux finds missing symbols in other fonts by itself")
class SymbolFontTest(unittest.TestCase):
    def test_every_ui_symbol_has_a_font(self):
        platforms.register_fonts()
        symbols = ui_symbols()
        self.assertIn("⚙", symbols)
        families = css_families() + [platforms.font_families("Silkscreen")]  # + the cat's speech bubble
        context = PangoCairo.FontMap.get_default().create_context()
        for family in families:
            missing = []
            for ch in symbols:
                layout = Pango.Layout.new(context)
                layout.set_font_description(Pango.FontDescription.from_string(f"{family.replace(chr(34), '')} 12px"))
                layout.set_text(ch, -1)
                if layout.get_unknown_glyphs_count():
                    missing.append(f"{ch} U+{ord(ch):04X}")
            self.assertEqual(missing, [], f"no font for these symbols with {family}")


if __name__ == "__main__":
    unittest.main()
