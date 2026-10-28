"""Renders the README pixel art from the app's own sprites.

Usage: python3 docs/make_art.py   ->  docs/*.png
Always the default cat (orange tabby), regardless of local customization.
"""
import math
import random
import sys
from pathlib import Path

import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
import cairo  # noqa: E402
from gi.repository import Pango, PangoCairo  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cat  # noqa: E402

BG = (0.055, 0.055, 0.055)
FG = "#ededea"
ACCENT = "#ff6a3d"
P = 4  # screen pixels per sprite pixel


def sprite(name, frame=0, breed="orange tabby", shape="normal"):
    # All colors (bowl, butterfly, accessories) + the breed's fur, ignoring local customization
    return cat.add_outline(cat.SHAPES[shape](cat.FILL[name][frame])), dict(cat.COLORS, **cat.BREEDS[breed])


def draw_sprite(cr, rows, colors, x, y, px=P, flip=False, alpha=1.0):
    w = cat.sprite_size(rows)[0]
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch != ".":
                cr.set_source_rgba(*cat.hex_to_rgb(colors.get(ch, FG)), alpha)
                cr.rectangle(x + ((w - 1 - c) if flip else c) * px, y + r * px, px, px)
                cr.fill()


def text(cr, s, x, y, size, color=FG):
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription.from_string(f"Silkscreen {size}px"))
    lay.set_text(s, -1)
    cr.set_source_rgb(*cat.hex_to_rgb(color))
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, lay)
    return lay.get_pixel_extents()[1]


def canvas(w, h, bg=True):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    if bg:
        cr.set_source_rgb(*BG)
        cr.paint()
    return surf, cr


def banner():
    surf, cr = canvas(900, 250)
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription.from_string("Silkscreen 72px"))
    lay.set_text("GOOD MEUWNING", -1)
    ink, logical = lay.get_pixel_extents()
    tx, ty = 60, 100
    text(cr, "GOOD MEUWNING", tx, ty, 72)
    text(cr, "_", tx + logical.width + 8, ty, 72, ACCENT)
    ground = ty + ink.y  # top of the letters: the cat and bowl stand here
    rows, colors = sprite("walk", 1)
    draw_sprite(cr, rows, colors, 300, ground - cat.sprite_size(rows)[1] * P + P)
    bowl = cat.BOWLS[0]
    draw_sprite(cr, bowl, colors, 640, ground - cat.sprite_size(bowl)[1] * P + P)
    text(cr, "a morning checklist with a pixel cat", tx + 2, ty + ink.y + ink.height + 22, 18, "#8a8a85")
    surf.write_to_png(str(HERE / "banner.png"))


