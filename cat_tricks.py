"""Ten more cat animations on the title, kept apart from cat.py so each one is easy to read,
plus two that only the water glasses use (drink and thirsty, see hydration.py) and three reactions
to the window being moved (stressed, grumpy and having fun, see window_moved()).

Each trick has start() (place the cat), tick() (move things on) and draw() (pick the cat sprite and
draw props behind it); draw_front() draws props in front of the cat. TitleCat picks them from TRICKS.
"""
import math
import random

import cat

PX = cat.PX
CW = 20 * PX  # the walking cat's width

# Props (fill only; the outline is added). x/X = box, n/N/Y = bird, Z/z = yarn, m/a/A = water bowl
BOX = ["XXXXXXXXXXXXXX", "xxxxxxxxxxxxxx", "xxxxxxxxxxxxxx", "xxxxxXXXXxxxxx", "xxxxxxxxxxxxxx", "xxxxxxxxxxxxxx"]
BIRD = [[".nn..", "nnnnY", ".NNn.", "..n.."], ["N...N", ".NnN.", ".nnnY", "..n.."]]  # perched, flying
YARN = [[".ZZZZ.", "ZzZZzZ", "ZZzzZZ", "ZzZZzZ", ".ZZZZ."], [".ZZZZ.", "ZZzZZZ", "ZzZZzZ", "ZZZzZZ", ".ZZZZ."]]
WATER_BOWL = [["..aaaaaa..", ".aAaaaaAa.", "mmmmmmmmmm", ".mmmmmmmm.", "..mmmmmm.."],
              ["..aaaaaa..", ".aaaAaaaa.", "mmmmmmmmmm", ".mmmmmmmm.", "..mmmmmm.."]]  # two ripples
cat.COLORS.update(x="#c8955a", X="#9c6a35", n="#8b5a3c", N="#5e3b26", Y="#ffc93c", Z="#e86a92", z="#b8456b",
                  m="#e6e1d6", a="#5cb8ff", A="#d6f0ff")
LASER = "#ff2a2a"


def _sit_with(changes, width=13):
    """The sitting cat (cat.FILL["sit"][0]) with some pixels changed: {(row, col): char}."""
    rows = [list(r.ljust(width, ".")) for r in cat.FILL["sit"][0]]
    for (r, c), ch in changes.items():
        rows[r][c] = ch
    return ["".join(r) for r in rows]


def _roll(paws_up):
    """Belly-up cat: legs in the air, white belly on top, head upside down on the right."""
    w, h = 20, 9
    g = [["."] * w for _ in range(h)]
    for x in range(2, 14):
        for y in range(2, 6):
            g[y][x] = "w" if y == 2 and 3 <= x <= 12 else "b"
    legs = (3, 6, 9, 12)
    for i, x in enumerate(legs):
        lift = 0 if (i % 2 == 0) == paws_up else 1  # paws wiggle
        g[lift][x] = "w"
        g[1][x] = g[1][x] if g[1][x] != "." else "b"
    for x, y in ((1, 4), (0, 5), (0, 6)):  # tail
        g[y][x] = "b"
    head = [".bwwwb.", "bbwpwbb", "bebwbeb", "bebbbeb", "bbbbbbb", "bp...pb", "b.....b"]  # upside down
    for dy, row in enumerate(head):
        for dx, ch in enumerate(row):
            if ch != ".":
                g[2 + dy][13 + dx] = ch
    return ["".join(r) for r in g]


cat.FILL["loaf"] = [[r.replace("o", "e") for r in cat.FILL["sleep"][0]], cat.FILL["sleep"][0]]  # eyes open / blink
cat.FILL["roll"] = [_roll(True), _roll(False)]
cat.FILL["wave"] = [_sit_with({(3, 11): "w", (4, 11): "w", (4, 12): "w", (12, 8): ".", (12, 9): "."}),
                    _sit_with({(1, 12): "w", (2, 12): "w", (2, 11): "w", (12, 8): ".", (12, 9): "."})]
