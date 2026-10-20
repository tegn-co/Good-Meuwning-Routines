"""Tittelen «good morning» med en animert pixel-katt som lever oppå bokstavene.

Fem animasjoner som byttes hvert 15. minutt:
  walk  – går fram og tilbake på bokstavene, som dukker litt under potene
          (over hvert mellomrom mellom ord tar den et hopp, i alle animasjoner som går)
  play  – markøren «_» hopper opp på tittelen og katten jager den bortover
  sleep – sover krøllet sammen oppå «morning», bokstavene puster med
  sit   – sitter ved enden og slår til markøren så den flyr opp
  jump  – hopper fram og tilbake over mellomrommet (mellom D og M i «good morning»),
          og bokstaven den lander på spretter
I lunsjtimen (standard 11–12, endres under ⚙ → schedule) spiser katten (eat) fra en skål oppå tittelen, og maten
minker utover timen.
  climb – hopper ut på vinduskanten og klatrer rundt rammen (se CatRoamer)
Klikk på tittelen: bokstavene tar en bølge og katten blir glad (♥).
Scrolles tittelen ut av syne, klatrer katten ned i rammen og går rundt der til tittelen er tilbake.
say(tekst): katten sier noe i en snakkeboble (f.eks. «good job!» når noe krysses av).

Sprites tegnes som fyll (b = pels, s = stripe, w = hvit, p = rosa, e = øye, . = tomt),
og konturen legges på automatisk. Alle ser mot høyre.
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

from db import CONFIG_DIR  # noqa: E402  (samme innstillingsmappe som resten av appen, følger XDG_CONFIG_HOME)

PX = 2  # skjermpiksler per sprite-piksel
FPS = 24  # oppdateringer i sekundet når katten beveger seg (jevnt nok for pikselgrafikk)
CALM_FPS = 8  # når den sover, sitter eller spiser og ingen bokstaver spretter
# En vanlig GLib-timer i stedet for add_tick_callback: tick-callback holder GTKs bildeklokke på 60 Hz
# med full layout hele tiden, og det alene kostet 15–25 % CPU.
_SURFACES = {}  # ferdigtegnede sprites/bokstaver, så hvert bilde bare limes inn i stedet for å tegnes piksel for piksel
SWITCH_MINUTES = 15
ANIMATIONS = ["walk", "play", "sleep", "sit", "jump", "climb"]
LUNCH = (11 * 60, 12 * 60)  # lunsj fra–til i minutter etter midnatt (settes fra ⚙ → schedule)
TITLE = "good morning"  # standardtittel; TitleCat(title=...) kan bruke en annen
# --- Utseende og replikker (kan endres i katteinnstillingene, lagres i CAT_FILE) ---
CAT_FILE = CONFIG_DIR / "cat.json"
# Delene av katten som kan farges: nøkkel i spritene, navn i innstillingene
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
# Raser med egen form (resten bruker standardformen): fluffy = øredusker og tykk hale
BREED_SHAPES = {"maine coon": "fluffy"}
# Det katten sier; flere alternativer skilles med | og velges tilfeldig. Tom = sier ingenting
EVENTS = [
    ("check", "you check something off"),
    ("all_done", "the whole list is done"),
    ("click", "you click the title"),
    ("start", "a focus session starts"),
    ("break", "time for a break"),
    ("focus", "the break is over"),
]
PHRASES = {"check": "good job!", "all_done": "all done!", "click": "",
           "start": "let's go!", "break": "break time!", "focus": "focus time!"}
DEFAULT_PHRASES = dict(PHRASES)

COLORS = dict(BREEDS["orange tabby"], c="#5aa9e6", f="#9a5b2e")  # c/f = matskåla
SETTINGS = {"breed": "orange tabby", "shape": "normal"}  # shape beholdes når fargene tilpasses («custom»)


def load_cat_settings():
    try:
        data = json.loads(CAT_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    SETTINGS["breed"] = data.get("breed", "orange tabby")
    SETTINGS["shape"] = data.get("shape", BREED_SHAPES.get(SETTINGS["breed"], "normal"))
    COLORS.update(BREEDS.get(SETTINGS["breed"], BREEDS["orange tabby"]))
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
        }, indent=2))
    except OSError:
        pass


def phrase(event):
    """En tilfeldig replikk for hendelsen, eller "" hvis katten skal være stille."""
    options = [p.strip() for p in PHRASES.get(event, "").split("|") if p.strip()]
    return random.choice(options) if options else ""


load_cat_settings()


def _walker(legs):
    """Sidekropp med hale til venstre, hode som ser rett fram til høyre, og to rader bein."""
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
        _walker(["..bb.bb....bb.bb..", "..ww.ww....ww.ww.."]),
        _walker([".bb...bb...bb..bb.", ".ww...ww...ww..ww."]),
    ],
    "run": [
        _walker([".bb...........bb..", "ww.............ww."]),
        _walker(["....bbb....bbb....", "....ww......ww...."]),
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
        [  # slår med labben
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
    [  # hodet nede i skåla, fornøyde lukkede øyne
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
    [  # løfter hodet litt og tygger
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
# Matskål med 2, 1 eller 0 rader mat
# Lukkede øyne i søvn: øynene blir en mørk strek
FILL["sleep"] = [[r.replace("e", "o") for r in f] for f in FILL["sleep"]]
HEART = [".p.p.", "ppppp", "ppppp", ".ppp.", "..p.."]
Z = ["eee", "..e", ".e.", "e..", "eee"]


def outline(fill):
    """Legg en 1 piksel mørk kontur rundt fyllet."""
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


def fluffy(fill):
    """Maine Coon-form: høye, mørke dusker på øretuppene og en dobbelt så tykk hale."""
    rows = list(fill)
    # Halen: rader som starter med en enkelt pelspiksel helt til venstre får en piksel til
    for i, r in enumerate(rows):
        j = len(r) - len(r.lstrip("."))
        if r.strip() and j <= 1 and r[j] == "b" and j + 1 < len(r) and r[j + 1] == ".":
            rows[i] = r[: j + 1] + "b" + r[j + 2:]
    # Øredusker: en mørk piksel over hver øretupp på øverste rad med ører («p» = innsiden av øret på raden under)
    ear_row = next(i for i, r in enumerate(rows) if i + 1 < len(rows) and "p" in rows[i + 1])
    tips = rows[ear_row]
    tuft = "".join("s" if ch == "b" and tips[max(0, k - 1):k + 2].count("b") == 1 else "." for k, ch in enumerate(tips))
    # To piksler høye dusker; mangler det rader over ørene, legges de til øverst
    for _ in range(max(0, 2 - ear_row)):
        rows.insert(0, "")
        ear_row += 1
    for r in (ear_row - 1, ear_row - 2):
        above = rows[r].ljust(len(tuft), ".")
        rows[r] = "".join(t if t != "." else a for t, a in zip(tuft, above))
    return rows


SHAPES = {"normal": lambda f: f, "fluffy": fluffy}
SPRITES = {}


def set_shape(shape):
    """Bygg spritene for en form (endrer SPRITES på stedet, så katten bruker dem med en gang)."""
    SETTINGS["shape"] = shape if shape in SHAPES else "normal"
    SPRITES.update({name: [outline(SHAPES[SETTINGS["shape"]](f)) for f in frames] for name, frames in FILL.items()})


set_shape(SETTINGS["shape"])
_BOWL = ["..ffffff..", ".ffffffff.", "cccccccccc", ".cccccccc.", "..cccccc.."]
BOWLS = [outline(_BOWL[2 - food:]) for food in (2, 1, 0)]  # full, halv, tom


def detached(widget):
    """True når widgeten har vært i et vindu som nå er lukket (da stopper timeren dens)."""
    if widget.get_root() is not None:
        widget._was_rooted = True
        return False
    return getattr(widget, "_was_rooted", False)


def size(sprite):
    return max(len(r) for r in sprite), len(sprite)


def rgb(hexc):
    return int(hexc[1:3], 16) / 255, int(hexc[3:5], 16) / 255, int(hexc[5:7], 16) / 255


class TitleCat(Gtk.DrawingArea):
    def __init__(self, palette, forced=None, title=TITLE, font_px=22):
        super().__init__(hexpand=True, height_request=64 + font_px)
        self.title = title
        self.font_px = font_px
        self.palette = palette  # funksjon som gir dagens farger (lys/mørk)
        self.forced = forced  # tving en bestemt animasjon (for testing)
        self.mode = None  # settes av pomodoro-panelet mens klokka går
        self.x, self.dir = 0.0, 1
        self.t = 0.0
        self.last = time.monotonic()
        self.anim = None
        self.letters = []  # [x, bredde] per bokstav
        self.dy = [0.0] * len(title)  # bokstavenes forskyvning (fjær)
        self.vy = [0.0] * len(title)
        self.cursor_y, self.cursor_vy = 0.0, 0.0  # markøren kan slås opp i lufta
        self.ball_x = 0.0  # markørens x når den er "ball" i play
        self.hop = {"from": 0.0, "to": 0.0, "t": 1.0}
        self.swat_at, self.swat_t = 0.0, -10.0
        self.happy_until = 0.0
        self.in_gap = False
        self.external = False  # True: katten tegnes av CatRoamer (laget over vinduet), ikke her
        self.away = False  # True: katten er ute på vinduskanten, tittelen står uten katt
        self.top = 0
        self.speech, self.speech_until = "", 0.0
        self.prev_frame = -1

        self.set_draw_func(self.draw)
        GLib.timeout_add(1000 // FPS, self.tick, None, None)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_click)
        self.add_controller(click)

    # --- hjelpere ---
    def animation(self):
        if self.forced in ANIMATIONS + ["eat"]:
            return self.forced
        if self.mode:
            return self.mode
        now = datetime.now()
        if 0 <= self.lunch_minute(now) < self.lunch_length():
            return "eat"
        return ANIMATIONS[(now.hour * 60 + now.minute) // SWITCH_MINUTES % len(ANIMATIONS)]

    def layout(self, cr, text=None):
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription.from_string(f"Silkscreen {self.font_px}px"))
        text = self.title if text is None else text
        lay.set_text(text, -1)
        return lay

    def lunch_minute(self, now):
        """Minutter siden lunsjen startet (negativt før lunsj)."""
        return now.hour * 60 + now.minute - LUNCH[0]

    def lunch_length(self):
        return max(1, LUNCH[1] - LUNCH[0])

    def letter_at(self, x):
        for i, (lx, lw) in enumerate(self.letters):
            if lx <= x < lx + lw and self.title[i] != " ":
                return i
        return None

    def kick(self, x, strength):
        if (i := self.letter_at(x)) is not None:
            self.vy[i] += strength

    def span(self):
        """Området katten kan gå på (fra første til siste bokstav)."""
        if not self.letters:
            return 0, 100
        return max(0, self.letters[0][0] - 4), self.letters[-1][0] + self.letters[-1][1] + 4

    # --- animasjon ---
    def tick(self, widget, clock):
        if detached(self):
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
        lo, hi = self.span()
        cw = 20 * PX
        if anim == "climb" and not self.external:
            anim = "walk"

        if self.away:
            pass
        elif anim in ("walk", "play"):
            speed = 28 if anim == "walk" else 70
            if self.gap_arc(self.x + cw / 2) > 0:
                speed *= 2.5  # et raskt sprett over mellomrommet, ikke et langsomt svev
            self.x += self.dir * speed * dt
            if anim == "play":
                # Markøren flykter foran katten; når den når enden, spretter den opp og katten snur
                self.ball_x += self.dir * speed * dt
                if (self.dir > 0 and self.ball_x > hi - 12) or (self.dir < 0 and self.ball_x < lo):
                    self.ball_x = max(lo, min(hi - 12, self.ball_x))
                    self.dir *= -1
                    self.cursor_vy = -140
                    self.ball_x = self.x + (cw + 6 if self.dir > 0 else -18)
                self.kick(self.ball_x + 6, 4)
            if self.x > hi - cw:
                self.x, self.dir = hi - cw, -1
            elif self.x < lo:
                self.x, self.dir = lo, 1
            # Hopp over mellomrom: bokstaven den lander på spretter
            arc = self.gap_arc(self.x + cw / 2)
            if self.in_gap and arc == 0:
                self.kick(self.x + cw / 2, 120)
            self.in_gap = arc > 0
            frame = int(self.t * (6 if anim == "walk" else 10)) % 2
            if frame != self.prev_frame and not self.in_gap:
                # Potene trykker ned bokstaven de tråkker på
                self.kick(self.x + (6 if frame else cw - 8), 25 if anim == "walk" else 40)
                self.prev_frame = frame
        elif anim == "jump":
            h = self.hop
            was_flying = h["t"] < 1
            h["t"] += dt / 0.6
            self.x = h["from"] + (h["to"] - h["from"]) * min(h["t"], 1)
            if was_flying and h["t"] >= 1:
                self.kick(self.x + cw / 2, 140)  # landing: bokstaven spretter
            if h["t"] >= 1.8:  # hvilt litt på bokstaven, hopp videre
                target = self.jump_target(lo, hi, cw)
                self.dir = 1 if target >= self.x else -1
                self.hop = {"from": self.x, "to": target, "t": 0.0}
        elif anim == "sleep":
            # Bokstavene under katten puster med
            breath = (math.sin(self.t * 2 * math.pi / 2.4) + 1) * 0.8
            for i, (lx, lw) in enumerate(self.letters):
                if self.x <= lx + lw / 2 <= self.x + 18 * PX and self.vy[i] == 0:
                    self.dy[i] = breath
        elif anim == "eat":
            frame = int(self.t * 2.5) % 2
            if frame != self.prev_frame:
                # Skåla dytter litt på bokstaven den står på for hver bit
                self.kick(self.x + 20 * PX, 18)
                self.prev_frame = frame
        elif anim == "sit" and self.t >= self.swat_at:
            # Slå til markøren
            self.swat_at = self.t + random.uniform(2.5, 4.5)
            self.swat_t = self.t
            self.cursor_vy = -170

        # Fjærfysikk for bokstavene
        for i in range(len(self.dy)):
            if self.vy[i] == 0 and anim == "sleep":
                continue
            self.vy[i] += (-120 * self.dy[i] - 9 * self.vy[i]) * dt
            self.dy[i] += self.vy[i] * dt
            if abs(self.dy[i]) < 0.05 and abs(self.vy[i]) < 0.5:
                self.dy[i] = self.vy[i] = 0.0
        # Tyngdekraft for markøren
        self.cursor_vy += 600 * dt
        self.cursor_y = min(0.0, self.cursor_y + self.cursor_vy * dt)
        if self.cursor_y == 0.0:
            self.cursor_vy = 0.0
        if now - getattr(self, "drawn_at", 0) >= 1 / (CALM_FPS if self.calm() else FPS) - 0.005:
            self.drawn_at = now
            self.queue_draw()
        return True

    def calm(self):
        """Står alt stille nok til at færre bilder i sekundet holder?"""
        moving = self.anim in ("walk", "play", "jump") and not self.away
        bouncing = any(self.vy) or self.cursor_y < 0 or self.t < self.speech_until + 0.3
        return not moving and not bouncing

    def start(self, anim):
        self.anim = anim
        lo, hi = self.span()
        cw = 20 * PX
        self.dy = [0.0] * len(self.title)
        self.vy = [0.0] * len(self.title)
        if anim == "sleep":
            # Midt på siste ord (f.eks. «morning»)
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
        elif anim == "jump":
            self.x = self.jump_target(lo, hi, cw)
            self.hop = {"from": self.x, "to": self.x, "t": 1.0}
        else:
            self.x = max(lo, min(hi - cw, self.x))

    def gaps(self):
        """(venstre, høyre) kant for hvert mellomrom mellom ord i tittelen."""
        out = []
        for i, ch in enumerate(self.title):
            if ch == " " and 0 < i < len(self.title) - 1:
                left = self.letters[i - 1][0] + self.letters[i - 1][1]
                out.append((left, self.letters[i + 1][0]))
        return out

    def gap_arc(self, cx):
        """0..1: hvor høyt katten er i hoppet over et mellomrom, ut fra hvor midten av katten er."""
        reach = 6 * PX  # hoppet starter/slutter så langt før/etter mellomrommet
        for left, right in self.gaps():
            a, b = left - reach, right + reach
            if a < cx < b:
                return math.sin(math.pi * (cx - a) / (b - a))
        return 0.0

    def jump_target(self, lo, hi, cw):
        """Bokstaven på andre siden av mellomrommet (D <-> M); uten mellomrom: en tilfeldig bokstav."""
        gap = self.title.find(" ")
        if gap > 0 and gap + 1 < len(self.title):
            spots = [self.letters[gap - 1], self.letters[gap + 1]]
            a, b = (max(lo, min(hi - cw, lx + lw / 2 - cw / 2)) for lx, lw in spots)
            return b if abs(self.x - a) < abs(self.x - b) else a
        spots = [lx + lw / 2 - cw / 2 for lx, lw in self.letters]
        spots = [t for t in spots if lo <= t <= hi - cw and abs(t - self.x) > 10]
        return random.choice(spots) if spots else self.x

    def on_click(self, *_):
        # Bølge gjennom bokstavene og et lite hjerte over katten
        for i in range(len(self.vy)):
            self.vy[i] -= 70 + 50 * math.sin(i / 1.5)
        self.react("click")

    def say(self, text, seconds=2.0):
        if text:
            self.speech, self.speech_until = text, self.t + seconds
        self.happy_until = self.t + 1.6

    def react(self, event, seconds=2.0):
        """Si replikken for en hendelse (se EVENTS); tom replikk gir bare et hjerte."""
        self.say(phrase(event), seconds)

    # --- tegning ---
    def blit(self, cr, sprite, x, y, flip=False, colors=COLORS, alpha=1.0):
        used = {ch: colors[ch] for ch in set("".join(sprite)) if ch != "."}
        key = (tuple(sprite), flip, tuple(sorted(used.items())))
        surf = _SURFACES.get(key)
        if surf is None:
            if len(_SURFACES) > 400:  # f.eks. etter mange fargebytter
                _SURFACES.clear()
            w, h = size(sprite)
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * PX, h * PX)
            sc = cairo.Context(surf)
            for row, line in enumerate(sprite):
                for col, ch in enumerate(line):
                    if ch != ".":
                        sc.set_source_rgb(*rgb(used[ch]))
                        sc.rectangle(((w - 1 - col) if flip else col) * PX, row * PX, PX, PX)
                        sc.fill()
            _SURFACES[key] = surf
        cr.set_source_surface(surf, round(x), round(y))
        cr.get_source().set_filter(cairo.FILTER_NEAREST)  # skarpe piksler også når katten er rotert
        if alpha < 1:
            cr.paint_with_alpha(alpha)
        else:
            cr.paint()

    def glyph(self, cr, ch, color):
        """En bokstav i tittelen som ferdig bilde (tegnes én gang per bokstav og farge)."""
        key = ("glyph", ch, color, self.font_px)
        surf = _SURFACES.get(key)
        if surf is None:
            lay = self.layout(cr, ch)
            _, log = lay.get_pixel_extents()
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, log.width + 2), max(1, log.height + 2))
            sc = cairo.Context(surf)
            sc.set_source_rgb(*rgb(color))
            PangoCairo.show_layout(sc, self.layout(sc, ch))
            _SURFACES[key] = surf
        return surf

    def draw(self, area, cr, width, height):
        pal = self.palette()
        if getattr(self, "metrics_for", None) != (self.title, self.font_px):
            lay = self.layout(cr)
            self.ink, self.logical = lay.get_pixel_extents()
            # Bokstavposisjoner (brukes av fysikken)
            self.letters = []
            for i in range(len(self.title)):
                r = lay.index_to_pos(len(self.title[:i].encode()))
                self.letters.append([r.x / Pango.SCALE, r.width / Pango.SCALE])
            self.metrics_for = (self.title, self.font_px)
        ink, logical = self.ink, self.logical
        base_y = height - logical.height - 2
        top = base_y + ink.y  # oversiden av bokstavene = bakken katten står på
        self.top = top

        if len(self.dy) != len(self.title):  # rett etter set_title
            self.dy = [0.0] * len(self.title)
            self.vy = [0.0] * len(self.title)

        # Tittelen, bokstav for bokstav med egen forskyvning
        for i, ch in enumerate(self.title):
            if ch != " ":
                cr.set_source_surface(self.glyph(cr, ch, pal["fg"]), self.letters[i][0], round(base_y + self.dy[i]))
                cr.paint()

        anim = self.anim
        if anim is None:
            return
        if self.away or (anim == "climb" and self.external):
            anim = None  # ingen katt på tittelen: markøren blinker som vanlig
        elif anim == "climb":
            anim = "walk"

        # Markøren «_»
        end_x = self.letters[-1][0] + self.letters[-1][1] + 2
        cr.set_source_rgb(*rgb(pal["accent"]))
        if anim == "eat":
            pass  # markøren tar lunsjpause
        elif anim == "play":
            # Markøren er "ballen" katten jager oppå bokstavene
            cr.rectangle(self.ball_x, top - 4 + self.cursor_y, 12, 4)
            cr.fill()
        elif int(self.t / 0.55) % 2 == 0 or self.cursor_y < 0:
            cr.rectangle(end_x, base_y + ink.y + ink.height - 3 + self.cursor_y, 12, 3)
            cr.fill()

        if not self.external:
            self.draw_cat(cr, width)

    def draw_cat(self, cr, width):
        """Katten (med skål, z-er, boble og hjerte) på tittelen, i tittelens koordinater."""
        pal = self.palette()
        top = self.top
        anim = "walk" if self.anim == "climb" else self.anim
        if anim is None:
            return
        # Katten
        flip = self.dir < 0
        y_off = 0
        if anim in ("walk", "play"):
            arc = self.gap_arc(self.x + 10 * PX)
            if arc > 0.1:  # i lufta over et mellomrom
                sprite = SPRITES["run"][0]
                y_off = -arc * 18
            elif anim == "walk":
                sprite = SPRITES["walk"][int(self.t * 6) % 2]
            else:
                sprite = SPRITES["run"][int(self.t * 10) % 2]
        elif anim == "sleep":
            sprite = SPRITES["sleep"][int(self.t / 1.2) % 2]
            for i in range(3):  # z-er som stiger
                phase = (self.t / 3 + i / 3) % 1
                zx = self.x + 16 * PX + phase * 14
                zy = top - size(sprite)[1] * PX - 6 - phase * 26
                self.blit(cr, Z, zx, zy, colors={"e": pal["muted"]}, alpha=1 - phase)
        elif anim == "eat":
            sprite = SPRITES["eat"][int(self.t * 2.5) % 2]
        elif anim == "sit":
            swatting = self.t - self.swat_t < 0.25
            sprite = SPRITES["sit"][2 if swatting else int(self.t * 2) % 2]
        else:  # jump
            arc = math.sin(math.pi * min(self.hop["t"], 1))
            sprite = SPRITES["run"][0] if arc > 0.2 else SPRITES["walk"][0]
            y_off = -arc * 30

        # Blunk av og til (ikke når den sover)
        if anim != "sleep" and (self.t % 4.2) < 0.12:
            sprite = [r.replace("e", "b") for r in sprite]

        cat_y = top - size(sprite)[1] * PX + PX + y_off  # nederste kontur står på bokstavene
        self.blit(cr, sprite, self.x, cat_y, flip)

        if anim == "eat":
            # Skåla foran hodet (tegnes over så hodet ser ut til å være nede i den); maten minker utover timen
            # Hvor langt i lunsjen vi er (0–1); maten minker i tre trinn
            if self.forced == "eat":
                part = (self.t / 15) % 1
            else:
                part = self.lunch_minute(datetime.now()) / self.lunch_length()
            bowl = BOWLS[min(2, int(part * 3))]
            bx = self.x + 16 * PX
            self.blit(cr, bowl, bx, top - size(bowl)[1] * PX + PX)
            # «nom» som stiger opp innimellom
            phase = (self.t % 2.2) / 2.2
            if part < 2 / 3 and phase < 0.7:  # ingen «nom» når skåla er tom
                cr.set_source_rgba(*rgb(pal["muted"]), 1 - phase / 0.7)
                cr.move_to(bx + 22 + phase * 8, top - 30 - phase * 18)
                nom = self.layout(cr, "nom")
                nom.set_font_description(Pango.FontDescription.from_string("Silkscreen 8px"))
                PangoCairo.show_layout(cr, nom)

        if self.t < self.speech_until:
            self.draw_bubble(cr, pal, width, self.x + size(sprite)[0] * PX / 2, cat_y - 4)
        elif self.t < self.happy_until:
            rise = (1 - (self.happy_until - self.t) / 1.6) * 14
            self.blit(cr, HEART, self.x + size(sprite)[0] * PX / 2 - 5, cat_y - 14 - rise)

    def draw_bubble(self, cr, pal, width, cx, bottom):
        """Pixel-snakkeboble med hale ned mot katten."""
        lay = self.layout(cr, self.speech)
        lay.set_font_description(Pango.FontDescription.from_string("Silkscreen 8px"))
        _, log = lay.get_pixel_extents()
        w, h = log.width + 10, log.height + 6
        x = round(max(1, min(width - w - 1, cx - w / 2)))
        y = round(max(1, bottom - h - 4))
        pop = min(1.0, (2.0 - (self.speech_until - self.t)) / 0.12)  # liten "pop" når den dukker opp
        cr.save()
        cr.translate(x + w / 2, y + h)
        cr.scale(pop, pop)
        cr.translate(-(x + w / 2), -(y + h))
        cr.set_source_rgb(*rgb(pal["fg"]))
        cr.rectangle(x, y, w, h)
        cr.fill()
        tail = round(max(x + 3, min(x + w - 7, cx - 2)))
        for i in range(3):  # trappetrinn-hale
            cr.rectangle(tail + i, y + h + i, 4 - i, 1 * 2)
        cr.fill()
        cr.set_source_rgb(*rgb(pal["bg"]))
        cr.move_to(x + 5, y + 3)
        PangoCairo.show_layout(cr, lay)
        cr.restore()


class CatRoamer(Gtk.Fixed):
    """Gjennomsiktig lag over hele vinduet som tegner katten.

    Selve tegneflaten er bare en liten rute (BOX) som flyttes dit katten er; da tegner GTK bare om den
    ruta i stedet for hele vinduet (uten grafikkort tegnes alt med prosessoren).

    På tittelen tegnes den der tittelen er (TitleCat styrer animasjonen). Er tittelen scrollet ut av syne,
    eller animasjonen er «climb», går katten rundt innsiden av vinduskanten: bunnen, opp høyre vegg,
    opp-ned langs taket og ned venstre vegg. Når tittelen synes igjen, hopper den tilbake dit.
    """

    SPEED = 40  # piksler i sekundet langs rammen
    EDGE = 1  # avstand fra kanten til potene
    HALF = 11 * PX  # halve kattelengden: katten snur i hjørnet når nesen når veggen, så ingenting stikker ut
    BOX = 160  # tegneflaten rundt katten (plass til boble, skål og z-er)

    def __init__(self, title):
        super().__init__(can_target=False, hexpand=True, vexpand=True)
        self.canvas = Gtk.DrawingArea(can_target=False, width_request=self.BOX, height_request=self.BOX)
        self.canvas.set_draw_func(self.draw_canvas)
        self.put(self.canvas, 0, 0)
        self.origin = (0, 0)
        self.title = title
        title.external = True
        self.mode = "title"  # title | frame | hop
        self.s, self.d = 0.0, 1  # posisjon langs rammen og retning
        self.hop = None
        self.enter = 0.0  # piksler katten ennå er over toppkanten når den klatrer inn i rammen
        self.last = time.monotonic()
        GLib.timeout_add(1000 // FPS, self.tick, None, None)

    # --- geometri ---
    def sides(self):
        """Lengden på hver kant katten kan gå langs (midten av katten holder seg en halv katt fra hjørnene)."""
        w, h, m = self.get_width(), self.get_height(), self.EDGE
        return max(1, w - 2 * m - 2 * self.HALF), max(1, h - 2 * m - 2 * self.HALF), m

    def perimeter(self):
        iw, ih, _ = self.sides()
        return 2 * (iw + ih)

    def frame_pose(self, s):
        """(x, y, vinkel) for potene ved posisjon s langs rammen. Vinkelen peker kattens «ned» mot kanten."""
        iw, ih, m = self.sides()
        w, h, e = self.get_width(), self.get_height(), self.HALF
        s %= max(1.0, self.perimeter())
        if s < iw:
            return m + e + s, h - m, 0.0  # bunnen, går mot høyre
        s -= iw
        if s < ih:
            return w - m, h - m - e - s, -math.pi / 2  # høyre vegg, klatrer opp
        s -= ih
        if s < iw:
            return w - m - e - s, m, math.pi  # taket, opp-ned mot venstre
        s -= iw
        return m, m + e + s, math.pi / 2  # venstre vegg, klatrer ned

    def title_pose(self):
        """(x, y, synlig) for kattens poter på tittelen, i lagets koordinater."""
        ok, p = self.title.compute_point(self, Graphene.Point())
        if not ok:
            return 0, 0, False
        x = p.x + self.title.x + 10 * PX
        y = p.y + self.title.top + PX
        visible = y - 17 * PX >= 0 and y <= self.get_height()  # hele katten må få plass
        return x, y, visible

    # --- animasjon ---
    def tick(self, widget, clock):
        if detached(self):
            return False
        now = time.monotonic()
        dt, self.last = min(now - self.last, 0.05), now
        if self.get_width() == 0:
            return True
        tx, ty, visible = self.title_pose()
        climbing = self.title.animation() == "climb"
        want_frame = not visible or climbing
        iw, ih, m = self.sides()

        if self.mode == "title" and want_frame:
            self.title.away = True
            if not visible:
                # Tittelen er scrollet bort: katten klatrer ned i rammen ovenfra langs nærmeste vegg
                if tx < self.get_width() / 2:
                    self.s, self.d = 2 * iw + ih, 1  # toppen av venstre vegg, nedover
                else:
                    self.s, self.d = iw + ih, -1  # toppen av høyre vegg, nedover
                self.enter = 22 * PX  # starter helt over kanten og klatrer ned i synet
                self.mode = "frame"
            else:
                # climb: hopp fra tittelen ut på nærmeste sidevegg
                if tx < self.get_width() / 2:
                    s, d = 2 * iw + ih + max(0, ty - m), 1
                else:
                    s, d = iw + (ih - max(0, ty - m)), -1
                self.start_hop((tx, ty, 0.0), self.frame_pose(s), "frame")
                self.s, self.d = s, d
        elif self.mode == "frame":
            if self.enter > 0:
                self.enter = max(0.0, self.enter - self.SPEED * dt)
            else:
                self.s = (self.s + self.d * self.SPEED * dt) % max(1.0, self.perimeter())
            if not want_frame:
                self.start_hop(self.frame_pose(self.s), (tx, ty, 0.0), "title")
        elif self.mode == "hop":
            self.hop["t"] += dt / 0.7
            if self.hop["then"] == "title":
                self.hop["to"] = (tx, ty, 0.0)  # tittelen kan ha flyttet seg mens katten var i lufta
            if self.hop["t"] >= 1:
                self.mode = self.hop["then"]
                if self.mode == "title":
                    self.title.away = False
                    self.title.kick(self.title.x + 10 * PX, 120)  # landing på bokstavene
        calm = self.mode == "title" and self.title.calm()
        if now - getattr(self, "drawn_at", 0) >= 1 / (CALM_FPS if calm else FPS) - 0.005:
            self.drawn_at = now
            # Flytt den lille tegneflaten dit katten er (potene litt under midten, så det er plass til boblen over)
            ax, ay = self.anchor()
            origin = (round(ax - self.BOX / 2), round(ay - self.BOX * 0.62))
            if origin != self.origin:
                self.origin = origin
                self.move(self.canvas, *origin)
            self.canvas.queue_draw()
        return True

    def anchor(self):
        """Kattens poter i lagets koordinater, uansett modus."""
        if self.mode == "title":
            x, y, _ = self.title_pose()
            return x, y
        if self.mode == "frame":
            x, y, _ = self.frame_pose(self.s)
            return x, y - self.enter
        e = min(self.hop["t"], 1)
        (x0, y0, _), (x1, y1, _) = self.hop["from"], self.hop["to"]
        return x0 + (x1 - x0) * e, y0 + (y1 - y0) * e - math.sin(math.pi * e) * self.hop_lift(y0, y1)

    def draw_canvas(self, area, cr, width, height):
        cr.translate(-self.origin[0], -self.origin[1])
        self.draw(area, cr, self.get_width(), self.get_height())

    def hop_lift(self, y0, y1):
        """Hvor høyt hoppet går: 40 px, men aldri så høyt at katten forsvinner over toppkanten."""
        return max(0.0, min(40.0, min(y0, y1) - 17 * PX))

    def start_hop(self, frm, to, then):
        self.hop = {"from": frm, "to": to, "then": then, "t": 0.0}
        self.mode = "hop"

    # --- tegning ---
    def draw(self, area, cr, width, height):
        title = self.title
        if self.mode == "title":
            tx, ty, _ = self.title_pose()
            ok, p = title.compute_point(self, Graphene.Point())
            cr.save()
            cr.translate(p.x, p.y)
            title.draw_cat(cr, title.get_width())
            cr.restore()
            return

        if self.mode == "frame":
            x, y, angle = self.frame_pose(self.s)
            y -= self.enter
            sprite = SPRITES["walk"][int(title.t * 6) % 2]
            flip = self.d < 0
        else:  # hop
            h = self.hop
            e = min(h["t"], 1)
            (x0, y0, a0), (x1, y1, a1) = h["from"], h["to"]
            x = x0 + (x1 - x0) * e
            y = y0 + (y1 - y0) * e - math.sin(math.pi * e) * self.hop_lift(y0, y1)
            angle = a0 if e < 0.5 else a1
            sprite = SPRITES["run"][0]
            flip = x1 < x0
        if (title.t % 4.2) < 0.12:  # blunk
            sprite = [r.replace("e", "b") for r in sprite]

        sw, sh = size(sprite)
        cr.save()
        cr.translate(x, y)
        cr.rotate(angle)
        title.blit(cr, sprite, -sw * PX / 2, -sh * PX + PX, flip)
        cr.restore()

        # Boble/hjerte over hodet, alltid rett vei opp
        hx = x + math.sin(angle) * sh * PX * 0.6
        hy = y - math.cos(angle) * sh * PX * 0.6
        pal = title.palette()
        if title.t < title.speech_until:
            title.draw_bubble(cr, pal, width, hx, max(30, hy - 8))
        elif title.t < title.happy_until:
            rise = (1 - (title.happy_until - title.t) / 1.6) * 14
            title.blit(cr, HEART, hx - 5, max(2, hy - 20 - rise))
