"""The title text ("good morning") with an animated pixel cat living on top of the letters.

The animation switches every 15 minutes:
  walk      - walks back and forth; the letters dip under its paws
  play      - chases the "_" cursor along the title
  sleep     - sleeps curled up on the last word; the letters breathe along
  sit       - sits at the end and swats the cursor into the air
  jump      - hops back and forth over the gap between words; the landing letter bounces
  climb     - jumps onto the window edge and climbs around the frame (see CatOverlay)
  butterfly - chases a butterfly along the title
  groom     - sits and washes with its paw
  stretch   - stretches (rear in the air), strolls a bit, stretches again
Moving cats hop over every gap between words. During lunch (default 11-12, set under
settings > schedule) the cat eats from a bowl that empties over the hour.

Clicking the title sends a wave through the letters and makes the cat happy. Clicking the cat
5 times quickly starts "playtime": it pounces after the mouse pointer. If the title scrolls out
of view, the cat walks around the window frame until it is back. say(text) shows a speech bubble.

Sprites are drawn as fill using letter codes (b = fur, s = stripes, w = white, p = pink,
e = eye, . = empty); the outline is added automatically. All sprites face right.
"""
import json
import math

import cairo
import random
import time
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk, Pango, PangoCairo  # noqa: E402

from database import CONFIG_DIR  # noqa: E402  (same config dir as the rest of the app, follows XDG_CONFIG_HOME)
from translations import _  # noqa: E402

PX = 2  # screen pixels per sprite pixel
PLAYTIME_SECONDS = 30  # how long the cat chases the pointer before returning to the title
FPS = 24  # frame rate while the cat moves (smooth enough for pixel art)
CALM_FPS = 8  # while sleeping, sitting or eating with no bouncing letters
# A plain GLib timer instead of add_tick_callback: a tick callback keeps GTK's frame clock at 60 Hz
# with full layout all the time, which alone cost 15-25 % CPU.
_SURFACES = {}  # pre-rendered sprites/letters, so each frame just blits them instead of drawing pixel by pixel
SWITCH_MINUTES = 15
ANIMATIONS = ["walk", "play", "sleep", "sit", "jump", "climb", "butterfly", "groom", "stretch"]
TRICKS = {}  # more animations, added by cat_tricks.py (imported at the end of this file)
LUNCH = (11 * 60, 12 * 60)  # lunch start/end in minutes after midnight (set under settings > schedule)
TITLE = _("good morning")  # default title; TitleCat(title=...) can use another
# --- Appearance and phrases (editable in the cat settings, saved in CAT_FILE) ---
CAT_FILE = CONFIG_DIR / "cat.json"
# Colorable parts of the cat: sprite key, name in the settings
PARTS = [("b", "fur"), ("s", "stripes"), ("w", "chest & paws"), ("p", "nose & ears"), ("e", "eyes"), ("o", "outline")]
BREEDS = {
    "orange tabby": {"b": "#f4a24c", "s": "#d9772b", "w": "#fff6ea", "p": "#ff9bb0", "e": "#2b1b14", "o": "#2b1b14"},
    "grey tabby": {"b": "#a3a8ae", "s": "#6e747b", "w": "#f2f2f2", "p": "#f2a5b4", "e": "#1e2226", "o": "#1e2226"},
    "black": {"b": "#2c2c33", "s": "#2c2c33", "w": "#2c2c33", "p": "#e58fa0", "e": "#f5d33b", "o": "#0d0d10"},
    "tuxedo": {"b": "#26262b", "s": "#26262b", "w": "#f7f7f2", "p": "#ff9bb0", "e": "#9bd36a", "o": "#0d0d10"},
    "calico": {"b": "#fbf3e6", "s": "#e8913f", "w": "#fbf3e6", "p": "#ff9bb0", "e": "#2b1b14", "o": "#3a2a20"},
    "white": {"b": "#f7f5f0", "s": "#e6e2da", "w": "#ffffff", "p": "#ffb3c1", "e": "#4a90d9", "o": "#5c5a57"},
    "siamese": {"b": "#efe2cc", "s": "#7a5a45", "w": "#efe2cc", "p": "#c98f7d", "e": "#4a90d9", "o": "#4a3528"},
    "maine coon": {"b": "#a8743f", "s": "#5e3b1e", "w": "#f3e9d9", "p": "#e8a0a0", "e": "#d4a72c", "o": "#2a1a10"},
}
# Breeds with their own shape (the rest use the default): fluffy = bigger, with ear tufts and a thick tail
BREED_SHAPES = {"maine coon": "fluffy"}
# Breeds saved from the cat panel: name -> {"colors": {part: hex}, "shape": "normal"/"fluffy"}
CUSTOM_BREEDS = {}
# What the cat says; alternatives are separated by | and picked at random. Empty = silent
EVENTS = [
    ("check", "you check something off"),
    ("all_done", "the whole list is done"),
    ("click", "you click the title"),
    ("start", "a focus session starts"),
    ("break", "time for a break"),
    ("focus", "the break is over"),
]
PHRASES = {"check": _("good job!"), "all_done": _("all done!"), "click": "",
           "start": _("let's go!"), "break": _("break time!"), "focus": _("focus time!")}
DEFAULT_PHRASES = dict(PHRASES)

COLORS = dict(BREEDS["orange tabby"], c="#5aa9e6", f="#9a5b2e",  # c/f = food bowl
              v="#b48cff", k="#3a2a55")  # v/k = butterfly
SETTINGS = {"breed": "orange tabby", "shape": "normal"}  # shape is kept when colors are customized ("custom")