cat.FILL["knead"] = [_sit_with({(3, 5): "o", (3, 9): "o", (12, 5): ".", (12, 6): ".", (11, 5): "w", (11, 6): "w"}),
                     _sit_with({(3, 5): "o", (3, 9): "o", (12, 8): ".", (12, 9): ".", (11, 8): "w", (11, 9): "w"})]
cat.set_shape(cat.SETTINGS["shape"])  # rebuild SPRITES with the new poses
PROPS = {"box": cat.add_outline(BOX), "bird": [cat.add_outline(b) for b in BIRD],
         "yarn": [cat.add_outline(y) for y in YARN],
         "water": [cat.add_outline(b) for b in WATER_BOWL], "empty_water": cat.add_outline(WATER_BOWL[0][2:])}


def _hop(t, duration, height):
    return -math.sin(math.pi * min(max(t / duration, 0), 1)) * height


class Trick:
    moving = False  # draw at the full frame rate
    accessories = True  # hats and bow tie can be added to its sprites
    clip_below_letters = False  # hide whatever is drawn below the letter tops

    def start(self, c, lo, hi):
        c.x = max(lo, min(hi - CW, c.x))

    def tick(self, c, dt, lo, hi):
        pass

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["sit"][0], 0

    def draw_front(self, c, cr, top, pal, cat_y):
        pass


class Zoomies(Trick):
    """Runs flat out back and forth for 4 s, catches its breath for 2 s."""
    moving = True

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.dust = []

    def running(self, c):
        return c.t % 6 < 4

    def tick(self, c, dt, lo, hi):
        if not self.running(c):
            return
        c.x += c.dir * 160 * dt
        if c.x > hi - CW or c.x < lo:
            c.x, c.dir = max(lo, min(hi - CW, c.x)), -c.dir
        if int(c.t * 14) != int((c.t - dt) * 14):
            c.bounce_letter(c.x + CW / 2, 60)
            c.dust.append((c.x + (0 if c.dir > 0 else CW), c.t))
        c.dust = [d for d in c.dust if c.t - d[1] < 0.5]

    def draw(self, c, cr, top, pal):
        for x, born in c.dust:
            age = (c.t - born) / 0.5
            cr.set_source_rgba(*cat.hex_to_rgb(pal["muted"]), 1 - age)
            cr.rectangle(round(x - c.dir * age * 10), round(top - 3 - age * 8), PX, PX)
            cr.fill()
        if self.running(c):
            return cat.SPRITES["run"][int(c.t * 14) % 2], 0
        return cat.SPRITES["sit"][int(c.t * 4) % 2], 0  # panting, tail going


class TailChase(Trick):
    """Spins after its own tail for 4 s, then sits dizzy with stars around its head."""
    moving = True

    def start(self, c, lo, hi):
        c.x = (lo + hi) / 2 - CW / 2

    def tick(self, c, dt, lo, hi):
        if c.t % 7 < 4:
            c.dir = 1 if int(c.t / 0.16) % 2 else -1

    def draw(self, c, cr, top, pal):
        if c.t % 7 < 4:
            return cat.SPRITES["run"][int(c.t * 12) % 2], -abs(math.sin(c.t * 20)) * 4
        for i in range(3):  # dizzy stars
            a = c.t * 4 + i * 2.1
            cr.set_source_rgb(*cat.hex_to_rgb(pal["accent"]))
            cr.rectangle(round(c.x + 9 * PX + math.cos(a) * 12), round(top - 34 + math.sin(a) * 3), PX, PX)
            cr.fill()
        return cat.SPRITES["sit"][0], 0


class Loaf(Trick):
    """Lies as a loaf with its paws tucked in and blinks slowly."""

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["loaf"][1 if c.t % 5 < 0.6 else 0], 0


