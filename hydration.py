"""Water: a row of pixel glasses under the hours, to help you drink enough during the day.

Click the next glass and it fills up – and the cat laps from its own water bowl. Click the last full
glass to undo. If no glass has been drunk for a while (⚙ → water), the next glass hops, the row
lights up and the cat sits by its empty bowl until you drink. Reaching the goal makes the glasses wave.
The count is stored per day in the database; the settings in config.json.
"""
import math
import time
from datetime import datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import cat  # noqa: E402
import database as db  # noqa: E402
import platforms  # noqa: E402
from translations import _  # noqa: E402

DEFAULTS = {"water_goal": 8, "water_glass_ml": 250, "water_every": 60, "water_notify": False}
MAX_GLASSES = 12  # glasses shown in the row (you can drink more; the count keeps going)
P = 2  # screen pixels per glass pixel
GLASS_W, GLASS_H, GAP = 9, 13, 4  # in glass pixels / screen pixels
WATER, SURFACE = "#5cb8ff", "#d6f0ff"
POUR_SECONDS, WAVE_SECONDS = 0.7, 2.0

CSS = """
.water { border-bottom: 1px solid @mt_line; padding: 12px 0; }
.water.attention { border-bottom-color: @mt_accent; }
"""


def settings():
    config = db.load_config()
    return {k: config.get(k, v) for k, v in DEFAULTS.items()}


def is_thirsty(now, since, every, glasses, goal):
    """Time for a glass: the reminder is on, the goal isn't reached and `every` minutes have passed
    since `since` (the last glass, or when the list was opened today)."""
    return bool(every) and glasses < goal and since is not None and now - since >= timedelta(minutes=every)


def litres(glasses, glass_ml):
    return f"{glasses * glass_ml / 1000:.2f}".rstrip("0").rstrip(".") + " L"


