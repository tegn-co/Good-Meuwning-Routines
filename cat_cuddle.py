"""Cuddle time: the cat comes up close, fills much of the window, purrs and wants to be petted.

It starts when you pet the cat on the title (stroke the pointer back and forth over it), once a day as
a reward when the whole list is done, or with --cat=cuddle. Stroke its face and it closes its eyes,
hearts pop up and it stays a little longer; click anywhere and it says goodbye and goes back. The
close-up is a front view of the cat in its own colors, kneading with its paws and blinking slowly.
CatOverlay (cat.py) runs it; never in productivity mode.
"""
import math
import random
import time

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

import cat  # noqa: E402
import platforms  # noqa: E402
from translations import _  # noqa: E402

W, H = 30, 26  # the face in sprite pixels (before the outline)
MID = (W - 1) / 2  # the middle line, between two pixel columns
APPROACH, LEAVE = 1.2, 0.8  # seconds to come close and to go back
STAY, STAY_MAX = 25.0, 60.0  # seconds it stays; petting makes it stay longer
PET_HEART = 90  # pixels of stroking per heart


def _in_triangle(x, y, a, b, c):
    def side(p, q):
        return (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def face(eyes="open", knead=0):
    """The front view, as fill letters. eyes: open, half, closed (a slow blink) or happy (^ ^).
    knead: 0, or 1/2 for the left/right paw lifted."""
    g = [["."] * W for _ in range(H)]

    def put(x, y, ch):
        if 0 <= x < W and 0 <= y < H:
            g[y][x] = ch

    def both(x, y, ch):  # this pixel and its mirror image
        put(x, y, ch)
        put(W - 1 - x, y, ch)

    for y in range(17, H):  # body
        for x in range(W):
            if abs(x - MID) <= 8.5 + (y - 17) * 0.45:
                put(x, y, "b")
    for y in range(H):  # head
        for x in range(W):
            if ((x - MID) / 12.6) ** 2 + ((y - 11.5) / 8.4) ** 2 <= 1:
                put(x, y, "b")
    for y in range(9):  # ears, pink inside
        for x in range(W // 2):
            if _in_triangle(x + 0.5, y + 0.5, (4, 0), (1, 8.5), (11.5, 6)):
                both(x, y, "p" if _in_triangle(x + 0.5, y + 0.5, (4.4, 2.6), (2.8, 7.4), (8.6, 6.2)) else "b")
    for y in range(4, 7):  # stripes on the forehead and the cheeks
        both(11, y, "s")
        both(14, y, "s")
    for y in (12, 14):
        for x in range(1, 4):
            both(x, y, "s")
    for y in range(12, 19):  # muzzle
        for x in range(W):
            if ((x - MID) / 5.4) ** 2 + ((y - 15.2) / 3.0) ** 2 <= 1:
                put(x, y, "w")
    for y in range(18, H):  # chest
        for x in range(W):
            if ((x - MID) / 3.4) ** 2 + ((y - 22) / 4.2) ** 2 <= 1:
                put(x, y, "w")
    for x in range(13, 17):  # nose
        put(x, 13, "p")
    both(14, 14, "p")
    for x, y in ((12, 15), (13, 16), (14, 15)):  # mouth: a little "w"
        both(x, y, "o")
    for side, (x0, x1) in ((1, (4, 10)), (2, (20, 26))):  # paws, kneading
        lift = 1 if knead == side else 0
        for y in range(H - 3 - lift, H - lift):
            for x in range(x0, x1):
                put(x, y, "w")
        for x in range(x0, x1):  # the paw lifts off: body color below it
            if lift:
                put(x, H - 1, "b")
    # Eyes, left and right (the shine is top left in both)
    for ex in (8.5, 20.5):
        for y in range(8, 14):
            for x in range(W):
                inside = ((x - ex) / 2.2) ** 2 + ((y - 10.5) / 2.7) ** 2 <= 1
                if not inside:
                    continue
                if eyes == "open":
                    put(x, y, "e")
                elif eyes == "half":
                    put(x, y, "e" if y >= 10.5 else "b")
        if eyes == "open":  # a big shine: soft, friendly eyes
            put(int(ex) - 1, 9, "w")
            put(int(ex), 9, "w")
            put(int(ex) - 1, 10, "w")
        elif eyes in ("closed", "happy"):
            arc = ((-2, 10), (-1, 11), (0, 11), (1, 11), (2, 10)) if eyes == "closed" else \
                  ((-2, 11), (-1, 10), (0, 9), (1, 10), (2, 11))  # a sleepy line, or ^ when happy
            for dx, y in arc:
                put(int(ex + 0.5) + dx, y, "o")
    return ["".join(r) for r in g]


FACES = {(eyes, knead): cat.add_outline(face(eyes, knead))
         for eyes in ("open", "half", "closed", "happy") for knead in (0, 1, 2)}


def _ease(k):
    return 1 - (1 - min(max(k, 0.0), 1.0)) ** 3


class Cuddle:
    """One cuddle: comes close, purrs and is petted, then goes back to where it came from."""

    def __init__(self, overlay, start):
        self.overlay, self.start = overlay, start  # start: the paws' (x, y) when it began
        self.t0 = time.monotonic()
        self.until = self.t0 + STAY
        self.leaving = None
        self.stroked, self.happy_until = 0.0, 0.0
        self.last_pointer = None
        self.hearts = []  # (x, y, born)
        self.purrs = []  # (side, born, word)
        self.next_purr = self.t0 + APPROACH

    # --- state ---
    def closeness(self, now):
        """0 = its normal size where it was, 1 = up close."""
        if self.leaving is not None:
            return 1 - _ease((now - self.leaving) / LEAVE)
        return _ease((now - self.t0) / APPROACH)

    def done(self, now):
        return self.leaving is not None and now - self.leaving >= LEAVE

    def leave(self):
        if self.leaving is None:
            self.leaving = time.monotonic()
            self.overlay.title.say(_("mrrp ♥"), 2)

    def tick(self, now):
        if self.leaving is None and now >= self.until:
            self.leave()
        if self.leaving is None and now >= self.next_purr and self.closeness(now) >= 1:
            self.purrs.append((random.choice((-1, 1)), now, random.choice(("purr", "prrr", "mrrr", "purrr"))))
            self.next_purr = now + random.uniform(0.7, 1.4) * (0.6 if now < self.happy_until else 1)
        self.purrs = [p for p in self.purrs if now - p[1] < 2.5]
        self.hearts = [h for h in self.hearts if now - h[2] < 1.6]

    def pet(self, x, y):
        """The pointer moved: strokes over the face make the cat happy."""
        now = time.monotonic()
        last, self.last_pointer = self.last_pointer, (x, y)
        fx, fy, fw, fh, _px = self.layout(now)
        if last is None or self.leaving is not None or not (fx <= x <= fx + fw and fy <= y <= fy + fh):
            return
        self.stroked += math.hypot(x - last[0], y - last[1])
        if self.stroked >= PET_HEART:
            self.stroked -= PET_HEART
            self.hearts.append((x, y, now))
            self.happy_until = now + 1.5
            self.until = min(self.t0 + STAY_MAX, max(self.until, now + 8))  # more petting, more time

    # --- drawing ---
    def layout(self, now):
        """(x, y, width, height, pixel size) of the face in the overlay."""
        w, h = self.overlay.area_width(), self.overlay.area_height()
        fw, fh = len(FACES[("open", 0)][0]), len(FACES[("open", 0)])
        big = max(cat.PX, min(w * 0.92 / fw, h * 0.8 / fh))
        k = self.closeness(now)
        px = max(1, round(cat.PX + (big - cat.PX) * k))  # whole screen pixels: no seams between the pixels
        cx = self.start[0] + (w / 2 - self.start[0]) * k
        bottom = self.start[1] + (h - self.start[1]) * k
        return round(cx - fw * px / 2), round(bottom - fh * px), fw * px, fh * px, px

    def eyes(self, now):
        if now < self.happy_until:
            return "happy"
        blink = (now - self.t0) % 5.0  # a slow blink: "I trust you"
        return "half" if blink < 0.3 or 0.7 <= blink < 1.0 else "closed" if blink < 0.7 else "open"

    def draw(self, cr, width, height):
        now = time.monotonic()
        k = self.closeness(now)
        pal = self.overlay.title.palette()
        cr.set_source_rgba(*cat.hex_to_rgb(pal["bg"]), 0.6 * k)  # the window fades behind the cat
        cr.paint()
        x, y, fw, fh, px = self.layout(now)
        if k >= 1 and self.leaving is None:
            x += (1 if int(now * 28) % 2 else 0)  # purring: a tiny shiver
        knead = 1 + int(now / 0.45) % 2 if k >= 1 else 0
        sprite = FACES[(self.eyes(now) if k >= 1 else "open", knead)]
        colors = cat.current_colors()
        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        for row, line in enumerate(sprite):
            for col, ch in enumerate(line):
                if ch != ".":
                    cr.set_source_rgb(*cat.hex_to_rgb(colors.get(ch, pal["fg"])))
                    cr.rectangle(x + col * px, y + row * px, px, px)
                    cr.fill()
        cr.restore()
        mid, muzzle = x + fw / 2, y + 16 * px  # whiskers from the muzzle, out past the cheeks
        cr.set_source_rgba(*cat.hex_to_rgb(colors["o"]), 0.75)
        cr.set_line_width(max(1.0, px * 0.35))
        for side in (-1, 1):
            for i in range(3):
                cr.move_to(mid + side * 5 * px, muzzle + (i - 1) * px * 0.9)
                cr.line_to(mid + side * 15.5 * px, muzzle + (i - 1) * px * 2.2 - px)
        cr.stroke()
        if k < 1:
            return
        font = f"{platforms.font_families('Silkscreen')} {max(8, round(px * 2))}px"
        for side, born, word in self.purrs:
            age = (now - born) / 2.5
            cr.set_source_rgba(*cat.hex_to_rgb(pal["muted"]), 1 - age)
            self.text(cr, word, mid + side * (fw * 0.42 + age * px * 4), y + fh * 0.35 - age * px * 10, font)
        for hx, hy, born in self.hearts:
            age = (now - born) / 1.6
            size = max(2, round(px * 0.6))
            cr.set_source_rgba(*cat.hex_to_rgb("#ff9bb0"), 1 - age)
            for r, line in enumerate(cat.HEART):
                for c, ch in enumerate(line):
                    if ch != ".":  # starts above the hand that strokes, and floats up
                        cr.rectangle(round(hx + (c - 2.5) * size), round(hy - px * 3 - age * px * 18 + (r - 5) * size), size, size)
            cr.fill()
        cr.set_source_rgba(*cat.hex_to_rgb(pal["muted"]), 1)
        self.text(cr, _("stroke me ♥ · click to let go"), width / 2, 10, f"{platforms.font_families('Silkscreen')} 9px")

    @staticmethod
    def text(cr, s, cx, y, font):
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription.from_string(font))
        lay.set_text(s, -1)
        cr.move_to(cx - lay.get_pixel_extents()[1].width / 2, y)
        PangoCairo.show_layout(cr, lay)