class Box(Trick):
    """Sits in a cardboard box and peeks over the edge."""
    clip_below_letters = True

    def start(self, c, lo, hi):
        c.x = (lo + hi) / 2 - 7 * PX

    def draw(self, c, cr, top, pal):
        phase = c.t % 5
        down = 20 if phase < 1.2 else -4 if phase < 4 else 20 - (5 - phase) * 24  # hidden, peeking, ducking
        return cat.SPRITES["sit"][int(c.t * 2) % 2], down

    def draw_front(self, c, cr, top, pal, cat_y):
        box = PROPS["box"]
        c.draw_sprite(cr, box, c.x - PX, top - cat.sprite_size(box)[1] * PX + PX)


class Knead(Trick):
    """Kneads a letter with its front paws ("making biscuits"); the letter dips with each push."""

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.knead_frame = 0

    def tick(self, c, dt, lo, hi):
        frame = int(c.t * 3) % 2
        if frame != c.knead_frame:
            c.knead_frame = frame
            c.bounce_letter(c.x + (6 if frame == 0 else 9) * PX, 30)

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["knead"][int(c.t * 3) % 2], 0


class Laser(Trick):
    """Chases a red laser dot that darts along the letters and stops now and then."""
    moving = True

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.dot = {"x": c.x + CW + 30, "to": c.x + CW + 30, "rest": 0.5}
        c.pounce_t = -10.0

    def tick(self, c, dt, lo, hi):
        d = c.dot
        if abs(d["to"] - d["x"]) > 1:
            step = 240 * dt
            d["x"] += max(-step, min(step, d["to"] - d["x"]))
        else:
            d["rest"] -= dt
            if d["rest"] <= 0:
                d["to"], d["rest"] = random.uniform(lo, hi), random.uniform(0.4, 1.4)
        if c.t - c.pounce_t < 0.5:
            return
        target = d["x"] - CW / 2
        if abs(target - c.x) > 3:
            c.dir = 1 if target > c.x else -1
            c.x = max(lo, min(hi - CW, c.x + c.dir * 90 * dt))
        elif d["rest"] > 0:
            c.pounce_t = c.t  # pounce – and the dot is gone again
            c.bounce_letter(d["x"], 100)
            d["to"], d["rest"] = random.uniform(lo, hi), 0.0

    def draw(self, c, cr, top, pal):
        x = c.dot["x"]
        for size, alpha in ((6, 0.25), (2, 1.0)):
            cr.set_source_rgba(*cat.hex_to_rgb(LASER), alpha)
            cr.rectangle(round(x - size / 2), round(top - 2 - size / 2), size, size)
            cr.fill()
        jump = c.t - c.pounce_t
        if jump < 0.5:
            return cat.SPRITES["run"][0], _hop(jump, 0.5, 18)
        moving = abs(x - CW / 2 - c.x) > 3
        return (cat.SPRITES["run"][int(c.t * 10) % 2] if moving else cat.SPRITES["run"][1]), 0


class Wave(Trick):
    """Waves a paw and says hi now and then."""

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.said_hi = c.t - 25

    def tick(self, c, dt, lo, hi):
        if c.t - c.said_hi > 30:
            c.said_hi = c.t
            c.say(cat._("hi!"), 2)

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["wave"][int(c.t * 4) % 2], 0