class WaterGlasses(Gtk.DrawingArea):
    """The pixel glasses. Animations: a glass filling or emptying, the next one hopping, and a wave."""

    def __init__(self, on_click):
        super().__init__(halign=Gtk.Align.START)
        self.count, self.slots = 0, DEFAULTS["water_goal"]
        self.thirsty = False
        self.fills = {}  # glass index -> (start, from level, to level)
        self.wave_start = -10.0
        self.timer = 0
        self.set_draw_func(self.draw)
        self.set_cursor_from_name("pointer")
        self.set_tooltip_text(_("Click a glass when you drink one; click the last full glass to undo"))
        click = Gtk.GestureClick()
        click.connect("pressed", lambda _g, _n, x, _y: on_click(self.index_at(x)))
        self.add_controller(click)
        self.resize()

    def resize(self):
        self.set_content_width(self.slots * (GLASS_W * P + GAP))
        self.set_content_height(GLASS_H * P + 8)  # + room for hopping

    def show(self, count, slots, thirsty):
        self.count, self.thirsty = count, thirsty
        if slots != self.slots:
            self.slots = slots
            self.resize()
        self.animate()

    def index_at(self, x):
        return int(x // (GLASS_W * P + GAP))

    def pour(self, i, filling):
        self.fills[i] = (time.monotonic(), 0.0 if filling else 1.0, 1.0 if filling else 0.0)
        self.animate()

    def slosh(self, i):
        self.fills[i] = (time.monotonic(), 1.0, 1.0)  # stays full; the surface ripples
        self.animate()

    def wave(self):
        self.wave_start = time.monotonic()
        self.animate()

    def busy(self, now):
        return self.thirsty or now - self.wave_start < WAVE_SECONDS or any(
            now - start < POUR_SECONDS + 0.5 for start, _f, _t in self.fills.values())

    def animate(self):
        self.queue_draw()
        if not self.timer and self.busy(time.monotonic()):
            self.timer = GLib.timeout_add(1000 // 30, self.tick)

    def tick(self):
        self.queue_draw()
        now = time.monotonic()
        self.fills = {i: f for i, f in self.fills.items() if now - f[0] < POUR_SECONDS + 0.5}  # splash done
        if cat.was_closed(self) or not self.busy(now):
            self.timer = 0
            return False
        return True

    def level(self, i, now):
        if i in self.fills:
            start, frm, to = self.fills[i]
            k = min(1.0, (now - start) / POUR_SECONDS)
            return frm + (to - frm) * (1 - (1 - k) ** 2)  # eases out
        return 1.0 if i < self.count else 0.0

    def draw(self, _area, cr, width, height):
        now = time.monotonic()
        wall = self.get_color()
        for i in range(self.slots):
            x0 = i * (GLASS_W * P + GAP)
            hop = 0.0
            if self.thirsty and i == self.count:
                hop = abs(math.sin(now * 6)) * 5 if now % 2 < 0.55 else 0  # the next glass hops: "drink me!"
            wave = now - self.wave_start
            if wave < WAVE_SECONDS:
                hop = max(hop, max(0.0, math.sin((wave - i * 0.1) * 7)) * 4 * (1 - wave / WAVE_SECONDS))
            y0 = height - GLASS_H * P - round(hop)
            level = self.level(i, now)
            # Water from the bottom up; the top row is the lighter surface (it ripples while pouring)
            rows = round(level * (GLASS_H - 1))
            for r in range(rows):
                y = GLASS_H - 2 - r
                left, right = 1 + y // 7, GLASS_W - 2 - y // 7
                for x in range(left, right + 1):
                    surface = r == rows - 1 and (i not in self.fills or (x + int(now * 12)) % 3)
                    cr.set_source_rgba(*cat.hex_to_rgb(SURFACE if surface else WATER), 1)
                    cr.rectangle(x0 + x * P, y0 + y * P, P, P)
            cr.fill()
            # A bubble rises in full glasses now and then
            if level >= 1 and (now + i * 0.7) % 4 < 1.2:
                b = (now + i * 0.7) % 4 / 1.2
                cr.set_source_rgba(*cat.hex_to_rgb(SURFACE), 1 - b)
                cr.rectangle(x0 + (3 + i % 3) * P, y0 + round((GLASS_H - 3) * (1 - b) + 1) * P, P, P)
                cr.fill()
            # Splash when a glass is full
            for start, frm, to in [self.fills[i]] if i in self.fills else []:
                k = (now - start - POUR_SECONDS * 0.8) / 0.5
                if to > frm and 0 < k < 1:
                    cr.set_source_rgba(*cat.hex_to_rgb(WATER), 1 - k)
                    for dx in (-1, 1):
                        cr.rectangle(x0 + (GLASS_W // 2 + dx * (1 + k * 3)) * P, y0 - k * 6 + (k * k) * 8, P, P)
                    cr.fill()
            # The glass: slightly narrower at the bottom, and a thick base
            cr.set_source_rgba(wall.red, wall.green, wall.blue, 0.75)
            for y in range(GLASS_H - 1):
                inset = y // 7
                cr.rectangle(x0 + inset * P, y0 + y * P, P, P)
                cr.rectangle(x0 + (GLASS_W - 1 - inset) * P, y0 + y * P, P, P)
            cr.rectangle(x0 + P, y0 + (GLASS_H - 1) * P, (GLASS_W - 2) * P, P)
            cr.fill()


class WaterBox(Gtk.Box):
    """The water section under the hours. on_change(glasses, last_glass_iso) saves the day."""

    def __init__(self, title_cat, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("water")
        self.title_cat, self.on_change = title_cat, on_change
        self.count, self.last = 0, None  # glasses today, time of the last one
        self.since = datetime.now()  # when to start counting for the reminder if nothing is drunk yet
        self.notified = False
        row = Gtk.Box(spacing=10)
        row.append(_label("H2O", "num"))
        row.append(_label(_("Water today"), "title"))
        self.amount = _label("", "detail", "muted")
        self.amount.set_hexpand(True)
        self.amount.set_xalign(1)
        row.append(self.amount)
        self.append(row)
        self.glasses = WaterGlasses(self.on_glass)
        self.glasses.set_margin_start(30)
        self.append(self.glasses)
        self.hint = _label("", "detail", "muted")
        self.hint.set_margin_start(30)
        self.hint.set_wrap(True)
        self.append(self.hint)
        self.apply_settings()

    def show_day(self, glasses, last_iso):
        """A new day is loaded (or today again)."""
        self.count = glasses or 0
        self.last = datetime.fromisoformat(last_iso) if last_iso else None
        self.since = datetime.now()
        self.notified = False
        self.refresh()

    def apply_settings(self):
        self.cfg = settings()
        self.set_visible(self.cfg["water_goal"] > 0)
        self.refresh()

    def thirsty_now(self, now=None):
        now = now or datetime.now()
        since = self.last if self.last and self.last.date() == now.date() else self.since
        return is_thirsty(now, since, self.cfg["water_every"], self.count, self.cfg["water_goal"])

    def refresh(self):
        goal = self.cfg["water_goal"]
        thirsty = self.get_visible() and self.thirsty_now()
        self.amount.set_label(f"{self.count} / {goal} · {litres(self.count, self.cfg['water_glass_ml'])}")
        if self.count >= goal > 0:
            hint = _("Goal reached – well done!")
        elif thirsty:
            hint = _("Time for a glass of water!")
        elif self.cfg["water_every"]:
            now = datetime.now()
            since = self.last if self.last and self.last.date() == now.date() else self.since
            left = max(1, math.ceil((since + timedelta(minutes=self.cfg["water_every"]) - now).total_seconds() / 60))
            hint = _("Click a glass when you drink · next in {min} min").format(min=left)
        else:
            hint = _("Click a glass when you drink")
        self.hint.set_label(hint)
        (self.add_css_class if thirsty else self.remove_css_class)("attention")
        (self.hint.add_css_class if thirsty else self.hint.remove_css_class)("err")
        self.title_cat.thirsty = thirsty
        self.glasses.show(self.count, max(1, min(MAX_GLASSES, max(goal, self.count))), thirsty)

    def check(self):
        """Called every 30 s: start or stop being thirsty, and let the cat ask now and then."""
        was = self.title_cat.thirsty
        self.refresh()
        if not self.title_cat.thirsty:
            self.notified = False
            return
        if not was or int(time.monotonic() / 30) % 4 == 0:  # when it starts, then about every 2 minutes
            self.title_cat.react_to("thirsty", 3)
        if self.cfg["water_notify"] and not self.notified:
            self.notified = True
            platforms.notify(_("Time for some water"), _("The cat is thirsty too – have a glass of water."))

    def on_glass(self, i):
        if i == self.count - 1:
            self.undo()
        elif i >= self.count:
            self.drink()
        else:
            self.glasses.slosh(i)  # an earlier full glass: just a little slosh

    def drink(self):
        self.count += 1
        self.last = datetime.now()
        if self.count <= MAX_GLASSES:
            self.glasses.pour(self.count - 1, True)
        self.title_cat.play("drink", 4.0)
        if self.count == self.cfg["water_goal"]:
            self.glasses.wave()
            self.title_cat.react_to("water_goal", 3)
        else:
            self.title_cat.react_to("water")
        self.notified = False
        self.refresh()
        self.on_change(self.count, self.last.isoformat(timespec="seconds"))

    def undo(self):
        if not self.count:
            return
        self.count -= 1
        self.glasses.pour(self.count, False)
        self.refresh()
        self.on_change(self.count, self.last.isoformat(timespec="seconds") if self.last else None)


def _label(text, *classes):
    lbl = Gtk.Label(label=text, xalign=0)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


def build_settings(page, on_change):
    """The water section on the settings page: goal, glass size, reminder and notification."""
    heading = _label(_("water"), "num")
    heading.set_margin_top(14)
    page.append(heading)
    about = _label(_("A glass to click per drink. 0 glasses hides the water row."), "detail", "muted")
    about.set_wrap(True)
    page.append(about)
    cfg = settings()

    def spin_row(text, key, lo, hi, step):
        row = Gtk.Box(spacing=8)
        row.add_css_class("setrow")
        lbl = _label(text, "detail")
        lbl.set_hexpand(True)
        lbl.set_wrap(True)
        row.append(lbl)
        spin = Gtk.SpinButton.new_with_range(lo, hi, step)
        spin.set_value(cfg[key])
        spin.connect("value-changed", lambda s: changed(key, int(s.get_value())))
        row.append(spin)
        page.append(row)

    def changed(key, value):
        db.update_config(**{key: value})
        on_change()

    spin_row(_("glasses a day"), "water_goal", 0, MAX_GLASSES, 1)
    spin_row(_("glass size (ml)"), "water_glass_ml", 100, 1000, 50)
    spin_row(_("remind me after (min, 0 = off)"), "water_every", 0, 240, 15)
    notify = Gtk.CheckButton(label=_("also as a desktop notification"), active=cfg["water_notify"])
    notify.add_css_class("detail")
    notify.get_last_child().set_wrap(True)
    notify.connect("toggled", lambda c: changed("water_notify", c.get_active()))
    page.append(notify)
