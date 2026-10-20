"""Pomodoro-panel for morgen-todo-vinduet (glir ut fra siden, som plan-panelet).

Standard: 25 min fokus → 5 min pause, og 15 min lang pause etter hver 4. fokusøkt.
Tidene kan endres under «settings» i panelet og lagres i ~/.config/morgen-todo/pomodoro-settings.json.
Katten i «good morning» følger med mens klokka går: sover når du jobber,
leker i pausene og spiser i den lange pausen. Når klokka står, gjør den som vanlig.
"""
import json
import subprocess
from datetime import date, datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import db  # noqa: E402
from i18n import _  # noqa: E402

# Standardverdier; brukerens egne ligger i SETTINGS_FILE. "rounds" = lang pause etter så mange fokusøkter
DEFAULTS = {"focus": 25, "short": 5, "long": 15, "rounds": 4}
# Innstillingene i panelet: nøkkel, tekst, min, maks
FIELDS = [("focus", "focus min", 1, 120), ("short", "break min", 1, 60), ("long", "long break min", 1, 90),
          ("rounds", "rounds before long", 2, 8)]
CONFIG_DIR = db.CONFIG_DIR
STATS_FILE = CONFIG_DIR / "pomodoro.json"  # antall fullførte økter i dag
SETTINGS_FILE = CONFIG_DIR / "pomodoro-settings.json"

PHASE_NAMES = {"focus": "focus", "short": "break", "long": "long break"}
CAT_MODE = {"focus": "sleep", "short": "play", "long": "eat"}  # kattens animasjon mens klokka går

CSS = """
.time { font-family: "Silkscreen"; font-size: 46px; }
.bar { font-family: "Silkscreen"; font-size: 9px; letter-spacing: 1px; }
button.pixel { font-family: "Silkscreen"; font-size: 11px; border-radius: 0; box-shadow: none;
               border: 2px solid @mt_fg; background: transparent; color: @mt_fg; padding: 4px 12px; min-height: 0; }
button.pixel:hover { border-color: @mt_accent; color: @mt_accent; }
button.pixel.go { background: @mt_accent; border-color: @mt_accent; color: @mt_bg; }
"""