class Bird(Trick):
    """A little bird lands on a letter, the cat sneaks up and pounces, and the bird flies off."""
    moving = True

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.bird = {"phase": "away", "t": 0.0, "x": hi, "to": hi}

    def tick(self, c, dt, lo, hi):
        b = c.bird
        b["t"] += dt
        if b["phase"] == "away" and b["t"] > 3:
            spots = [s for s in range(int(lo + CW), int(hi - 10)) if abs(s - c.x - CW / 2) > 50] or [int(hi - 10)]
            b.update(phase="landing", t=0.0, to=random.choice(spots), start=hi + 30)
        elif b["phase"] == "landing" and b["t"] > 1.5:
            b.update(phase="perched", t=0.0, x=b["to"])
        elif b["phase"] == "perched":
            target = b["x"] - CW - 4 if b["x"] > c.x else b["x"] + 8
            c.dir = 1 if b["x"] > c.x else -1
            if abs(target - c.x) > 2:
                c.x = max(lo, min(hi - CW, c.x + (15 if target > c.x else -15) * dt))  # sneaking
            if b["t"] > 2.5:
                b.update(phase="pounce", t=0.0, from_x=c.x)
        elif b["phase"] == "pounce":
            c.x = b["from_x"] + (b["x"] - CW / 2 - b["from_x"]) * min(b["t"] / 0.6, 1)
            if b["t"] > 0.6:
                c.bounce_letter(c.x + CW / 2, 120)
                b.update(phase="flyaway", t=0.0)
        elif b["phase"] == "flyaway" and b["t"] > 1.2:
            b.update(phase="away", t=0.0)

    def draw(self, c, cr, top, pal):
        b = c.bird
        bird_y, bird_x = top - 4 * PX - PX, b["x"]
        if b["phase"] == "landing":
            e = min(b["t"] / 1.5, 1)
            bird_x = b["start"] + (b["to"] - b["start"]) * e
            bird_y -= (1 - e) * 40
        elif b["phase"] in ("pounce", "flyaway"):
            bird_y -= (b["t"] + (0.6 if b["phase"] == "flyaway" else 0)) * 50
            bird_x += (b["t"] + (0.6 if b["phase"] == "flyaway" else 0)) * 40
        if b["phase"] != "away":
            flying = b["phase"] != "perched"
            c.draw_sprite(cr, PROPS["bird"][1 if flying and int(c.t * 10) % 2 else 0], bird_x - 3, bird_y)
        if b["phase"] == "pounce":
            return cat.SPRITES["run"][0], _hop(b["t"], 0.6, 22)
        if b["phase"] == "perched":
            return cat.SPRITES["run"][1], 0  # crouched, sneaking
        return cat.SPRITES["sit"][int(c.t * 2) % 2], 0


class Roll(Trick):
    """Lies on its back with its paws in the air and rolls from side to side."""
    accessories = False  # a hat would end up on the floor

    def tick(self, c, dt, lo, hi):
        if int(c.t / 4) != int((c.t - dt) / 4):
            c.dir = -c.dir  # roll over
            c.x = max(lo, min(hi - CW, c.x + c.dir * 6))

    def draw(self, c, cr, top, pal):
        rolling = c.t % 4 < 0.3
        return cat.SPRITES["roll"][int(c.t * 3) % 2], (-4 if rolling else 0)


class Yarn(Trick):
    """Bats a ball of yarn along the title; it rolls away and leaves a thread behind."""
    moving = True

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.yarn = {"x": c.x + CW + 16, "v": 0.0, "from": c.x + CW + 16, "rolled": 0.0}
        c.swat_t = -10.0

    def tick(self, c, dt, lo, hi):
        y = c.yarn
        if y["v"]:
            step = y["v"] * dt
            y["x"] += step
            y["rolled"] += abs(step)
            y["v"] -= y["v"] * 1.4 * dt  # friction
            if y["x"] < lo or y["x"] > hi - 10:
                y["x"], y["v"] = max(lo, min(hi - 10, y["x"])), -y["v"] * 0.6
            c.bounce_letter(y["x"] + 5, 6)
            if abs(y["v"]) < 6:
                y["v"] = 0.0
            return
        target = y["x"] - CW if y["x"] > c.x + CW / 2 else y["x"] + 10
        if abs(target - c.x) > 3:
            c.dir = 1 if target > c.x else -1
            c.x = max(lo, min(hi - CW, c.x + c.dir * 40 * dt))
        else:
            c.swat_t = c.t  # bat it!
            away = 1 if y["x"] > c.x + CW / 2 else -1
            y["v"] = away * random.uniform(90, 150)
            c.dir = away

    def draw(self, c, cr, top, pal):
        y = c.yarn
        cr.set_source_rgba(*cat.hex_to_rgb(cat.COLORS["Z"]), 0.8)  # the thread back to where it started
        for i in range(0, int(abs(y["x"] - y["from"])), 3):
            x = min(y["x"], y["from"]) + i
            cr.rectangle(round(x), round(top - 2 + math.sin(i / 7) * 1.5), 2, 1)
        cr.fill()
        ball = PROPS["yarn"][int(y["rolled"] / 6) % 2]
        c.draw_sprite(cr, ball, y["x"], top - cat.sprite_size(ball)[1] * PX + PX)
        if c.t - c.swat_t < 0.3:
            return cat.SPRITES["sit"][2], 0
        moving = not y["v"] and abs((y["x"] - CW if y["x"] > c.x + CW / 2 else y["x"] + 10) - c.x) > 3
        return (cat.SPRITES["walk"][int(c.t * 6) % 2] if moving else cat.SPRITES["sit"][0]), 0


