import unittest

from tests import env  # noqa: F401
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

import cairo  # noqa: E402
import cat  # noqa: E402

PAL = {"bg": "#0e0e0e", "fg": "#ededea", "muted": "#6b6b66", "line": "#262624", "accent": "#ff6a3d"}


class CatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()

    def test_sprites_are_rectangular_with_known_colors(self):
        for shape in cat.SHAPES:
            cat.set_shape(shape)
            for name, frames in cat.SPRITES.items():
                for f in frames:
                    self.assertEqual(len({len(r) for r in f}), 1, f"{shape}/{name} not rectangular")
                    self.assertTrue(set("".join(f)) <= set(cat.COLORS) | {"."}, f"{shape}/{name} unknown color")
        cat.set_shape("normal")

    def test_every_animation_ticks_and_draws(self):
        for anim in cat.ANIMATIONS + ["eat"]:
            for mode in (None, "eat"):  # "eat" = long pomodoro break, also outside lunch
                c = cat.TitleCat(lambda: PAL, forced=None if mode else anim)
                c.mode = mode
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 86)
                cr = cairo.Context(surf)
                c.draw(None, cr, 320, 86)
                for _ in range(40):
                    c.last -= 0.05
                    c.tick(None, None)
                    c.draw(None, cr, 320, 86)
                c.say("good job!")
                c.draw(None, cr, 320, 86)

    def test_bowl_outside_lunch(self):
        cat.LUNCH = (23 * 60 + 58, 23 * 60 + 59)
        c = cat.TitleCat(lambda: PAL)
        c.mode = "eat"
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 86)
        c.draw(None, cairo.Context(surf), 320, 86)
        c.tick(None, None)
        c.draw(None, cairo.Context(surf), 320, 86)  # crashed before v1.0.4


if __name__ == "__main__":
    unittest.main()