def notify(title, body):
    subprocess.Popen(["notify-send", "-i", "appointment-soon", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def label(text, *classes):
    lbl = Gtk.Label(label=_(text), xalign=0)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


class PomodoroPanel(Gtk.Box):
    def __init__(self, cat, palette, on_change=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.cat = cat  # tittel-katten i hovedvinduet
        self.palette = palette
        self.on_change = on_change  # kalles hvert kvartsekund, f.eks. for å vise tiden på knappen
        self.settings = self.load_settings()
        self.phase = "focus"
        self.remaining = self.full_remaining = timedelta(minutes=self.settings["focus"])
        self.ends_at = None  # satt når klokka går (veggklokke, så den tåler at maskinen sover)
        self.done_in_cycle = 0
        self.today = self.load_stats()
        self.stats_date = date.today()

        head = Gtk.Box(margin_bottom=4)
        head.append(label("pomodoro", "big"))
        self.phase_lbl = label("", "detail", "muted")
        self.phase_lbl.set_hexpand(True)
        self.phase_lbl.set_xalign(1)
        head.append(self.phase_lbl)
        self.append(head)

        self.time = label("25:00", "time")
        self.time.set_xalign(0.5)
        self.time.set_margin_top(12)
        self.append(self.time)
        self.bar = Gtk.Label(use_markup=True)
        self.bar.add_css_class("bar")
        self.append(self.bar)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=8)
        self.start_btn = self.button("start", self.on_start, "go")
        buttons.append(self.start_btn)
        buttons.append(self.button("reset", self.on_reset))
        buttons.append(self.button("skip", self.on_skip))
        self.append(buttons)

        self.sessions = label("", "detail", "muted")
        self.sessions.set_xalign(0.5)
        self.sessions.set_margin_top(6)
        self.append(self.sessions)

        # Innstillinger (skjult til du trykker «settings»)
        toggle = Gtk.ToggleButton(label=_("settings ▸"), halign=Gtk.Align.CENTER, margin_top=6)
        toggle.add_css_class("flat")
        grid = Gtk.Grid(row_spacing=6, column_spacing=12, margin_top=6, halign=Gtk.Align.CENTER)
        for row, (key, text, lo, hi) in enumerate(FIELDS):
            grid.attach(label(text, "detail", "muted"), 0, row, 1, 1)
            spin = Gtk.SpinButton.new_with_range(lo, hi, 1)
            spin.set_value(self.settings[key])
            spin.connect("value-changed", self.on_setting_changed, key)
            grid.attach(spin, 1, row, 1, 1)
        revealer = Gtk.Revealer(child=grid, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        toggle.connect("toggled", lambda b: (revealer.set_reveal_child(b.get_active()),
                                             b.set_label(_("settings ▾") if b.get_active() else _("settings ▸"))))
        self.append(toggle)
        self.append(revealer)

        self.refresh()
        GLib.timeout_add(250, self.tick)

    def button(self, text, handler, *classes):
        b = Gtk.Button(label=_(text))
        b.add_css_class("pixel")
        for c in classes:
            b.add_css_class(c)
        b.connect("clicked", handler)
        return b

    # --- innstillinger ---
    def load_settings(self):
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except (OSError, ValueError):
            saved = {}
        return {k: int(saved.get(k, v)) for k, v in DEFAULTS.items()}

    def on_setting_changed(self, spin, key):
        self.settings[key] = int(spin.get_value())
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings))
        except OSError:
            pass
        # Står klokka urørt i denne fasen, får den den nye tiden med en gang; ellers gjelder den fra neste fase
        if key == self.phase and not self.running() and not self.started():
            self.remaining = self.full_remaining = timedelta(minutes=self.settings[key])
        self.refresh()

    def started(self):
        """Er det gått tid i denne fasen (pauset midt i)?"""
        return self.remaining != self.full_remaining

    # --- statistikk ---
    def load_stats(self):
        try:
            data = json.loads(STATS_FILE.read_text())
            return data["count"] if data.get("date") == date.today().isoformat() else 0
        except (OSError, ValueError, KeyError):
            return 0

    def save_stats(self):
        try:
            STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATS_FILE.write_text(json.dumps({"date": date.today().isoformat(), "count": self.today}))
        except OSError:
            pass

    # --- klokke ---
    def running(self):
        return self.ends_at is not None

    def left(self):
        return max(timedelta(0), self.ends_at - datetime.now()) if self.running() else self.remaining

    def clock(self):
        secs = int(self.left().total_seconds() + 0.999)
        return f"{secs // 60:02d}:{secs % 60:02d}"

    def tick(self):
        if self.running() and self.left() <= timedelta(0):
            self.finish_phase()
        self.refresh()
        return True

    def roll_over_day(self):
        """Står vinduet åpent over midnatt, begynner tellingen på nytt for den nye dagen."""
        if date.today() != self.stats_date:
            self.stats_date = date.today()
            self.today = 0
            self.done_in_cycle = 0

    def finish_phase(self):
        self.roll_over_day()
        if self.phase == "focus":
            self.today += 1
            self.done_in_cycle += 1
            self.save_stats()
            nxt = "long" if self.done_in_cycle % self.settings["rounds"] == 0 else "short"
            notify(_("🍅 Focus done"), _("Time for a {n} min break.").format(n=self.settings[nxt]))
            self.set_phase(nxt, autostart=True)  # pausen starter av seg selv
            self.cat.react("break", 3)
        else:
            notify(_("🍅 Break over"), _("Ready for the next focus session?"))
            self.set_phase("focus", autostart=False)  # fokus starter når du trykker start
            self.cat.react("focus", 3)

    def set_phase(self, phase, autostart):
        self.phase = phase
        self.remaining = timedelta(minutes=self.settings[phase])
        self.full_remaining = self.remaining
        self.ends_at = datetime.now() + self.remaining if autostart else None

    def refresh(self):
        self.roll_over_day()
        left = self.left()
        self.time.set_label(self.clock())
        total = self.full_remaining.total_seconds()
        filled = max(0, min(20, round(20 * (1 - left.total_seconds() / total))))
        pal = self.palette()
        self.bar.set_markup(
            f'<span foreground="{pal["accent"]}">{"■" * filled}</span>'
            f'<span foreground="{pal["line"]}">{"■" * (20 - filled)}</span>'
        )
        rounds = self.settings["rounds"]
        dots = "■" * (self.done_in_cycle % rounds) + "□" * (rounds - self.done_in_cycle % rounds)
        self.sessions.set_label(_("{dots}   today: {n}").format(dots=dots, n=self.today))
        self.phase_lbl.set_label(_(PHASE_NAMES[self.phase]) + ("" if self.running() else _(" · paused") if self.started() else ""))
        self.start_btn.set_label(_("pause") if self.running() else _("start"))
        # Katten følger pomodoroen mens den går; ellers vanlige animasjoner
        self.cat.mode = CAT_MODE[self.phase] if self.running() else None
        if self.on_change:
            self.on_change(self)

    # --- knapper ---
    def on_start(self, _):
        if self.running():
            self.remaining = self.left()
            self.ends_at = None
        else:
            self.ends_at = datetime.now() + self.remaining
            if self.phase == "focus":
                self.cat.react("start")
        self.refresh()

    def on_reset(self, _):
        self.set_phase(self.phase, autostart=False)
        self.refresh()

    def on_skip(self, _):
        self.set_phase("short" if self.phase == "focus" else "focus", autostart=False)
        self.refresh()