def load_cat_settings():
    try:
        data = json.loads(CAT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    CUSTOM_BREEDS.clear()
    for name, breed in data.get("custom_breeds", {}).items():
        if name in BREEDS or not isinstance(breed, dict):
            continue
        colors = dict(BREEDS["orange tabby"], **{k: v for k, v in breed.get("colors", {}).items() if k in dict(PARTS)})
        CUSTOM_BREEDS[name] = {"colors": colors, "shape": "fluffy" if breed.get("shape") == "fluffy" else "normal"}
    SETTINGS["breed"] = data.get("breed", "orange tabby")
    SETTINGS["wear"] = data.get("wear", {})
    SETTINGS["shape"] = data.get("shape", breed_shape(SETTINGS["breed"]))
    COLORS.update(breed_colors(SETTINGS["breed"]) or BREEDS["orange tabby"])
    COLORS.update({k: v for k, v in data.get("colors", {}).items() if k in dict(PARTS)})
    PHRASES.update({k: v for k, v in data.get("phrases", {}).items() if k in PHRASES})


def save_cat_settings():
    try:
        CAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        CAT_FILE.write_text(json.dumps({
            "breed": SETTINGS["breed"],
            "shape": SETTINGS["shape"],
            "colors": {k: COLORS[k] for k, _ in PARTS},
            "phrases": PHRASES,
            "wear": SETTINGS.get("wear", {}),
            "custom_breeds": CUSTOM_BREEDS,
        }, indent=2), encoding="utf-8")
    except OSError:
        pass


def breed_names():
    """Built-in breeds first, then the saved ones."""
    return list(BREEDS) + list(CUSTOM_BREEDS)


def breed_colors(name):
    """A breed's colors, or None for "custom" (unsaved) and unknown names."""
    return BREEDS.get(name) or CUSTOM_BREEDS.get(name, {}).get("colors")


def breed_shape(name):
    return CUSTOM_BREEDS[name]["shape"] if name in CUSTOM_BREEDS else BREED_SHAPES.get(name, "normal")


def save_custom_breed(name):
    """Save the current colors and shape as a breed (replaces a saved one with the same name).
    Returns False for names that can't be used: empty, "custom" or a built-in breed."""
    name = name.strip()
    if not name or name in BREEDS or name in ("custom", _("custom")) or name in map(_, BREEDS):
        return False
    CUSTOM_BREEDS[name] = {"colors": {k: COLORS[k] for k, _p in PARTS}, "shape": SETTINGS["shape"]}
    SETTINGS["breed"] = name
    save_cat_settings()
    return True


def delete_custom_breed(name):
    """Forget a saved breed; the cat keeps its look, now as "custom"."""
    if CUSTOM_BREEDS.pop(name, None) is not None:
        if SETTINGS["breed"] == name:
            SETTINGS["breed"] = "custom"
        save_cat_settings()


def random_phrase(event):
    """A random phrase for the event, or "" if the cat should stay quiet."""
    options = [p.strip() for p in PHRASES.get(event, "").split("|") if p.strip()]
    return random.choice(options) if options else ""


load_cat_settings()


def _side_view_cat(legs):
    """Side view: tail on the left, head facing right, plus two rows of legs."""
    return [
        "b.........." + "b.....b",
        "b.........." + "bp...pb",
        "b.........." + "bbbbbbb",
        ".b........." + "bebbbeb",
        "..bbsbbsbbb" + "bebwbeb",
        "..bbbsbbsbb" + "bbwpwbb",
        "..bbbbbbbbb" + "bbwwwbb",
        "..bbbbbbbbb" + "wwwww..",
        "..bbbbbbbbb" + "bwww...",
    ] + legs


FILL = {
    "walk": [
        _side_view_cat(["..bb.bb....bb.bb..", "..ww.ww....ww.ww.."]),
        _side_view_cat([".bb...bb...bb..bb.", ".ww...ww...ww..ww."]),
    ],
    "run": [
        _side_view_cat([".bb...........bb..", "ww.............ww."]),
        _side_view_cat(["....bbb....bbb....", "....ww......ww...."]),
    ],
    "sit": [
        [
            "....b.....b",
            "....bp...pb",
            "....bbbbbbb",
            "....bebbbeb",
            "....bebwbeb",
            "....bbwpwbb",
            ".....bwwwb.",
            "....bbwwwbb",
            "...bbbwwwbb",
            "...bsbwwwbb",
            "...bsbbwbbb",
            "bbbbbbbbbbb",
            ".....ww.ww.",
        ],
        [
            "....b.....b",
            "....bp...pb",
            "....bbbbbbb",
            "....bebbbeb",
            "....bebwbeb",
            "....bbwpwbb",
            ".....bwwwb.",
            "....bbwwwbb",
            "b..bbbwwwbb",
            "b..bsbwwwbb",
            ".b.bsbbwbbb",
            "..bbbbbbbbb",
            ".....ww.ww.",
        ],
        [  # swatting with the paw
            "....b.....b..",
            "....bp...pb..",
            "....bbbbbbb..",
            "....bebbbeb..",
            "....bebwbeb..",
            "....bbwpwbb..",
            ".....bwwwbbww",
            "....bbwwwbb..",
            "...bbbwwwbb..",
            "...bsbwwwbb..",
            "...bsbbwbbb..",
            "bbbbbbbbbbb..",
            ".....ww......",
        ],
    ],
    "sleep": [
        [
            ".........b.....b",
            ".........bp...pb",
            "...bbbbbbbbbbbbb",
            "..bsbbsbbbebbbeb",
            ".bbbsbbsbbbwpwbb",
            "bbbbbbbbbbbbwbbb",
            "bbbbbbbbbbbbbbbb",
            ".bbbbbbbbbbbbbb.",
            "..bbbbbbbbbbbww.",
        ],
        [
            ".........b.....b",
            ".........bp...pb",
            "....bbbbbbbbbbbb",
            "..bsbbsbbbebbbeb",
            ".bbbsbbsbbbwpwbb",
            "bbbbbbbbbbbbwbbb",
            "bbbbbbbbbbbbbbbb",
            ".bbbbbbbbbbbbbb.",
            "..bbbbbbbbbbbww.",
        ],
    ],
}
FILL["eat"] = [
    [  # head down in the bowl, eyes contentedly closed
        "b.................",
        "b.................",
        "b..........b.....b",
        ".b.........bp...pb",
        "..bbsbbsbbbbbbbbbb",
        "..bbbsbbsbbbobbbob",
        "..bbbbbbbbbbbbwbbb",
        "..bbbbbbbbbbbwpwbb",
        "..bbbbbbbbb.bwwwb.",
        "..bb.bb....bb.bb..",
        "..ww.ww....ww.ww..",
    ],
    [  # head raised a little, chewing
        "b.................",
        "b..........b.....b",
        "b..........bp...pb",
        ".b.........bbbbbbb",
        "..bbsbbsbbbbebbbeb",
        "..bbbsbbsbbbebwbeb",
        "..bbbbbbbbbbbwpwbb",
        "..bbbbbbbbbbbwwwbb",
        "..bbbbbbbbb.wwwww.",
        "..bb.bb....bb.bb..",
        "..ww.ww....ww.ww..",
    ],
]
# Grooming: sitting with a paw at the mouth, eyes closed; frame 2 has the tongue out
FILL["groom"] = [
    [
        "....b.....b..",
        "....bp...pb..",
        "....bbbbbbb..",
        "....bobbbob..",
        "....bbbwbbb..",
        "....bbwpwbww.",
        ".....bwwwbww.",
        "....bbwwwbb..",
        "...bbbwwwbb..",
        "...bsbwwwbb..",
        "...bsbbwbbb..",
        "bbbbbbbbbbb..",
        ".....ww......",
    ],
    [
        "....b.....b..",
        "....bp...pb..",
        "....bbbbbbb..",
        "....bobbbob..",
        "....bbbwbbb..",
        "....bbwpwbww.",
        ".....bwpwbww.",
        "....bbwwwbb..",
        "...bbbwwwbb..",
        "...bsbwwwbb..",
        "...bsbbwbbb..",
        "bbbbbbbbbbb..",
        ".....ww......",
    ],
]


def _stretch(tail_up):
    """Stretch pose: rear up, chest down, front legs reaching forward, eyes closed."""
    w, h = 22, 10
    g = [["."] * w for _ in range(h)]
    for x in range(2, 15):  # body slopes down from the rear to the chest
        top = 2 + max(0, x - 6) // 2
        bottom = 6 if x <= 6 else min(8, 6 + (x - 6) // 2)
        for y in range(top, bottom + 1):
            g[y][x] = "s" if (x in (4, 7, 10) and y == top + 1) else "b"
    for x in (2, 3, 5, 6):  # hind legs
        g[7][x] = g[8][x] = "b"
        g[9][x] = "w"
    for x in range(11, 22):  # front legs stretched forward along the ground
        g[9][x] = "w"
    head = ["b.....b", "bp...pb", "bbbbbbb", "bobbbob", "bobwbob", "bbwpwbb", ".bwwwb."]  # eyes closed
    for dy, row in enumerate(head):
        for dx, ch in enumerate(row):
            if ch != ".":
                g[2 + dy][14 + dx] = ch
    tail = [(1, 1), (0, 0)] if tail_up else [(1, 2), (0, 3)]
    for x, y in tail:
        g[y][x] = "b"
    return ["".join(r) for r in g]


FILL["stretch"] = [_stretch(True), _stretch(False)]
BUTTERFLY = [["vv.vv", "vvkvv", ".vkv.", "..k.."], [".v.v.", ".vkv.", "..k..", "..k.."]]

# Closed eyes while sleeping: the eyes become a dark line
FILL["sleep"] = [[r.replace("e", "o") for r in f] for f in FILL["sleep"]]
HEART = [".p.p.", "ppppp", "ppppp", ".ppp.", "..p.."]
Z = ["eee", "..e", ".e.", "e..", "eee"]


def add_outline(fill):
    """Add a dark 1-pixel outline around the fill."""
    w = max(len(r) for r in fill) + 2
    grid = ["." * w] + ["." + r.ljust(w - 2, ".") + "." for r in fill] + ["." * w]
    out = []
    for y, row in enumerate(grid):
        line = ""
        for x, ch in enumerate(row):
            if ch == ".":
                near = any(
                    0 <= y + dy < len(grid) and 0 <= x + dx < w and grid[y + dy][x + dx] != "."
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                )
                line += "o" if near else "."
            else:
                line += ch
        out.append(line)
    return out


MAINE_COON_GROWTH = 2  # sprite pixels the Maine Coon is taller and longer than the other cats


def _transpose(rows):
    return ["".join(col) for col in zip(*rows)]


def _repeat_body_lines(lines, count, rank):
    """Repeat `count` lines with fur (b/s) and no face pixels (eyes, nose/inner ears), best rank() first."""
    ok = [i for i, ln in enumerate(lines) if (ln.count("b") + ln.count("s")) and not set(ln) & set("epo")]
    for i in sorted(sorted(ok, key=rank)[:count], reverse=True):  # from the bottom up, so earlier indices stay valid
        lines.insert(i + 1, lines[i])
    return lines


def _grow(fill, extra=MAINE_COON_GROWTH):
    """A bigger cat: `extra` rows and columns of the body are repeated. Columns preferably go through the
    middle of the torso, not through the ear tips (they keep their tufts) or the legs and chest."""
    w = max(len(r) for r in fill)
    rows = [r.ljust(w, ".") for r in fill]
    fur = lambda ln: ln.count("b") + ln.count("s")
    rows = _repeat_body_lines(rows, extra, lambda i: -fur(rows[i]))
    ears = next((i for i, r in enumerate(rows) if "p" in r), 0) + 1  # rows down to the inner ears
    cols = _transpose(rows)
    rank = lambda i: (set(cols[i][:ears]) != {"."}, "w" in cols[i], abs(i - w / 2), -fur(cols[i]))
    return _transpose(_repeat_body_lines(cols, extra, rank))


def maine_coon_shape(fill):
    """Maine Coon shape: a couple of pixels bigger, tall dark tufts on the ear tips and a double-thick tail."""
    rows = _grow(fill)
    # Tail: rows starting with a single fur pixel at the far left get one more pixel
    for i, r in enumerate(rows):
        j = len(r) - len(r.lstrip("."))
        if r.strip() and j <= 1 and r[j] == "b" and j + 1 < len(r) and r[j + 1] == ".":
            rows[i] = r[: j + 1] + "b" + r[j + 2:]
    # Ear tufts: a dark pixel above each ear tip on the top ear row ("p" = inner ear on the row below)
    ear_row = next(i for i, r in enumerate(rows) if i + 1 < len(rows) and "p" in rows[i + 1])
    tips = rows[ear_row]
    tuft = "".join("s" if ch == "b" and tips[max(0, k - 1):k + 2].count("b") == 1 else "." for k, ch in enumerate(tips))
    # Tufts are two pixels tall; if there are no rows above the ears, add them at the top
    for _ in range(max(0, 2 - ear_row)):
        rows.insert(0, "")
        ear_row += 1
    for r in (ear_row - 1, ear_row - 2):
        above = rows[r].ljust(len(tuft), ".")
        rows[r] = "".join(t if t != "." else a for t, a in zip(tuft, above))
    return rows


SHAPES = {"normal": lambda f: f, "fluffy": maine_coon_shape}  # "fluffy" is the saved setting value
SPRITES = {}
BUTTERFLY_SPRITES = [add_outline(b) for b in BUTTERFLY]


def set_shape(shape):
    """Build the sprites for a shape (updates SPRITES in place, so the cat uses them right away)."""
    SETTINGS["shape"] = shape if shape in SHAPES else "normal"
    SPRITES.update({name: [add_outline(SHAPES[SETTINGS["shape"]](f)) for f in frames] for name, frames in FILL.items()})


set_shape(SETTINGS["shape"])

# --- Accessories, season and time of day ---
# Unlocked by streaks (consecutive days with the whole list done); what the cat wears is chosen in the cat panel
UNLOCKS = [("bowtie", 3, "bow tie"), ("coffee", 5, "coffee cup"), ("beanie", 10, "beanie")]
UNLOCKED = set()  # set by the window from the best streak
SEASON_OVERRIDE = None  # "december" / "halloween" / "none" - for testing
ACCESSORIES = {
    "beanie": ["..hhhhh..", ".hhhhhhh.", "HHHHHHHHH"],  # knitted beanie with brim
    "santa": [".......WW", ".....rr..", "...rrrrr.", "..rrrrrrr", "WWWWWWWWW"],  # Santa hat with pompom
    "bowtie": ["q...q", "qqqqq", "q...q"],
}
CUP = ["CCCC.", "CddCC", "CddC.", "CCCC."]
COLORS.update(h="#4a7bd0", H="#e9e6de", r="#d63a3a", W="#ffffff", q="#c93a4a", C="#f2efe9", d="#6b3e1e")
_DRESSED = {}


def current_season(today=None):
    if SEASON_OVERRIDE:
        return None if SEASON_OVERRIDE == "none" else SEASON_OVERRIDE
    d = today or datetime.now().date()
    if d.month == 12:
        return "december"
    if d.month == 10 and d.day >= 24:
        return "halloween"
    return None


def worn_accessories():
    """Accessories the cat is wearing right now."""
    wear = SETTINGS.get("wear", {})
    on = [k for k, _, _ in UNLOCKS if k in UNLOCKED and wear.get(k, True)]
    if current_season() == "december":
        on = [k for k in on if k != "beanie"] + ["santa"]  # the Santa hat replaces the beanie
    return tuple(on)


def current_colors():
    """Normal colors, or ghost colors during Halloween week."""
    if current_season() != "halloween":
        return COLORS
    return dict(COLORS, b="#f4f4f6", s="#d9dbe2", w="#ffffff", o="#9a9cab", p="#c7c9d6", e="#2b2b33")


def add_accessories(sprite):
    """Stamp accessories (hat, bow tie) into the sprite itself, so they follow when the cat flips and rotates."""
    on = worn_accessories()
    hats = [a for a in on if a in ("beanie", "santa")]
    if not hats and "bowtie" not in on:
        return sprite
    key = (tuple(sprite), on)
    if key in _DRESSED:
        return _DRESSED[key]
    grid = [list(r) for r in sprite]
    w = len(grid[0])

    def stamp(acc, top, center, with_outline=True):
        nonlocal grid
        acc = add_outline(acc) if with_outline else acc
        left = round(center - (len(acc[0]) - 1) / 2)
        if top < 0:  # hat sticks out above the sprite: add rows on top (feet stay at the bottom)
            grid = [["."] * w for _ in range(-top)] + grid
            top = 0
        for dy, row in enumerate(acc):
            for dx, ch in enumerate(row):
                x = left + dx
                if ch == "." or not 0 <= x < w or top + dy >= len(grid):
                    continue
                if ch == "o" and grid[top + dy][x] not in (".", "o"):
                    continue  # the accessory's outline must not cover the cat
                grid[top + dy][x] = ch

    if "bowtie" in on:  # below the muzzle (nose = pink pixel between two white ones)
        for r, row in enumerate(grid):
            c = next((c for c in range(1, w - 1) if row[c] == "p" and row[c - 1] == "w" and row[c + 1] == "w"), None)
            if c is not None:
                stamp(ACCESSORIES["bowtie"], r + 2, c, with_outline=False)  # small, right below the muzzle
                break
    if hats:  # above the ears (the row with pink inner ears)
        ear = next((r for r, row in enumerate(grid) if row.count("p") >= 2), None)
        if ear is not None:
            pinks = [c for c, ch in enumerate(grid[ear]) if ch == "p"]
            hat = ACCESSORIES[hats[-1]]
            stamp(hat, ear + 1 - len(hat) - 1, (pinks[0] + pinks[-1]) / 2)
    result = ["".join(r) for r in grid]
    if len(_DRESSED) > 300:
        _DRESSED.clear()
    _DRESSED[key] = result
    return result


def yawning_sprite(sprite):
    """Yawn: eyes closed and mouth open (below the nose)."""
    rows = [r.replace("e", "o") for r in sprite]
    for r, row in enumerate(rows[:-1]):
        c = row.find("wpw")
        if c >= 0:
            below = rows[r + 1]
            rows[r + 1] = below[:c + 1] + "o" + below[c + 2:]
            break
    return rows
# Food bowl with 2, 1 or 0 rows of food
_BOWL = ["..ffffff..", ".ffffffff.", "cccccccccc", ".cccccccc.", "..cccccc.."]
BOWLS = [add_outline(_BOWL[2 - food:]) for food in (2, 1, 0)]  # full, half, empty


def was_closed(widget):
    """True once the widget has been in a window that is now closed (its timer then stops)."""
    if widget.get_root() is not None:
        widget._was_rooted = True
        return False
    return getattr(widget, "_was_rooted", False)


def sprite_size(sprite):
    return max(len(r) for r in sprite), len(sprite)


def hex_to_rgb(hexc):
    return int(hexc[1:3], 16) / 255, int(hexc[3:5], 16) / 255, int(hexc[5:7], 16) / 255


class TitleCat(Gtk.DrawingArea):
    def __init__(self, palette, forced=None, title=TITLE, font_px=22):
        super().__init__(hexpand=True, height_request=64 + font_px)
        self.title = title
        self.font_px = font_px
        self.palette = palette  # function returning the current colors (light/dark)
        self.forced = forced  # force a specific animation (for testing)
        self.mode = None  # set by the pomodoro panel while the timer runs
        self.x, self.dir = 0.0, 1
        self.t = 0.0
        self.last = time.monotonic()
        self.anim = None
        self.letters = []  # [x, width] per letter
        self.dy = [0.0] * len(title)  # letter offsets (spring physics)
        self.vy = [0.0] * len(title)
        self.cursor_y, self.cursor_vy = 0.0, 0.0  # the cursor can be swatted into the air
        self.ball_x = 0.0  # cursor x when it is the "ball" in play
        self.hop = {"from": 0.0, "to": 0.0, "t": 1.0}
        self.swat_at, self.swat_t = 0.0, -10.0
        self.happy_until = 0.0
        self.in_gap = False
        self.external = False  # True: the cat is drawn by CatOverlay (the layer above the window), not here
        self.away = False  # True: the cat is out on the window edge, the title has no cat
        self.top = 0
        self.speech, self.speech_until = "", 0.0
        self.prev_frame = -1

        self.set_draw_func(self.draw)
        GLib.timeout_add(1000 // FPS, self.tick, None, None)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_click)
        self.add_controller(click)

    # --- helpers ---
    def animation(self):
        if self.forced in ANIMATIONS + ["eat"]:
            return self.forced
        if self.mode:
            return self.mode
        now = datetime.now()
        if 0 <= self.minutes_into_lunch(now) < self.lunch_duration():
            return "eat"
        if now.hour >= 16 and (now.hour * 60 + now.minute) // SWITCH_MINUTES % 2 == 0:
            return "sleep"  # sleepy in the afternoon: sleeps every other quarter hour
        return ANIMATIONS[(now.hour * 60 + now.minute) // SWITCH_MINUTES % len(ANIMATIONS)]

    def layout(self, cr, text=None):
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription.from_string(f"Silkscreen {self.font_px}px"))
        text = self.title if text is None else text
        lay.set_text(text, -1)
        return lay

    def minutes_into_lunch(self, now):
        """Minutes since lunch started (negative before lunch)."""
        return now.hour * 60 + now.minute - LUNCH[0]

    def lunch_duration(self):
        return max(1, LUNCH[1] - LUNCH[0])

    def letter_index_at(self, x):
        for i, (lx, lw) in enumerate(self.letters):
            if lx <= x < lx + lw and self.title[i] != " ":
                return i
        return None

    def bounce_letter(self, x, strength):
        if (i := self.letter_index_at(x)) is not None:
            self.vy[i] += strength

    def walkable_range(self):
        """The range the cat can walk on (first to last letter)."""
        if not self.letters:
            return 0, 100
        return max(0, self.letters[0][0] - 4), self.letters[-1][0] + self.letters[-1][1] + 4

    # --- animation ---
    def tick(self, widget, clock):
        if was_closed(self):
            return False
        now = time.monotonic()
        dt, self.last = min(now - self.last, 0.05), now
        self.t += dt
        if not self.letters:
            self.queue_draw()
            return True
        anim = self.animation()
        if anim != self.anim or len(self.dy) != len(self.title):
            self.start(anim)
        lo, hi = self.walkable_range()
        cw = 20 * PX
        if anim == "climb" and not self.external:
            anim = "walk"

        if self.away:
            pass
        elif anim == "butterfly":
            self.butterfly_tick(dt, lo, hi, cw)
        elif anim in TRICKS:
            TRICKS[anim].tick(self, dt, lo, hi)
        elif anim in ("walk", "play") or self.is_stretch_walk(anim):
            speed = 70 if anim == "play" else 28
            if self.gap_jump_height(self.x + cw / 2) > 0:
                speed *= 2.5  # a quick hop over the gap, not a slow float
            self.x += self.dir * speed * dt
            if anim == "play":
                # The cursor flees ahead of the cat; at the end it pops up and the cat turns around
                self.ball_x += self.dir * speed * dt
                if (self.dir > 0 and self.ball_x > hi - 12) or (self.dir < 0 and self.ball_x < lo):
                    self.ball_x = max(lo, min(hi - 12, self.ball_x))
                    self.dir *= -1
                    self.cursor_vy = -140
                    self.ball_x = self.x + (cw + 6 if self.dir > 0 else -18)
                self.bounce_letter(self.ball_x + 6, 4)
            if self.x > hi - cw:
                self.x, self.dir = hi - cw, -1
            elif self.x < lo:
                self.x, self.dir = lo, 1
            # Hopping over gaps: the letter it lands on bounces
            arc = self.gap_jump_height(self.x + cw / 2)
            if self.in_gap and arc == 0:
                self.bounce_letter(self.x + cw / 2, 120)
            self.in_gap = arc > 0
            frame = int(self.t * (10 if anim == "play" else 6)) % 2
            if frame != self.prev_frame and not self.in_gap:
                # The paws push down the letter they step on
                self.bounce_letter(self.x + (6 if frame else cw - 8), 40 if anim == "play" else 25)
                self.prev_frame = frame
        elif anim == "jump":
            h = self.hop
            was_flying = h["t"] < 1
            h["t"] += dt / 0.6
            self.x = h["from"] + (h["to"] - h["from"]) * min(h["t"], 1)
            if was_flying and h["t"] >= 1:
                self.bounce_letter(self.x + cw / 2, 140)  # landing: the letter bounces
            if h["t"] >= 1.8:  # rested on the letter a bit, hop on
                target = self.next_jump_spot(lo, hi, cw)
                self.dir = 1 if target >= self.x else -1
                self.hop = {"from": self.x, "to": target, "t": 0.0}
        elif anim == "sleep":
            # The letters under the cat breathe along
            breath = (math.sin(self.t * 2 * math.pi / 2.4) + 1) * 0.8
            for i, (lx, lw) in enumerate(self.letters):
                if self.x <= lx + lw / 2 <= self.x + 18 * PX and self.vy[i] == 0:
                    self.dy[i] = breath
        elif anim == "eat":
            frame = int(self.t * 2.5) % 2
            if frame != self.prev_frame:
                # The bowl nudges the letter it stands on with each bite
                self.bounce_letter(self.x + 20 * PX, 18)
                self.prev_frame = frame
        elif anim == "sit" and self.t >= self.swat_at:
            # Swat the cursor
            self.swat_at = self.t + random.uniform(2.5, 4.5)
            self.swat_t = self.t
            self.cursor_vy = -170

        # Spring physics for the letters
        for i in range(len(self.dy)):
            if self.vy[i] == 0 and anim == "sleep":
                continue
            self.vy[i] += (-120 * self.dy[i] - 9 * self.vy[i]) * dt
            self.dy[i] += self.vy[i] * dt
            if abs(self.dy[i]) < 0.05 and abs(self.vy[i]) < 0.5:
                self.dy[i] = self.vy[i] = 0.0
        # Gravity for the cursor
        self.cursor_vy += 600 * dt
        self.cursor_y = min(0.0, self.cursor_y + self.cursor_vy * dt)
        if self.cursor_y == 0.0:
            self.cursor_vy = 0.0
        if now - getattr(self, "drawn_at", 0) >= 1 / (CALM_FPS if self.is_calm() else FPS) - 0.005:
            self.drawn_at = now
            self.queue_draw()
        return True

    def is_stretch_walk(self, anim):
        """stretch: 3 s stretching, then 5 s strolling, repeated."""
        return anim == "stretch" and (self.t % 8) >= 3

    def butterfly_tick(self, dt, lo, hi, cw):
        bf = self.bf
        # The butterfly flutters toward a point near the cat and picks a new one when it gets there
        step = 35 * dt
        bf["x"] += max(-step, min(step, bf["tx"] - bf["x"]))
        if abs(bf["tx"] - bf["x"]) < 1:
            bf["tx"] = random.uniform(max(lo, self.x - 70), min(hi, self.x + cw + 70))
        if self.t - self.pounce_t < 0.6:
            return  # mid-pounce
        if self.pounce_t and self.t - self.pounce_t < 0.65:
            self.bounce_letter(self.x + cw / 2, 120)  # landing
        target = bf["x"] - cw / 2
        if abs(target - self.x) > 2:
            self.dir = 1 if target > self.x else -1
            self.x = max(lo, min(hi - cw, self.x + self.dir * 40 * dt))
        low = math.sin(self.t * 2.2) > 0.4  # the butterfly is low right now
        if abs(target - self.x) < 12 and low and self.t - self.pounce_t > 1.6:
            self.pounce_t = self.t  # pounce!
            bf["tx"] = random.uniform(lo, hi)  # and it flies away

    def is_calm(self):
        """Is everything still enough for the lower frame rate?"""
        moving = (self.anim in ("walk", "play", "jump", "butterfly") or self.is_stretch_walk(self.anim)
                  or (self.anim in TRICKS and TRICKS[self.anim].moving)) and not self.away
        bouncing = any(self.vy) or self.cursor_y < 0 or self.t < self.speech_until + 0.3
        return not moving and not bouncing

    def start(self, anim):
        self.anim = anim
        lo, hi = self.walkable_range()
        cw = 20 * PX
        self.dy = [0.0] * len(self.title)
        self.vy = [0.0] * len(self.title)
        if anim == "sleep":
            # Middle of the last word (e.g. "morning")
            m = self.letters[self.title.rfind(" ") + 1:]
            self.x = (m[0][0] + m[-1][0] + m[-1][1]) / 2 - 9 * PX
            self.dir = 1
        elif anim == "sit":
            self.x, self.dir = hi - 13 * PX - 4, 1
            self.swat_at = self.t + 1.5
        elif anim == "play":
            self.x, self.dir = lo, 1
            self.ball_x = lo + cw + 30
        elif anim == "eat":
            self.x, self.dir = lo + 24, 1
        elif anim == "butterfly":
            self.x = max(lo, min(hi - cw, self.x))
            self.bf = {"x": self.x + cw + 30, "tx": self.x + cw + 60}
            self.pounce_t = 0.0
        elif anim == "jump":
            self.x = self.next_jump_spot(lo, hi, cw)
            self.hop = {"from": self.x, "to": self.x, "t": 1.0}
        elif anim in TRICKS:
            TRICKS[anim].start(self, lo, hi)
        else:
            self.x = max(lo, min(hi - cw, self.x))

    def word_gaps(self):
        """(left, right) edges of each gap between words in the title."""
        out = []
        for i, ch in enumerate(self.title):
            if ch == " " and 0 < i < len(self.title) - 1:
                left = self.letters[i - 1][0] + self.letters[i - 1][1]
                out.append((left, self.letters[i + 1][0]))
        return out

    def gap_jump_height(self, cx):
        """0..1: how high the cat is in a gap hop, given the x of its center."""
        reach = 6 * PX  # the hop starts/ends this far before/after the gap
        for left, right in self.word_gaps():
            a, b = left - reach, right + reach
            if a < cx < b:
                return math.sin(math.pi * (cx - a) / (b - a))
        return 0.0

    def next_jump_spot(self, lo, hi, cw):
        """The letter across the gap (D <-> M); without a gap, a random letter."""
        gap = self.title.find(" ")
        if gap > 0 and gap + 1 < len(self.title):
            spots = [self.letters[gap - 1], self.letters[gap + 1]]
            a, b = (max(lo, min(hi - cw, lx + lw / 2 - cw / 2)) for lx, lw in spots)
            return b if abs(self.x - a) < abs(self.x - b) else a
        spots = [lx + lw / 2 - cw / 2 for lx, lw in self.letters]
        spots = [t for t in spots if lo <= t <= hi - cw and abs(t - self.x) > 10]
        return random.choice(spots) if spots else self.x

    def on_click(self, gesture, n_press, x, y):
        # A wave through the letters and a small heart above the cat
        for i in range(len(self.vy)):
            self.vy[i] -= 70 + 50 * math.sin(i / 1.5)
        # Easter egg: 5 clicks on the cat within 2.5 s start "playtime"
        box = getattr(self, "cat_box", None)
        if box and not self.away and box[0] - 4 <= x <= box[0] + box[2] + 4 and box[1] - 4 <= y <= box[1] + box[3] + 4:
            now = time.monotonic()
            self.cat_clicks = [t for t in getattr(self, "cat_clicks", []) if now - t < 2.5] + [now]
            if len(self.cat_clicks) >= 5 and getattr(self, "on_playtime", None):
                self.cat_clicks = []
                self.on_playtime()
                return
        self.react_to("click")

    def say(self, text, seconds=2.0):
        if text:
            self.speech, self.speech_until = text, self.t + seconds
            self.speech_start = self.t
        self.happy_until = self.t + 1.6

    def react_to(self, event, seconds=2.0):
        """Say the phrase for an event (see EVENTS); an empty phrase just shows a heart."""
        self.say(random_phrase(event), seconds)

    # --- drawing ---
    def draw_sprite(self, cr, sprite, x, y, flip=False, colors=None, alpha=1.0):
        colors = colors or current_colors()
        used = {ch: colors[ch] for ch in set("".join(sprite)) if ch != "."}
        key = (tuple(sprite), flip, tuple(sorted(used.items())))
        surf = _SURFACES.get(key)
        if surf is None:
            if len(_SURFACES) > 400:  # e.g. after many color changes
                _SURFACES.clear()
            w, h = sprite_size(sprite)
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * PX, h * PX)
            sc = cairo.Context(surf)
            for row, line in enumerate(sprite):
                for col, ch in enumerate(line):
                    if ch != ".":
                        sc.set_source_rgb(*hex_to_rgb(used[ch]))
                        sc.rectangle(((w - 1 - col) if flip else col) * PX, row * PX, PX, PX)
                        sc.fill()
            _SURFACES[key] = surf
        cr.set_source_surface(surf, round(x), round(y))
        cr.get_source().set_filter(cairo.FILTER_NEAREST)  # crisp pixels even when the cat is rotated
        if alpha < 1:
            cr.paint_with_alpha(alpha)
        else:
            cr.paint()

    def letter_surface(self, cr, ch, color):
        """A title letter as a cached image (rendered once per letter and color)."""
        key = ("glyph", ch, color, self.font_px)
        surf = _SURFACES.get(key)
        if surf is None:
            lay = self.layout(cr, ch)
            _, log = lay.get_pixel_extents()
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, log.width + 2), max(1, log.height + 2))
            sc = cairo.Context(surf)
            sc.set_source_rgb(*hex_to_rgb(color))
            PangoCairo.show_layout(sc, self.layout(sc, ch))
            _SURFACES[key] = surf
        return surf

    def draw(self, area, cr, width, height):
        pal = self.palette()
        if getattr(self, "metrics_for", None) != (self.title, self.font_px):
            lay = self.layout(cr)
            self.ink, self.logical = lay.get_pixel_extents()
            # Letter positions (used by the physics)
            self.letters = []
            for i in range(len(self.title)):
                r = lay.index_to_pos(len(self.title[:i].encode()))
                self.letters.append([r.x / Pango.SCALE, r.width / Pango.SCALE])
            self.metrics_for = (self.title, self.font_px)
        ink, logical = self.ink, self.logical
        base_y = height - logical.height - 2
        top = base_y + ink.y  # top of the letters = the ground the cat stands on
        self.top = top

        if len(self.dy) != len(self.title):  # right after set_title
            self.dy = [0.0] * len(self.title)
            self.vy = [0.0] * len(self.title)

        # The title, letter by letter, each with its own offset
        for i, ch in enumerate(self.title):
            if ch != " ":
                cr.set_source_surface(self.letter_surface(cr, ch, pal["fg"]), self.letters[i][0], round(base_y + self.dy[i]))
                cr.paint()

        anim = self.anim
        if anim is None:
            return
        if self.away or (anim == "climb" and self.external):
            anim = None  # no cat on the title: the cursor blinks as usual
        elif anim == "climb":
            anim = "walk"

        # The "_" cursor
        end_x = self.letters[-1][0] + self.letters[-1][1] + 2
        cr.set_source_rgb(*hex_to_rgb(pal["accent"]))
        if anim == "eat":
            pass  # the cursor takes a lunch break
        elif anim == "play":
            # The cursor is the "ball" the cat chases along the letters
            cr.rectangle(self.ball_x, top - 4 + self.cursor_y, 12, 4)
            cr.fill()
        elif int(self.t / 0.55) % 2 == 0 or self.cursor_y < 0:
            cr.rectangle(end_x, base_y + ink.y + ink.height - 3 + self.cursor_y, 12, 3)
            cr.fill()

        if not self.external:
            self.draw_cat(cr, width)

    def draw_cat(self, cr, width):
        """The cat (with bowl, z's, bubble and heart) on the title, in title coordinates."""
        pal = self.palette()
        top = self.top
        anim = "walk" if self.anim == "climb" else self.anim
        if anim is None:
            return
        flip = self.dir < 0
        y_off = 0
        if anim in ("walk", "play") or self.is_stretch_walk(anim):
            arc = self.gap_jump_height(self.x + 10 * PX)
            if arc > 0.1:  # in the air over a gap
                sprite = SPRITES["run"][0]
                y_off = -arc * 18
            elif anim != "play":
                sprite = SPRITES["walk"][int(self.t * 6) % 2]
            else:
                sprite = SPRITES["run"][int(self.t * 10) % 2]
        elif anim == "sleep":
            sprite = SPRITES["sleep"][int(self.t / 1.2) % 2]
            for i in range(3):  # rising z's
                phase = (self.t / 3 + i / 3) % 1
                zx = self.x + 16 * PX + phase * 14
                zy = top - sprite_size(sprite)[1] * PX - 6 - phase * 26
                self.draw_sprite(cr, Z, zx, zy, colors={"e": pal["muted"]}, alpha=1 - phase)
        elif anim == "eat":
            sprite = SPRITES["eat"][int(self.t * 2.5) % 2]
        elif anim == "sit":
            swatting = self.t - self.swat_t < 0.25
            sprite = SPRITES["sit"][2 if swatting else int(self.t * 2) % 2]
        elif anim == "groom":
            # Grooms for 4 s, looks around for 2 s
            sprite = SPRITES["groom"][int(self.t * 3) % 2] if self.t % 6 < 4 else SPRITES["sit"][0]
        elif anim == "stretch":
            sprite = SPRITES["stretch"][int(self.t / 1.5) % 2]  # tail sways slowly
        elif anim == "butterfly":
            jump = self.t - self.pounce_t
            if jump < 0.6:
                sprite = SPRITES["run"][0]
                y_off = -math.sin(math.pi * jump / 0.6) * 26
            else:
                sprite = SPRITES["walk"][int(self.t * 6) % 2] if abs(self.bf["x"] - 10 * PX - self.x) > 3 else SPRITES["sit"][0]
            # The butterfly above the letters, flapping its wings
            by = top - 20 * PX - 4 + math.sin(self.t * 2.2) * 12
            self.draw_sprite(cr, BUTTERFLY_SPRITES[int(self.t * 8) % 2], self.bf["x"] - 7, by)
        elif anim in TRICKS:
            sprite, y_off = TRICKS[anim].draw(self, cr, top, pal)
        else:  # jump
            arc = math.sin(math.pi * min(self.hop["t"], 1))
            sprite = SPRITES["run"][0] if arc > 0.2 else SPRITES["walk"][0]
            y_off = -arc * 30

        # Blink now and then (not while asleep), and yawn in the morning
        if anim != "sleep" and datetime.now().hour < 9 and self.t % 20 < 1.2:
            sprite = yawning_sprite(sprite)
        elif anim != "sleep" and (self.t % 4.2) < 0.12:
            sprite = [r.replace("e", "b") for r in sprite]
        trick = TRICKS.get(anim)
        if not trick or trick.accessories:
            sprite = add_accessories(sprite)

        cat_y = top - sprite_size(sprite)[1] * PX + PX + y_off  # the bottom outline rests on the letters
        if trick and trick.clip_below_letters:
            cr.save()
            cr.rectangle(-1000, -1000, 4000, top + 1000)  # e.g. the cat sinking into its box
            cr.clip()
        self.draw_sprite(cr, sprite, self.x, cat_y, flip)
        if trick and trick.clip_below_letters:
            cr.restore()
        if trick:
            trick.draw_front(self, cr, top, pal, cat_y)
        if "coffee" in worn_accessories() and anim in ("sit", "groom", "sleep", "stretch") and not self.is_stretch_walk(anim):
            # Coffee cup next to the cat, with a little steam
            cx = self.x - 7 * PX if flip else self.x + sprite_size(sprite)[0] * PX + 2
            self.draw_sprite(cr, add_outline(CUP), cx, top - (len(CUP) + 2) * PX + PX)
            for i in range(2):
                phase = (self.t / 2 + i / 2) % 1
                cr.set_source_rgba(*hex_to_rgb(pal["muted"]), 1 - phase)
                cr.rectangle(round(cx + 3 * PX + math.sin(phase * 6 + i) * 3), round(top - 8 * PX - phase * 14), PX, PX)
                cr.fill()
        self.cat_box = (self.x, cat_y, sprite_size(sprite)[0] * PX, sprite_size(sprite)[1] * PX)  # for clicks on the cat

        if anim == "eat":
            # Bowl in front of the head (drawn on top so the head looks dipped in it).
            # part = progress through lunch (0-1); the food shrinks in three steps
            if self.forced == "eat" or self.mode == "eat":
                part = (self.t / 15) % 1  # testing or a long pomodoro break: not tied to lunch time
            else:
                part = self.minutes_into_lunch(datetime.now()) / self.lunch_duration()
            bowl = BOWLS[max(0, min(2, int(part * 3)))]
            bx = self.x + 16 * PX
            self.draw_sprite(cr, bowl, bx, top - sprite_size(bowl)[1] * PX + PX)
            # A "nom" rising now and then
            phase = (self.t % 2.2) / 2.2
            if part < 2 / 3 and phase < 0.7:  # no "nom" once the bowl is empty
                cr.set_source_rgba(*hex_to_rgb(pal["muted"]), 1 - phase / 0.7)
                cr.move_to(bx + 22 + phase * 8, top - 30 - phase * 18)
                nom = self.layout(cr, _("nom"))
                nom.set_font_description(Pango.FontDescription.from_string("Silkscreen 8px"))
                PangoCairo.show_layout(cr, nom)

        if self.t < self.speech_until:
            self.draw_speech_bubble(cr, pal, width, self.x + sprite_size(sprite)[0] * PX / 2, cat_y - 4)
        elif self.t < self.happy_until:
            rise = (1 - (self.happy_until - self.t) / 1.6) * 14
            self.draw_sprite(cr, HEART, self.x + sprite_size(sprite)[0] * PX / 2 - 5, cat_y - 14 - rise)

    def draw_speech_bubble(self, cr, pal, width, cx, bottom):
        """Pixel speech bubble with a tail pointing down at the cat."""
        lay = self.layout(cr, self.speech)
        lay.set_font_description(Pango.FontDescription.from_string("Silkscreen 8px"))
        _, log = lay.get_pixel_extents()
        w, h = log.width + 10, log.height + 6
        x = round(max(1, min(width - w - 1, cx - w / 2)))
        y = round(max(1, bottom - h - 4))
        # Small "pop" when the bubble appears (timed from its start, so long bubbles work too)
        pop = max(0.05, min(1.0, (self.t - getattr(self, "speech_start", self.t - 1)) / 0.12))
        cr.save()
        cr.translate(x + w / 2, y + h)
        cr.scale(pop, pop)
        cr.translate(-(x + w / 2), -(y + h))
        cr.set_source_rgb(*hex_to_rgb(pal["fg"]))
        cr.rectangle(x, y, w, h)
        cr.fill()
        tail = round(max(x + 3, min(x + w - 7, cx - 2)))
        for i in range(3):  # stair-step tail
            cr.rectangle(tail + i, y + h + i, 4 - i, 1 * 2)
        cr.fill()
        cr.set_source_rgb(*hex_to_rgb(pal["bg"]))
        cr.move_to(x + 5, y + 3)
        PangoCairo.show_layout(cr, lay)
        cr.restore()


