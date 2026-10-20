"""Lager app-ikonet: den sittende pixel-katten (orange tabby) i alle størrelser GNOME bruker.

Bruk: python3 make_icon.py <utmappe>   ->  <utmappe>/<N>x<N>/apps/no.zivid.MorgenTodo.png
Katten skaleres med hele piksler, så ikonet er skarpt i alle størrelser.
"""
import sys
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cat  # noqa: E402

ICON = "no.zivid.MorgenTodo"
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
# Standardkatten, uavhengig av hvordan katten er tilpasset på maskinen som bygger pakken
COLORS = dict(cat.BREEDS["orange tabby"])
SPRITE = cat.add_outline(cat.FILL["sit"][0])


def render(size, out):
    w, h = cat.sprite_size(SPRITE)
    scale = max(1, size // max(w, h))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    ox, oy = (size - w * scale) // 2, (size - h * scale) // 2
    for row, line in enumerate(SPRITE):
        for col, ch in enumerate(line):
            if ch != ".":
                cr.set_source_rgb(*cat.hex_to_rgb(COLORS[ch]))
                cr.rectangle(ox + col * scale, oy + row * scale, scale, scale)
                cr.fill()
    out.parent.mkdir(parents=True, exist_ok=True)
    surf.write_to_png(str(out))


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for n in SIZES:
        render(n, root / f"{n}x{n}" / "apps" / f"{ICON}.png")