class Drink(Trick):
    """Laps water from its bowl while you drink a glass; little drops jump out."""

    def start(self, c, lo, hi):
        c.x, c.dir = max(lo, min(hi - CW - 10 * PX, c.x)), 1

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["eat"][int(c.t * 4) % 2], 0

    def draw_front(self, c, cr, top, pal, cat_y):
        bowl = PROPS["water"][int(c.t * 4) % 2]
        bx, by = c.x + 16 * PX, top - cat.sprite_size(bowl)[1] * PX + PX
        c.draw_sprite(cr, bowl, bx, by)  # in front, so the head dips into it
        for i in range(2):
            phase = (c.t * 1.4 + i / 2) % 1
            cr.set_source_rgba(*cat.hex_to_rgb(cat.COLORS["a"]), 1 - phase)
            cr.rectangle(round(bx + (3 + i * 4) * PX + math.sin(phase * 5 + i) * 2), round(by - phase * 12), PX, PX)
            cr.fill()


class Thirsty(Trick):
    """Sits by its empty water bowl and pats it now and then, until you drink something."""

    def start(self, c, lo, hi):
        c.x, c.dir = max(lo, min(hi - CW - 10 * PX, c.x)), 1

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["sit"][2 if c.t % 3 < 0.35 else 0], 0

    def draw_front(self, c, cr, top, pal, cat_y):
        bowl = PROPS["empty_water"]
        pat = PX if c.t % 3 < 0.35 else 0  # the bowl jiggles when patted
        c.draw_sprite(cr, bowl, c.x + 14 * PX + pat, top - cat.sprite_size(bowl)[1] * PX + PX)


TRICKS = {"zoomies": Zoomies(), "tailchase": TailChase(), "loaf": Loaf(), "box": Box(), "knead": Knead(),
          "laser": Laser(), "wave": Wave(), "bird": Bird(), "roll": Roll(), "yarn": Yarn()}
cat.TRICKS.update(TRICKS)
cat.ANIMATIONS.extend(TRICKS)
WATER_TRICKS = {"drink": Drink(), "thirsty": Thirsty()}  # not in the rotation: only when you drink, or forget to
cat.TRICKS.update(WATER_TRICKS)


# --- Reactions when the window is moved ---
ANGER = ["r.r.r", ".....", "r...r", ".....", "r.r.r"]  # a little "anger mark" over the head
SWEAT = "#7fc8ff"