def single(name, frame, file, extra=None, w=200, h=120):
    surf, cr = canvas(w, h, bg=False)
    rows, colors = sprite(name, frame)
    x = (w - cat.sprite_size(rows)[0] * P) // 2 - (20 if extra == "eat" else 0)
    y = h - 8 - cat.sprite_size(rows)[1] * P
    draw_sprite(cr, rows, colors, x, y)
    if extra == "sleep":
        for i, (dx, dy) in enumerate(((60, 30), (75, 12), (92, -4))):
            draw_sprite(cr, cat.Z, {"e": "#8a8a85"}, x + dx, y + dy - 10, px=3, alpha=1 - i * 0.3)
    if extra == "eat":
        bowl = cat.BOWLS[0]
        draw_sprite(cr, bowl, colors, x + 16 * P, h - 8 - cat.sprite_size(bowl)[1] * P + P)
    if extra == "heart":
        draw_sprite(cr, cat.HEART, {"p": "#ff9bb0"}, x + cat.sprite_size(rows)[0] * P // 2 - 10, y - 30, px=4)
    surf.write_to_png(str(HERE / file))


def butterfly():
    surf, cr = canvas(200, 130, bg=False)
    rows, colors = sprite("run", 0)
    draw_sprite(cr, rows, colors, 40, 130 - 8 - cat.sprite_size(rows)[1] * P - 20)  # mid-jump
    draw_sprite(cr, cat.BUTTERFLY_SPRITES[0], colors, 135, 18, px=4)
    surf.write_to_png(str(HERE / "cat-butterfly.png"))


def accessories():
    """Bow tie, coffee cup, beanie, Santa hat and pumpkin hat."""
    looks = [({"bowtie"}, "none", False), ({"coffee"}, "none", True), ({"beanie"}, "none", False),
             (set(), "december", False), (set(), "halloween", False)]
    surf, cr = canvas(130 * len(looks), 140, bg=False)
    for i, (unlocked, season, cup) in enumerate(looks):
        cat.UNLOCKED, cat.SEASON_OVERRIDE = set(unlocked), season
        cat._DRESSED.clear()
        rows, base = sprite("sit", 0)
        rows = cat.add_accessories(rows)
        x, y = i * 130 + 20, 132 - cat.sprite_size(rows)[1] * P
        draw_sprite(cr, rows, base, x, y)
        if cup:
            cup_rows = cat.add_outline(cat.CUP)
            draw_sprite(cr, cup_rows, base, x + cat.sprite_size(rows)[0] * P + 4, 132 - cat.sprite_size(cup_rows)[1] * P, px=3)
    cat.UNLOCKED, cat.SEASON_OVERRIDE = set(), None
    surf.write_to_png(str(HERE / "accessories.png"))


def breeds():
    names = list(cat.BREEDS)
    surf, cr = canvas(110 * len(names), 120, bg=False)
    for i, name in enumerate(names):
        rows, colors = sprite("sit", 0, name, cat.BREED_SHAPES.get(name, "normal"))
        draw_sprite(cr, rows, colors, i * 110 + (110 - cat.sprite_size(rows)[0] * P) // 2, 112 - cat.sprite_size(rows)[1] * P)
    surf.write_to_png(str(HERE / "breeds.png"))


# The extra animations (cat_tricks.py) and a nice moment in each, in seconds
TRICK_POSES = {"zoomies": 1.5, "tailchase": 5, "loaf": 1.5, "box": 1.5, "knead": 1.5,
               "laser": 5, "wave": 7, "bird": 5, "roll": 1.5, "yarn": 2.5}


def tricks():
    """Each extra animation drawn by the app's own TitleCat (with its box, bird, yarn ...), without the title."""
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    Gtk.init()
    import cat_tricks  # noqa: F401
    cat.COLORS.update(cat.BREEDS["orange tabby"])
    cat.set_shape("normal")
    pal = {"bg": "#0e0e0e", "fg": FG, "muted": "#6b6b66", "line": "#262624", "accent": ACCENT}
    blank = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    cat.TitleCat.letter_surface = lambda self, cr, ch, color: blank  # no title, just the cat
    w, h, scale = 300, 110, 2  # the title cat uses 2 screen px per sprite px, the README art 4
    for name, at in TRICK_POSES.items():
        random.seed(name)  # same pictures every run
        c = cat.TitleCat(lambda: pal, forced=name)
        c.draw(None, cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)), w, h)
        for _step in range(round(at / 0.05)):
            c.last -= 0.05
            c.tick(None, None)
        if name == "laser":  # the dot just ahead of the cat
            c.dot["x"] = c.x + cat_tricks.CW + 30 if c.dir > 0 else c.x - 30
        surf, cr = canvas(w, h, bg=False)
        c.draw(None, cr, w, h)
        cr.set_operator(cairo.OPERATOR_CLEAR)  # remove the "_" cursor
        cr.rectangle(c.letters[-1][0] + c.letters[-1][1], 0, w, h)
        cr.fill()
        surf.flush()
        data, stride = surf.get_data(), surf.get_stride()
        ink = [(x, y) for y in range(h) for x in range(w) if data[y * stride + x * 4 + 3]]
        x0, y0 = min(x for x, _ in ink) - 4, min(y for _, y in ink) - 4
        x1, y1 = max(x for x, _ in ink) + 5, max(y for _, y in ink) + 5
        out, oc = canvas((x1 - x0) * scale, (y1 - y0) * scale, bg=False)
        oc.scale(scale, scale)
        oc.set_source_surface(surf, -x0, -y0)
        oc.get_source().set_filter(cairo.FILTER_NEAREST)
        oc.paint()
        out.write_to_png(str(HERE / f"cat-{name}.png"))


def divider():
    """Thin strip: a small cat walking along a line."""
    surf, cr = canvas(600, 40, bg=False)
    cr.set_source_rgb(*cat.hex_to_rgb("#8a8a85"))
    cr.rectangle(0, 34, 600, 2)
    cr.fill()
    rows, colors = sprite("walk", 0)
    draw_sprite(cr, rows, colors, 520, 35 - cat.sprite_size(rows)[1] * 2 + 2, px=2)
    surf.write_to_png(str(HERE / "divider.png"))


if __name__ == "__main__":
    banner()
    single("walk", 0, "cat-walk.png")
    single("sleep", 0, "cat-sleep.png", "sleep")
    single("eat", 0, "cat-eat.png", "eat", w=240)
    single("sit", 2, "cat-sit.png")
    single("sit", 0, "cat-love.png", "heart")
    single("run", 0, "cat-run.png")
    single("groom", 1, "cat-groom.png")
    single("stretch", 0, "cat-stretch.png", w=240)
    butterfly()
    accessories()
    breeds()
    divider()
    tricks()