class CatOverlay(Gtk.DrawingArea):
    """Transparent layer over the whole window that draws the cat.

    The canvas is only a small square (BOX) that the overlay positions where the cat is
    (get-child-position), so GTK redraws just that square instead of the whole window. The frame the
    cat walks around is the overlay's size, i.e. the visible content; the square can never enlarge it.

    On the title the cat is drawn where the title is (TitleCat drives the animation). If the title is
    scrolled out of view, or the animation is "climb", the cat walks around the inside of the window
    edge: bottom, up the right wall, upside down along the top, down the left wall. When the title is
    visible again, it hops back.
    """

    SPEED = 40  # pixels per second along the frame
    EDGE = 1  # distance from the edge to the paws
    HALF = 11 * PX  # half the cat's length: it turns at a corner when its nose reaches the wall, so nothing sticks out
    BOX = 160  # canvas size around the cat (room for bubble, bowl and z's)

    def __init__(self, title, overlay):
        super().__init__(can_target=False)
        self.overlay = overlay
        self.set_draw_func(self.draw_canvas)
        overlay.add_overlay(self)
        overlay.connect("get-child-position", self.place_canvas)
        self.origin = (0, 0)
        # "playtime" easter egg: the cat pounces after the mouse pointer
        self.pointer = None  # (x, y) in the overlay, None when the pointer is outside
        self.pointer_left = 0.0
        self.play_until = 0.0
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _, x, y: setattr(self, "pointer", (x, y)))
        motion.connect("leave", self.on_pointer_leave)
        overlay.add_controller(motion)
        title.on_playtime = self.start_playtime
        self.title = title
        title.external = True
        self.mode = "title"  # title | frame | hop | playtime
        self.s, self.d = 0.0, 1  # position along the frame and direction
        self.hop = None
        self.enter = 0.0  # pixels the cat is still above the top edge while climbing into the frame
        self.last = time.monotonic()
        GLib.timeout_add(1000 // FPS, self.tick, None, None)

    def place_canvas(self, overlay, widget, rect):
        if widget is not self:
            return False
        rect.x, rect.y = self.origin
        rect.width = rect.height = self.BOX
        return True

    # The frame is the overlay (the visible content), not this small canvas
    def area_width(self):
        return self.overlay.get_width()

    def area_height(self):
        return self.overlay.get_height()

    # --- playtime ---
    def on_pointer_leave(self, _):
        self.pointer = None
        self.pointer_left = time.monotonic()

    def start_playtime(self):
        now = time.monotonic()
        self.play_until = now + PLAYTIME_SECONDS
        self.play_wait, self.play_catches = 0.0, 0
        self.title.away = True
        self.title.say(_(random.choice(["playtime!", "mrrrow!", "let's play!"])), 2)
        x, y = self.paw_position()
        angle = self.pose_on_frame(self.s)[2] if self.mode == "frame" else 0.0
        self.enter = 0.0
        self.start_hop((x, y, angle), (x, y, 0.0), "playtime")  # a small hop in place to start the chase

    def playtime_landing_spot(self):
        """Where the cat will land: at the pointer, but inside the window."""
        px, py = self.pointer
        return (max(self.HALF, min(self.area_width() - self.HALF, px)),
                max(17 * PX, min(self.area_height() - 1, py)))

    def playtime_tick(self, dt, now, tx, ty, visible):
        x, y = self.pt
        gone = self.pointer is None and now - self.pointer_left > 4
        if now > self.play_until or gone:
            # Playtime over: back to the title, or out to the frame if the title is scrolled away
            self.play_until = 0.0
            if visible:
                self.start_hop((x, y, 0.0), (tx, ty, 0.0), "title")
            else:
                self.s, self.d = 0.0, 1
                self.start_hop((x, y, 0.0), self.pose_on_frame(0.0), "frame")
            return
        self.play_wait -= dt
        if self.play_wait <= 0 and self.pointer:
            gx, gy = self.playtime_landing_spot()
            if math.hypot(gx - x, gy - y) > 14:
                self.pt_flip = gx < x
                self.start_hop((x, y, 0.0), (gx, gy, 0.0), "playtime")

    # --- geometry ---
    def frame_edges(self):
        """Walkable length of each edge (the cat's center stays half a cat away from the corners)."""
        w, h, m = self.area_width(), self.area_height(), self.EDGE
        return max(1, w - 2 * m - 2 * self.HALF), max(1, h - 2 * m - 2 * self.HALF), m

    def perimeter(self):
        iw, ih, _ = self.frame_edges()
        return 2 * (iw + ih)

    def pose_on_frame(self, s):
        """(x, y, angle) of the paws at position s along the frame. The angle points the cat's "down" at the edge."""
        iw, ih, m = self.frame_edges()
        w, h, e = self.area_width(), self.area_height(), self.HALF
        s %= max(1.0, self.perimeter())
        if s < iw:
            return m + e + s, h - m, 0.0  # bottom, walking right
        s -= iw
        if s < ih:
            return w - m, h - m - e - s, -math.pi / 2  # right wall, climbing up
        s -= ih
        if s < iw:
            return w - m - e - s, m, math.pi  # top, upside down going left
        s -= iw
        return m, m + e + s, math.pi / 2  # left wall, climbing down

    def pose_on_title(self):
        """(x, y, visible) of the cat's paws on the title, in overlay coordinates."""
        ok, p = self.title.compute_point(self.overlay, Graphene.Point())
        if not ok:
            return 0, 0, False
        x = p.x + self.title.x + 10 * PX
        y = p.y + self.title.top + PX
        visible = y - 17 * PX >= 0 and y <= self.area_height()  # the whole cat must fit
        return x, y, visible

    # --- animation ---
    def tick(self, widget, clock):
        if was_closed(self):
            return False
        now = time.monotonic()
        dt, self.last = min(now - self.last, 0.05), now
        if self.area_width() == 0:
            return True
        tx, ty, visible = self.pose_on_title()
        if self.mode == "playtime":
            self.playtime_tick(dt, now, tx, ty, visible)
            tx, ty, visible = self.pose_on_title()
        climbing = self.title.animation() == "climb"
        want_frame = not visible or climbing
        iw, ih, m = self.frame_edges()

        if self.mode == "playtime":
            pass  # driven by playtime_tick; its hops go through "hop" below
        elif self.mode == "title" and want_frame:
            self.title.away = True
            if not visible:
                # Title scrolled away: the cat climbs down into the frame from above, along the nearest wall
                if tx < self.area_width() / 2:
                    self.s, self.d = 2 * iw + ih, 1  # top of the left wall, heading down
                else:
                    self.s, self.d = iw + ih, -1  # top of the right wall, heading down
                self.enter = 22 * PX  # starts fully above the edge and climbs down into view
                self.mode = "frame"
            else:
                # climb: hop from the title onto the nearest side wall
                if tx < self.area_width() / 2:
                    s, d = 2 * iw + ih + max(0, ty - m), 1
                else:
                    s, d = iw + (ih - max(0, ty - m)), -1
                self.enter = 0.0  # may be left over from an interrupted climb-in
                self.start_hop((tx, ty, 0.0), self.pose_on_frame(s), "frame")
                self.s, self.d = s, d
        elif self.mode == "frame":
            if self.enter > 0:
                self.enter = max(0.0, self.enter - self.SPEED * dt)
            else:
                self.s = (self.s + self.d * self.SPEED * dt) % max(1.0, self.perimeter())
            if not want_frame:
                x, y = self.paw_position()  # where the cat actually is (also mid climb-in)
                self.start_hop((x, y, self.pose_on_frame(self.s)[2]), (tx, ty, 0.0), "title")
                self.enter = 0.0
        elif self.mode == "hop":
            self.hop["t"] += dt / 0.7
            if self.hop["then"] == "title":
                self.hop["to"] = (tx, ty, 0.0)  # the title may have moved while the cat was in the air
            if self.hop["t"] >= 1:
                self.mode = self.hop["then"]
                if self.mode == "playtime":
                    self.pt = self.hop["to"][:2]
                    self.play_wait = 0.25
                    if self.pointer and math.hypot(*(a - b for a, b in zip(self.playtime_landing_spot(), self.pt))) < 20:
                        self.play_catches += 1  # landed on the pointer
                        self.play_wait = 0.8
                        if self.play_catches % 3 == 1:
                            self.title.say(_(random.choice(["got it!", "pounce!", "mrrp!", "gotcha!"])), 1.2)
                if self.mode == "title":
                    self.title.away = False
                    self.title.bounce_letter(self.title.x + 10 * PX, 120)  # landing on the letters
        calm = self.mode == "title" and self.title.is_calm()
        if now - getattr(self, "drawn_at", 0) >= 1 / (CALM_FPS if calm else FPS) - 0.005:
            self.drawn_at = now
            # Move the small canvas to the cat (paws a bit below center, leaving room for the bubble above)
            ax, ay = self.paw_position()
            origin = (round(ax - self.BOX / 2), round(ay - self.BOX * 0.62))
            if origin != self.origin:
                self.origin = origin
                self.overlay.queue_allocate()  # moves the square (see place_canvas)
            self.queue_draw()
        return True

    def paw_position(self):
        """The cat's paws in overlay coordinates, in any mode."""
        if self.mode == "title":
            x, y, _ = self.pose_on_title()
            return x, y
        if self.mode == "frame":
            x, y, _ = self.pose_on_frame(self.s)
            return x, y - self.enter
        if self.mode == "playtime":
            return self.pt
        e = min(self.hop["t"], 1)
        (x0, y0, _), (x1, y1, _) = self.hop["from"], self.hop["to"]
        return x0 + (x1 - x0) * e, y0 + (y1 - y0) * e - math.sin(math.pi * e) * self.hop_height(y0, y1)

    def draw_canvas(self, area, cr, width, height):
        cr.translate(-self.origin[0], -self.origin[1])
        self.draw(area, cr, self.area_width(), self.area_height())

    def hop_height(self, y0, y1):
        """Hop height: 40 px, but never so high that the cat disappears above the top edge."""
        return max(0.0, min(40.0, min(y0, y1) - 17 * PX))

    def start_hop(self, frm, to, then):
        self.hop = {"from": frm, "to": to, "then": then, "t": 0.0}
        self.mode = "hop"

    # --- drawing ---
    def draw(self, area, cr, width, height):
        title = self.title
        if self.mode == "title":
            tx, ty, _ = self.pose_on_title()
            ok, p = title.compute_point(self.overlay, Graphene.Point())
            cr.save()
            cr.translate(p.x, p.y)
            title.draw_cat(cr, title.get_width())
            cr.restore()
            return

        if self.mode == "frame":
            x, y, angle = self.pose_on_frame(self.s)
            y -= self.enter
            sprite = SPRITES["walk"][int(title.t * 6) % 2]
            flip = self.d < 0
        elif self.mode == "playtime":
            # Sits ready and watches the pointer between hops
            (x, y), angle = self.pt, 0.0
            if self.pointer:
                self.pt_flip = self.pointer[0] < x
            sprite = SPRITES["sit"][int(title.t * 3) % 2]
            flip = getattr(self, "pt_flip", False)
        else:  # hop
            h = self.hop
            e = min(h["t"], 1)
            (x0, y0, a0), (x1, y1, a1) = h["from"], h["to"]
            x = x0 + (x1 - x0) * e
            y = y0 + (y1 - y0) * e - math.sin(math.pi * e) * self.hop_height(y0, y1)
            angle = a0 if e < 0.5 else a1
            sprite = SPRITES["run"][0]
            flip = x1 < x0
        if (title.t % 4.2) < 0.12:  # blink
            sprite = [r.replace("e", "b") for r in sprite]
        sprite = add_accessories(sprite)

        sw, sh = sprite_size(sprite)
        cr.save()
        cr.translate(x, y)
        cr.rotate(angle)
        title.draw_sprite(cr, sprite, -sw * PX / 2, -sh * PX + PX, flip)
        cr.restore()

        # Bubble/heart above the head, always upright
        hx = x + math.sin(angle) * sh * PX * 0.6
        hy = y - math.cos(angle) * sh * PX * 0.6
        pal = title.palette()
        if title.t < title.speech_until:
            title.draw_speech_bubble(cr, pal, width, hx, max(30, hy - 8))
        elif title.t < title.happy_until:
            rise = (1 - (title.happy_until - title.t) / 1.6) * 14
            title.draw_sprite(cr, HEART, hx - 5, max(2, hy - 20 - rise))


import cat_tricks  # noqa: E402,F401  (registers the extra animations in TRICKS and ANIMATIONS)