class Stressed(Trick):
    """Clings on and trembles, with drops of sweat, while the letters shiver."""

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.shake_x = c.x

    def tick(self, c, dt, lo, hi):
        c.x = c.shake_x + (PX if int(c.t * 30) % 2 else -PX)
        if random.random() < dt * 12:
            c.bounce_letter(random.uniform(lo, hi), 25)

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["sit"][0], -PX if int(c.t * 15) % 2 else 0

    def draw_front(self, c, cr, top, pal, cat_y):
        for i in range(2):
            phase = (c.t * 1.6 + i / 2) % 1
            cr.set_source_rgba(*cat.hex_to_rgb(SWEAT), 1 - phase)
            x = c.shake_x + (11 + i * 3) * PX + phase * 6
            cr.rectangle(round(x), round(cat_y + 2 * PX + phase * 14), PX, 2 * PX)
            cr.fill()


class Grumpy(Trick):
    """Swats at you with an anger mark over its head, stomping the letter it sits on."""

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.swat_frame = 0

    def tick(self, c, dt, lo, hi):
        frame = int(c.t * 5) % 2
        if frame != c.swat_frame:
            c.swat_frame = frame
            if frame:
                c.bounce_letter(c.x + 12 * PX, 60)

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["sit"][2 if int(c.t * 5) % 2 else 0], 0

    def draw_front(self, c, cr, top, pal, cat_y):
        if int(c.t * 4) % 3:  # the mark pulses
            c.draw_sprite(cr, ANGER, c.x + 14 * PX, cat_y - 3 * PX, colors={"r": "#ff3b3b"})


class Wheee(Trick):
    """Loves the ride: bounces back and forth on the letters with little sparkles."""
    moving = True

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.ride_from = c.x
        c.landed = True

    def tick(self, c, dt, lo, hi):
        c.x = max(lo, min(hi - CW, c.ride_from + math.sin(c.t * 2.5) * 40))
        c.dir = 1 if math.cos(c.t * 2.5) > 0 else -1
        up = abs(math.sin(c.t * 6)) > 0.2
        if not up and c.landed is False:
            c.bounce_letter(c.x + CW / 2, 50)
        c.landed = not up

    def draw(self, c, cr, top, pal):
        return cat.SPRITES["run"][0], -abs(math.sin(c.t * 6)) * 14

    def draw_front(self, c, cr, top, pal, cat_y):
        for i in range(3):
            phase = (c.t * 1.2 + i / 3) % 1
            cr.set_source_rgba(*cat.hex_to_rgb(cat.COLORS["Y"]), 1 - phase)
            x = c.x + CW / 2 + math.sin(i * 2.1 + c.t) * 22
            cr.rectangle(round(x), round(cat_y - phase * 12), PX, PX)
            cr.fill()


MOVE_TRICKS = {"stressed": Stressed(), "grumpy": Grumpy(), "wheee": Wheee()}  # only when the window is moved
cat.TRICKS.update(MOVE_TRICKS)
MOVE_EVENTS = {"stressed": "moved_stressed", "grumpy": "moved_grumpy", "wheee": "moved_fun"}


def window_moved(c):
    """The window is being dragged: the cat reacts – stressed, grumpy or having fun.
    Moved again and again within 20 seconds, it gets grumpy."""
    c.moved_at = [t for t in getattr(c, "moved_at", []) if c.t - t < 20] + [c.t]
    if c.treat in MOVE_TRICKS and c.t < c.treat_until:
        return  # already reacting to this move
    mood = "grumpy" if len(c.moved_at) >= 3 else random.choice(list(MOVE_TRICKS))
    c.play(mood, 3.5)
    c.react_to(MOVE_EVENTS[mood], 2.5)


# --- Otto: write "otto" in the plan and the cat turns into a dancing otter for a while ---
OTTER = ["....uuuuuu....",
         "...uuuuuuuu...",
         "..uiyiuuiyiu..",
         "..uiiiiiiiiu..",
         "..iiiiyyiiii..",
         "...iiiiiiii...",
         "....uiiiiu....",
         "...uuiiiiuu...",
         "...uiiiiiiu...",
         "...uiiiiiiu...",
         "...uiiiiiiu...",
         "...uiiiiiiuu..",
         "....uiiiiu.uu.",
         "....uu..uu..uu",
         "...UUU..UUU..U"]
