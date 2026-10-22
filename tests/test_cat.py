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

    def test_water_tricks(self):
        """drink and thirsty are only shown by the water glasses, not in the rotation."""
        import cat_tricks
        for anim in cat_tricks.WATER_TRICKS:
            self.assertNotIn(anim, cat.ANIMATIONS)
        c = cat.TitleCat(lambda: PAL)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 86)
        c.draw(None, cairo.Context(surf), 320, 86)
        c.thirsty = True
        c.play("drink", 1.0)
        seen = set()
        for _ in range(60):
            c.last -= 0.05
            c.tick(None, None)
            c.draw(None, cairo.Context(surf), 320, 86)
            seen.add(c.anim)
        lunch = 0 <= c.minutes_into_lunch(__import__("datetime").datetime.now()) < c.lunch_duration()
        self.assertEqual(seen, {"drink", "eat" if lunch else "thirsty"})  # first drinks, then thirsty again

    def test_maine_coon_is_bigger(self):
        g = cat.MAINE_COON_GROWTH
        for name, frames in cat.FILL.items():
            for f in frames:
                w, h = cat.sprite_size(f)
                grown = cat._grow(f)
                self.assertEqual(cat.sprite_size(grown), (w + g, h + g), name)
                self.assertEqual("".join(grown).count("e"), "".join(f).count("e"), f"{name}: eyes stretched")

    def test_custom_breed_is_saved_and_loaded(self):
        cat.COLORS.update(cat.BREEDS["black"], e="#00ff00")
        cat.set_shape("fluffy")
        self.assertTrue(cat.save_custom_breed(" Mittens "))
        self.assertFalse(cat.save_custom_breed("tuxedo"))  # built-in names are taken
        self.assertFalse(cat.save_custom_breed("custom"))
        cat.CUSTOM_BREEDS.clear()
        cat.load_cat_settings()
        self.assertEqual(cat.breed_names()[-1], "Mittens")
        self.assertEqual(cat.SETTINGS["breed"], "Mittens")
        self.assertEqual(cat.breed_shape("Mittens"), "fluffy")
        self.assertEqual(cat.breed_colors("Mittens")["e"], "#00ff00")
        cat.delete_custom_breed("Mittens")
        cat.load_cat_settings()
        self.assertEqual((cat.CUSTOM_BREEDS, cat.SETTINGS["breed"]), ({}, "custom"))
        cat.CAT_FILE.unlink()
        cat.load_cat_settings()
        cat.set_shape("normal")

    def test_random_look(self):
        for _i in range(50):
            cat.random_look()
            self.assertEqual(cat.SETTINGS["breed"], "custom")
            for key, _name in cat.PARTS:
                self.assertRegex(cat.COLORS[key], r"^#[0-9a-f]{6}$")
            self.assertEqual(cat.SETTINGS["custom"]["colors"]["b"], cat.COLORS["b"])
        cat.CAT_FILE.unlink(missing_ok=True)
        cat.load_cat_settings()
        cat.set_shape("normal")

    def test_custom_look_comes_back_after_another_breed(self):
        from cat_panel import CatPanel, to_rgba
        panel = CatPanel(cat.TitleCat(lambda: PAL))
        names = cat.breed_names()
        panel.breed.set_selected(names.index("tuxedo"))
        panel.color_btns["e"].set_rgba(to_rgba("#00ff00"))  # now "custom"
        panel.maine_coon.set_active(True)
        self.assertEqual(cat.SETTINGS["breed"], "custom")
        panel.breed.set_selected(names.index("siamese"))
        self.assertEqual(cat.COLORS["e"], cat.BREEDS["siamese"]["e"])
        cat.load_cat_settings()  # also after a restart
        panel.show_current_settings()
        panel.breed.set_selected(len(names))  # "custom" again
        self.assertEqual((cat.SETTINGS["breed"], cat.COLORS["e"], cat.SETTINGS["shape"]), ("custom", "#00ff00", "fluffy"))
        self.assertEqual(cat.COLORS["b"], cat.BREEDS["tuxedo"]["b"])
        cat.CAT_FILE.unlink(missing_ok=True)
        cat.SETTINGS.pop("custom", None)
        cat.load_cat_settings()
        cat.set_shape("normal")

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