OTTER_ARMS = [{(7, 2): "u", (6, 1): "u", (5, 1): "u", (4, 1): "u", (3, 1): "U",  # left paw up, right paw down
               (8, 11): "u", (9, 11): "u", (10, 11): "U"},
              {(7, 11): "u", (6, 12): "u", (5, 12): "u", (4, 12): "u", (3, 12): "U",  # right paw up, left paw down
               (8, 2): "u", (9, 2): "u", (10, 2): "U"}]
NOTE = ["..ee", "..e.", "..e.", "eee.", "ee.."]
cat.COLORS.update(u="#6e4527", U="#432817", i="#e3c49a", y="#1b1410")
POOF = 0.6  # seconds for the puff of smoke at each end
OTTER_SECONDS = 10 + 2 * POOF


def _otter(arms):
    rows = [list(r) for r in OTTER]
    for (r, c), ch in arms.items():
        rows[r][c] = ch
    return cat.add_outline(["".join(r) for r in rows])


OTTER_SPRITES = [_otter(a) for a in OTTER_ARMS]


class Otter(Trick):
    """Poof! An otter dances for 10 s with music notes around it, then poof! the cat is back."""
    moving = True
    accessories = False  # the hat and bow tie belong to the cat

    def start(self, c, lo, hi):
        super().start(c, lo, hi)
        c.otter_from, c.otter_x = c.t, c.x

    def tick(self, c, dt, lo, hi):
        dancing = POOF < c.t - c.otter_from < OTTER_SECONDS - POOF
        c.x = max(lo, min(hi - CW, c.otter_x + (math.sin(c.t * 3) * 10 if dancing else 0)))
        if dancing and int(c.t * 4) != int((c.t - dt) * 4):
            c.bounce_letter(c.x + 7 * PX, 40)

    def is_otter(self, c):
        return POOF / 2 < c.t - c.otter_from < OTTER_SECONDS - POOF / 2

    def draw(self, c, cr, top, pal):
        if not self.is_otter(c):
            return cat.SPRITES["sit"][0], 0
        c.dir = 1 if int(c.t * 2) % 2 else -1  # turns with the beat
        return OTTER_SPRITES[int(c.t * 4) % 2], -abs(math.sin(c.t * 2 * math.pi)) * 6

    def draw_front(self, c, cr, top, pal, cat_y):
        age = c.t - c.otter_from
        if self.is_otter(c):
            for i in range(2):
                phase = (c.t / 1.6 + i / 2) % 1
                nx = c.x + (-6 if i else 15 * PX) + math.sin(phase * 5 + i) * 4
                c.draw_sprite(cr, NOTE, nx, cat_y - phase * 18, colors={"e": pal["accent"]}, alpha=1 - phase)
        for start in (0.0, OTTER_SECONDS - POOF):
            if start <= age < start + POOF:
                self.draw_poof(c, cr, cat_y, (age - start) / POOF, pal)

    def draw_poof(self, c, cr, cat_y, k, pal):
        """A puff of smoke that swells and fades, hiding the change from cat to otter and back."""
        cx, cy = c.x + 7 * PX, cat_y + 8 * PX
        cr.set_source_rgba(*cat.hex_to_rgb(pal["muted"]), 1 - k)
        for i in range(9):
            angle = i * 2 * math.pi / 9
            reach = 6 + k * 18
            size = round((1 - k) * 8 + 4)
            cr.rectangle(round(cx + math.cos(angle) * reach - size / 2), round(cy + math.sin(angle) * reach * 0.7 - size / 2), size, size)
        cr.fill()


cat.TRICKS["otter"] = Otter()


def otter(c):
    """Turn the cat into a dancing otter (when "otto" is written in the plan)."""
    c.play("otter", OTTER_SECONDS)
    c.say("otto!", 1.5)
