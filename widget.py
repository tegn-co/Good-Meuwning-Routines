#!/usr/bin/env python3
"""Lite, flyttbart morgen-todo-vindu (GTK4). Lagrer i SQLite via db.py (se der for hvor databasen ligger)."""
import json
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from cat import CatRoamer, TitleCat  # noqa: E402
from pomodoro import CSS as POMODORO_CSS, PomodoroPanel  # noqa: E402
from cat_settings import CatSettings  # noqa: E402
import cat as catmod  # noqa: E402
import db  # noqa: E402
import schedule  # noqa: E402
from onboarding import Onboarding  # noqa: E402

SAVE_DELAY = 10  # sekunder uten endringer før lagring
MAIN_H = 600  # vinduet starter alltid i MAIN_W × MAIN_H med sidepanelet lukket
MAIN_W, SIDE_W = 360, 317  # bredde på hovedlisten og plan-panelet (inkl. marger og kant)

ITEMS = [
    ("email", "Check email", ["Reply to anything urgent, flag the rest", "Add new tasks to today's plan"]),
    ("jira", "Go through Jira tickets", ["Tickets assigned to me – status and priority", "New comments and mentions", "Anything blocked or waiting on me?"]),
    ("calendar", "Check today's meetings", ["Add each meeting under item 04"]),
    ("prep", "Prepare for your meetings", []),
    ("plan", "Make a short plan for the day", ["The 1–3 most important things today", "Focus time between meetings", "What can wait until tomorrow?", "Start each task with - to check it off under plan ▸"]),
]
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
PREP = ["Read the agenda", "Review notes from the last meeting", "Open relevant documents / tickets", "Write down questions and input"]

CSS = """
window, .bg { background: @mt_bg; color: @mt_fg; font-family: "JetBrains Mono"; font-size: 12px; }
headerbar { background: @mt_bg; box-shadow: none; border: none; min-height: 32px; }
.pixel { font-family: "Silkscreen"; }
.muted { color: @mt_muted; }
.num { font-family: "Silkscreen"; font-size: 10px; color: @mt_muted; }
.title { font-weight: 500; font-size: 13px; }
.done .title { color: @mt_muted; }
.detail { color: @mt_muted; font-size: 11px; }
.item { border-top: 1px solid @mt_line; padding: 10px 0; }
.blocks { font-family: "Silkscreen"; letter-spacing: 2px; }
.off { color: @mt_line; }
.err { color: @mt_accent; }
.side { border-left: 1px solid @mt_line; }
.item.drop-above { box-shadow: inset 0 2px @mt_accent; }
.item.drop-below { box-shadow: inset 0 -2px @mt_accent; }
.handle:hover { color: @mt_accent; }
button.danger { color: @mt_accent; }
.setrow { border-top: 1px solid @mt_line; padding: 6px 0; }
.side checkbutton label { font-size: 13px; }
.side checkbutton:checked label { color: @mt_muted; }
.hours { border-top: 1px solid @mt_line; border-bottom: 1px solid @mt_line; padding: 12px 0; margin-top: 4px; }
.hours.attention { border-color: @mt_accent; }
.big { font-family: "Silkscreen"; font-size: 18px; }
.plus { color: @mt_accent; }
spinbutton { background: transparent; border: 1px solid @mt_line; border-radius: 0; box-shadow: none; }
checkbutton check { border-radius: 0; border: 2px solid @mt_fg; background: transparent; min-width: 12px; min-height: 12px; box-shadow: none; }
checkbutton check:checked { background: @mt_accent; border-color: @mt_accent; color: @mt_bg; }
entry, textview, textview text { background: transparent; color: @mt_fg; border-radius: 0; box-shadow: none; }
entry { border: none; border-bottom: 1px solid @mt_line; min-height: 26px; }
.planbox { border: 1px solid @mt_line; padding: 6px; }
button.flat { font-family: "Silkscreen"; font-size: 10px; color: @mt_muted; padding: 2px 4px; min-height: 0; }
button.flat:hover { color: @mt_accent; background: transparent; }
"""

# Fargepaletter for lys og mørk modus (brukes som @mt_* i CSS-en over)
PALETTES = {
    "light": {"bg": "#f4f4f0", "fg": "#111111", "muted": "#8a8a85", "line": "#dcdcd6", "accent": "#ff4f1f"},
    "dark": {"bg": "#0e0e0e", "fg": "#ededea", "muted": "#6b6b66", "line": "#262624", "accent": "#ff6a3d"},
}
THEME_FILE = db.CONFIG_DIR / "theme"
THEMES = [("system", "◐", Adw.ColorScheme.DEFAULT), ("light", "☀", Adw.ColorScheme.FORCE_LIGHT), ("dark", "☾", Adw.ColorScheme.FORCE_DARK)]


def palette():
    return PALETTES["dark" if Adw.StyleManager.get_default().get_dark() else "light"]


def set_struck(lbl, text, on):
    """Gjennomstreking settes i selve teksten (ikke via CSS), så den alltid forsvinner igjen når
    avkryssingen fjernes – GTK tegnet ikke alltid om teksten når bare CSS-streken skulle bort."""
    escaped = GLib.markup_escape_text(text)
    lbl.set_markup(f"<s>{escaped}</s>" if on else escaped)


def label(text, *classes, wrap=False):
    lbl = Gtk.Label(label=text, xalign=0, wrap=wrap)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


class Widget(Adw.ApplicationWindow):
    def __init__(self, app, cat=None):
        super().__init__(application=app, title="Morning Routine", default_width=MAIN_W, default_height=MAIN_H)
        self.state = {"checks": {}, "plan": "", "meetings": [], "hours": None, "day_off": False, "routine": [], "order": [], "hidden": []}
        self.save_id = 0
        self.loading = True

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("bg")
        header = Adw.HeaderBar(show_title=False)
        # Bytt mellom system / lys / mørk modus
        self.theme_btn = Gtk.Button()
        self.theme_btn.add_css_class("flat")
        self.theme_btn.connect("clicked", lambda _: app.cycle_theme())
        header.pack_start(self.theme_btn)
        # Åpner/lukker pomodoro-panelet; viser gjenstående tid mens klokka går
        self.pomo_btn = Gtk.ToggleButton(label="pomo", tooltip_text="Pomodoro timer")
        self.pomo_btn.add_css_class("flat")
        self.pomo_btn.connect("toggled", self.on_side_toggled, "pomo")
        header.pack_start(self.pomo_btn)
        # Åpner/lukker katteinnstillingene
        self.cat_btn = Gtk.ToggleButton(label="cat", tooltip_text="Customize the cat")
        self.cat_btn.add_css_class("flat")
        self.cat_btn.connect("toggled", self.on_side_toggled, "cat")
        header.pack_start(self.cat_btn)
        # Innstillinger: her slettes punkter (ikke i selve listen, så ingenting forsvinner ved et feiltrykk)
        self.settings_btn = Gtk.ToggleButton(label="⚙", tooltip_text="Settings")
        self.settings_btn.add_css_class("flat")
        self.settings_btn.connect("toggled", self.on_side_toggled, "settings")
        header.pack_start(self.settings_btn)
        root.append(header)

        self.scroll = scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=MAIN_W)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=18, margin_end=18, margin_bottom=14)
        scroll.set_child(body)
        main = Gtk.Box()
        main.append(scroll)

        # --- Sidepanel med to sider: dagens plan og pomodoro-klokka ---
        self.side_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, width_request=280,
                                    margin_start=18, margin_end=18)
        # Plan: punkt 05 som todo-liste (linjer som starter med "-")
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side_head = Gtk.Box(margin_bottom=12)
        side_head.append(label("today's plan", "big"))
        self.plan_count = label("", "blocks", "muted")
        self.plan_count.set_hexpand(True)
        self.plan_count.set_xalign(1)
        side_head.append(self.plan_count)
        side.append(side_head)
        self.plan_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        side.append(self.plan_list)
        self.plan_hint = label("Write lines starting with - in 05 to add them here", "detail", "muted", wrap=True)
        side.append(self.plan_hint)
        # EXTERNAL: panelet kan bli smalere enn innholdet, så vindusbredden alene bestemmer hvor mye som vises
        self.side = Gtk.ScrolledWindow(vexpand=True, hexpand=True, visible=False,
                                       hscrollbar_policy=Gtk.PolicyType.EXTERNAL)
        self.side_stack.add_named(side, "plan")
        # Clamp: sidene får aldri mer enn panelets bredde, så lange tekster brytes i stedet for å sprenge panelet
        self.side.set_child(Adw.Clamp(child=self.side_stack, maximum_size=SIDE_W - 1, tightening_threshold=SIDE_W - 1))
        self.side.add_css_class("side")
        main.append(self.side)
        # Én animasjon styrer vindusbredden, så panelet glir ut/inn sammen med vinduskanten
        self.side_anim = Adw.TimedAnimation.new(
            self, MAIN_W, MAIN_W + SIDE_W, 220,
            Adw.CallbackAnimationTarget.new(self.resize_to_width),
        )
        self.side_anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.side_anim.connect("done", self.on_side_anim_done)
        # Katten tegnes i et gjennomsiktig lag over hele innholdet, så den kan klatre rundt rammen
        self.overlay = Gtk.Overlay(child=main)
        root.append(self.overlay)
        self.set_content(root)

        # Tittelen «good morning» med pixel-katten som lever oppå bokstavene
        self.title_cat = TitleCat(palette, forced=cat)
        body.append(self.title_cat)
        CatRoamer(self.title_cat, self.overlay)  # legger seg selv i overlay-et
        self.pomodoro = PomodoroPanel(self.title_cat, palette, on_change=self.on_pomodoro_change)
        self.side_stack.add_named(self.pomodoro, "pomo")
        self.cat_settings = CatSettings(self.title_cat)
        self.side_stack.add_named(self.cat_settings, "cat")
        self.side_stack.add_named(self.build_settings(), "settings")

        meta = Gtk.Box(margin_bottom=16)
        self.date_lbl = label("", "muted", "detail")
        meta.append(self.date_lbl)
        self.streak_lbl = label("", "detail", "muted")  # «3 days in a row»
        self.streak_lbl.set_margin_start(10)
        meta.append(self.streak_lbl)
        self.blocks = Gtk.Label(use_markup=True, hexpand=True, xalign=1)
        self.blocks.add_css_class("blocks")
        meta.append(self.blocks)
        body.append(meta)

        # Alle punktene (faste og rutine) ligger i én liste som kan sorteres ved å dra i nummeret
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.list_box)
        self.items = {}
        self.titles = {}  # tittel-etiketten til de faste punktene (gjennomstrekes når de er krysset av)
        self.nums = {}  # nummer-etiketten per punkt (oppdateres når rekkefølgen endres)
        self.routine_widgets = {}
        for i, (key, text, details) in enumerate(ITEMS, 1):
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            item.add_css_class("item")
            row = Gtk.Box(spacing=10)
            row.append(self.drag_handle(key, item))
            self.titles[key] = label(text, "title", wrap=True)
            row.append(self.titles[key])
            check = Gtk.CheckButton(hexpand=True, halign=Gtk.Align.END)
            check.connect("toggled", self.on_item_toggled, key)
            if key == "plan":
                # Åpner/lukker sidepanelet med planpunktene; ligger i raden så den er synlig også når 05 er krysset av
                self.side_btn = Gtk.ToggleButton(label="plan ▸")
                self.side_btn.add_css_class("flat")
                self.side_btn.connect("toggled", self.on_side_toggled, "plan")
                check.set_hexpand(False)
                self.side_btn.set_hexpand(True)
                self.side_btn.set_halign(Gtk.Align.END)
                row.append(self.side_btn)
            row.append(check)
            item.append(row)

            extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=30, margin_top=4)
            for d in details:
                extra.append(label(f"› {d}", "detail", wrap=True))
            if key == "prep":
                self.meeting_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                extra.append(self.meeting_box)
                add = Gtk.Button(label="+ add meeting", halign=Gtk.Align.START)
                add.add_css_class("flat")
                add.connect("clicked", self.on_add_meeting)
                extra.append(add)
            if key == "plan":
                self.plan = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=90, top_margin=4, left_margin=4)
                frame = Gtk.Box(margin_top=8)
                frame.add_css_class("planbox")
                self.plan.set_hexpand(True)
                frame.append(self.plan)
                extra.append(frame)
                self.plan.get_buffer().connect("changed", self.on_plan_changed)
            item.append(extra)
            self.make_drop_target(item, key)
            self.items[key] = (item, check, extra)

        # --- Egne rutinepunkter kommer tilbake hver dag; legges til her ---
        add_row = Gtk.Box(spacing=10, margin_top=6, margin_bottom=10)
        add_row.append(label("+", "num"))
        self.new_todo = Gtk.Entry(placeholder_text="add to routine and press enter", hexpand=True)
        self.new_todo.connect("activate", self.on_add_todo)
        add_row.append(self.new_todo)
        body.append(add_row)

        # --- Timeføring (påminnelse kl 15:00) ---
        self.hours_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.hours_box.add_css_class("hours")
        row = Gtk.Box(spacing=10)
        row.append(label("⏱", "num"))
        row.append(label("Hours worked today", "title"))
        self.hours = Gtk.SpinButton.new_with_range(0, 24, 0.25)
        self.hours.set_digits(2)
        self.hours.set_hexpand(True)
        self.hours.set_halign(Gtk.Align.END)
        self.hours.connect("value-changed", self.on_hours_changed)
        # Enter fører timene selv om tallet ikke endret seg (ellers kan man ikke føre nøyaktig 0)
        self.hours.connect("activate", lambda spin: self.state["hours"] is None and self.on_hours_changed(spin))
        row.append(self.hours)
        self.hours_box.append(row)
        self.today_diff = label("", "detail")
        self.today_diff.set_margin_start(30)
        self.hours_box.append(self.today_diff)
        self.day_off = Gtk.CheckButton(label="day off (vacation, sick, holiday)", margin_start=26)
        self.day_off.add_css_class("detail")
        self.day_off.connect("toggled", self.on_day_off_changed)
        self.hours_box.append(self.day_off)
        bal = Gtk.Box(margin_start=30, spacing=16)
        self.bal_total = label("", "big")
        bal.append(self.bal_total)
        self.bal_detail = label("", "detail", "muted")
        bal.append(self.bal_detail)
        self.hours_box.append(bal)
        body.append(self.hours_box)

        self.footer = label("", "pixel", "muted", "detail")
        self.footer.set_xalign(0.5)
        self.footer.set_margin_top(14)
        body.append(self.footer)
        self.status = label("", "detail", "muted")
        self.status.set_xalign(0.5)
        body.append(self.status)

        self.connect("close-request", self.on_close)
        self.db = db.Worker()
        self.loaded = False  # ingenting lagres før dagens data er lest (ellers kan tom liste overskrive alt)
        self.size_delta = 0  # standardstørrelse minus synlig størrelse (se resize_to_width)
        self.connect("map", lambda *_: GLib.timeout_add(150, self.fix_start_size))
        self.day = date.today()
        self.load()

        self.apply_schedule(schedule.load())
        # Sjekk veggklokka hvert 30. sekund (en vanlig timer stopper når maskinen sover)
        GLib.timeout_add_seconds(30, self.check_clock)

    def apply_schedule(self, sch):
        """Ta i bruk tidene fra ⚙ → schedule i vinduet (lukketid og kattens lunsj)."""
        self.schedule = sch
        start, end = schedule.parse(sch["lunch"]), schedule.parse(sch["lunch_end"])
        catmod.LUNCH = (start.hour * 60 + start.minute, end.hour * 60 + end.minute)
        # Neste lukketid etter at vinduet ble åpnet eller tiden ble endret (har den passert, gjelder den i morgen)
        self.close_at = None
        if sch["close_on"]:
            self.close_at = datetime.combine(date.today(), schedule.parse(sch["close"]))
            if datetime.now() >= self.close_at:
                self.close_at += timedelta(days=1)

    # --- streaks og humør ---
    def refresh_streak(self):
        self.db.submit(db.streak_info, self.day, bool(self.state.get("complete")), callback=self.show_streak)

    def show_streak(self, info, err):
        if err or not info:
            return
        n = info["streak"]
        self.streak_lbl.set_label(f"· {n} day{'s' if n != 1 else ''} in a row" if n >= 2 else "")
        (self.streak_lbl.add_css_class if self.state.get("complete") else self.streak_lbl.remove_css_class)("plus")
        unlocked = {k for k, days, _ in catmod.UNLOCKS if info["best"] >= days}
        new = unlocked - catmod.UNLOCKED
        first = not hasattr(self, "streak_seen")  # ved oppstart: ingen feiring for det man allerede har
        catmod.UNLOCKED.clear()
        catmod.UNLOCKED.update(unlocked)
        self.cat_settings.refresh_wear()
        if not first and new:
            name = next(label for k, _, label in catmod.UNLOCKS if k in new)
            self.title_cat.say(f"unlocked: {name}!", 3)
        elif not first and self.state.get("complete") and n >= 2 and n != getattr(self, "streak_seen", 0):
            self.title_cat.say(f"{n} days in a row!", 3)
        self.streak_seen = n

    def mood(self):
        """Katten reagerer på hvordan dagen går (sjekkes hvert 30. sekund)."""
        if not self.loaded or self.pomodoro.running() or random.random() > 0.12:
            return
        now = datetime.now()
        keys = self.order()
        done = sum(bool(self.state["checks"].get(k)) for k in keys)
        if done == 0 and now.hour >= 10:
            self.title_cat.say(random.choice(["meow?", "*stares at list*", "mrrp?"]), 2)
        elif keys and done == len(keys):
            self.title_cat.say("", 0)  # bare et hjerte: fornøyd katt

    def check_clock(self):
        self.check_new_day()
        self.mood()
        if self.close_at is None or datetime.now() < self.close_at:
            return True
        # Lagre først; lukk bare hvis lagringen gikk bra, ellers prøv igjen om 30 sekunder
        if not self.loaded:
            return True
        self.hours.update()
        self.save_now(then=self.close)
        return True

    def check_new_day(self):
        """Står vinduet åpent over midnatt, lagres gårsdagen og dagens liste lastes (med overførte planpunkter)."""
        if date.today() == self.day or getattr(self, "changing_day", False):
            return

        def go():
            self.changing_day = False
            self.day = date.today()
            self.load()

        def retry():
            self.changing_day = False  # gårsdagen ble ikke lagret; check_clock prøver igjen om 30 s

        if self.loaded:
            self.changing_day = True
            self.hours.update()
            self.save_now(then=go, failed=retry)
        else:
            go()

    def on_close(self, _):
        # Lagre før vinduet lukkes og vent på databasen (maks 10 s), også om en lagring allerede er i gang.
        # Ellers kan bakgrunnstråden bli avbrutt midt i skrivingen når appen avslutter.
        if self.loaded:
            self.hours.update()  # tall skrevet i timefeltet uten Enter
            if self.save_id:
                GLib.source_remove(self.save_id)
                self.save_id = 0
            try:
                self.db.run_sync(db.save_day, self.day, self.snapshot())
            except Exception:
                pass
        return False

    # --- data (all databasetilgang går via self.db, en bakgrunnstråd) ---
    def snapshot(self):
        return json.loads(json.dumps(self.state))  # kopi, så tråden ikke leser en liste som endres

    def set_status(self, ok, text):
        self.status.set_label(text)
        (self.status.remove_css_class if ok else self.status.add_css_class)("err")

    def load(self):
        self.loaded = False
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = 0
        d = self.day
        self.date_lbl.set_label(f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}")
        self.set_status(True, "○ loading…")
        self.scroll.set_sensitive(False)  # det som skrives nå, ville blitt erstattet når dataene kommer
        self.db.submit(db.load_day, d, callback=lambda result, err: self.on_loaded(d, result, err))

    def on_loaded(self, day, result, err):
        if day != self.day:
            return  # svar for en dag vi har gått videre fra
        if err:
            # Ikke la brukeren endre noe som ikke kan lagres trygt; prøv igjen om litt
            self.scroll.set_sensitive(False)
            self.set_status(False, f"● could not read the database – retrying in 30 s ({err})")
            GLib.timeout_add_seconds(30, lambda: (self.load() if not self.loaded and day == self.day else None) and False)
            return
        self.state = {"checks": {}, "plan": "", "meetings": [], "hours": None, "day_off": False,
                      "routine": [], "order": [], "hidden": []}
        self.state.update(result)
        self.loading = True
        for key, (_, check, _) in self.items.items():
            check.set_active(bool(self.state["checks"].get(key)))
        self.plan.get_buffer().set_text(self.state["plan"])
        self.render_meetings()
        self.render_routine()
        self.render_plan_items()
        self.hours.set_value(self.state["hours"] or 0)
        self.day_off.set_active(self.state["day_off"])
        self.loading = False
        self.loaded = True
        self.scroll.set_sensitive(True)
        self.set_status(True, "● saved")
        self.update_progress()
        self.update_hours()
        self.refresh_streak()

    def save(self):
        if self.loading or not self.loaded:
            return
        self.set_status(True, "○ unsaved changes")
        if self.save_id:
            GLib.source_remove(self.save_id)
        # Vent til det har vært stille i SAVE_DELAY sekunder før vi skriver til databasen
        self.save_id = GLib.timeout_add_seconds(SAVE_DELAY, self.save_now)

    def save_now(self, then=None, failed=None):
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = 0
        if not self.loaded:
            return False
        day = self.day

        def done(_, err):
            if err:
                self.set_status(False, f"● not saved – {err}")
                if failed:
                    failed()
                return
            if day == self.day:
                self.set_status(True, "● saved")
                self.update_hours()
                self.refresh_streak()
            if then:
                then()

        self.db.submit(db.save_day, day, self.snapshot(), callback=done)
        return False

    # --- UI ---
    def update_progress(self):
        keys = self.order()
        done = sum(bool(self.state["checks"].get(k)) for k in keys)
        total = len(keys)
        self.blocks.set_markup("■" * done + f'<span foreground="{palette()["line"]}">{"■" * (total - done)}</span>')
        self.footer.set_label("[ all done – have a great day ]" if done == total else f"{done}/{total}")
        # Hele listen ferdig akkurat nå (ikke når den lastes inn ferdig)
        if done == total and not getattr(self, "all_done", True) and not self.loading:
            self.title_cat.react("all_done", 3)
        self.all_done = done == total
        self.state["complete"] = total > 0 and done == total  # lagres per dag, brukes til streaks
        for key, (item, check, extra) in self.items.items():
            on = check.get_active()
            (item.add_css_class if on else item.remove_css_class)("done")
            set_struck(self.titles[key], dict((k, t) for k, t, _ in ITEMS)[key], on)
            extra.set_visible(not on)

    def update_hours(self):
        self.db.submit(db.summary, self.day, callback=self.show_hours)

    def show_hours(self, sm, err):
        if sm and not err:
            self.last_summary = sm
        fmt = lambda h: f"{h:+.2f} h"
        h = self.state.get("hours")
        expected = db.expected_for(self.day, self.state.get("day_off"))
        if h is None:
            self.today_diff.set_label(f"not logged yet · expected {expected:g} h")
        else:
            self.today_diff.set_label(f"today {fmt(h - expected)} vs {expected:g} h")
        if sm and not err:
            self.bal_total.set_label(fmt(sm["total"]))
            (self.bal_total.add_css_class if sm["total"] > 0 else self.bal_total.remove_css_class)("plus")
            self.bal_detail.set_label(f"overtime balance\nweek {fmt(sm['week'])} · month {fmt(sm['month'])}")

    def focus_hours(self):
        """Kalles kl 15:00: marker timeføringen og sett fokus på feltet."""
        self.hours_box.add_css_class("attention")
        self.hours.grab_focus()
        GLib.idle_add(lambda: self.scroll_to(self.hours_box))

    def scroll_to(self, widget):
        adj = self.scroll.get_vadjustment()
        ok, point = widget.compute_point(self.scroll.get_child(), Graphene.Point())
        if ok:
            adj.set_value(point.y - 20)
        return False

    def on_day_off_changed(self, check):
        if self.loading:
            return
        self.state["day_off"] = check.get_active()
        self.show_hours(None, None)
        self.save()

    def on_hours_changed(self, spin):
        if self.loading:
            return
        self.state["hours"] = spin.get_value()
        self.hours_box.remove_css_class("attention")
        self.show_hours(None, None)
        self.save()

    # --- rekkefølge og dra-og-slipp ---
    def order(self):
        """Alle punktnøklene i visningsrekkefølge; nye punkter havner nederst."""
        keys = [k for k in self.items if k not in self.state["hidden"]] + [f"r:{r['id']}" for r in self.state["routine"]]
        saved = [k for k in self.state["order"] if k in keys]
        return saved + [k for k in keys if k not in saved]

    def render_list(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        for n, key in enumerate(self.order(), 1):
            widget = self.items[key][0] if key in self.items else self.routine_widgets[key]
            self.list_box.append(widget)
            self.nums[key].set_label(f"{n:02d}")
        self.render_settings()

    def drag_handle(self, key, item):
        """Nummeret («01») er håndtaket du drar punktet etter."""
        num = label("", "num", "handle")
        num.set_cursor_from_name("grab")
        num.set_tooltip_text("Drag to reorder")
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(key))
        source.connect("drag-begin", lambda src, _: src.set_icon(Gtk.WidgetPaintable.new(item), 0, 0))
        num.add_controller(source)
        self.nums[key] = num
        return num

    def make_drop_target(self, item, key):
        target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

        def where(y):
            return "drop-above" if y < item.get_height() / 2 else "drop-below"

        def motion(_, x, y):
            item.remove_css_class("drop-above")
            item.remove_css_class("drop-below")
            item.add_css_class(where(y))
            return Gdk.DragAction.MOVE

        def leave(_):
            item.remove_css_class("drop-above")
            item.remove_css_class("drop-below")

        def drop(_, dragged, x, y):
            leave(None)
            self.move_item(dragged, key, after=where(y) == "drop-below")
            return True

        target.connect("motion", motion)
        target.connect("leave", leave)
        target.connect("drop", drop)
        item.add_controller(target)

    def move_item(self, dragged, target, after):
        order = self.order()
        if dragged == target or dragged not in order or target not in order:
            return  # f.eks. tekst dratt inn fra et tekstfelt
        order.remove(dragged)
        order.insert(order.index(target) + (1 if after else 0), dragged)
        self.state["order"] = order
        self.render_list()
        self.save()

    def render_routine(self):
        self.routine_widgets = {}
        for i, r in enumerate(self.state["routine"]):
            key = f"r:{r['id']}"
            done = bool(self.state["checks"].get(key))
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            item.add_css_class("item")
            if done:
                item.add_css_class("done")
            row = Gtk.Box(spacing=10)
            row.append(self.drag_handle(key, item))
            title = label(r["text"], "title", wrap=True)
            set_struck(title, r["text"], done)
            title.set_hexpand(True)
            row.append(title)
            check = Gtk.CheckButton(active=done)
            check.connect("toggled", self.on_todo_toggled, key)
            row.append(check)
            item.append(row)
            self.make_drop_target(item, key)
            self.routine_widgets[key] = item
        self.render_list()

    def on_add_todo(self, entry):
        text = entry.get_text().strip()
        if not text:
            return
        self.state["routine"].append({"id": uuid.uuid4().hex[:8], "text": text})
        entry.set_text("")
        self.render_routine()
        self.update_progress()
        self.save()

    # --- settings: slette og gjenopprette punkter ---
    def build_settings(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head = Gtk.Box()
        head.append(label("settings", "big"))
        tutorial = Gtk.Button(label="show tutorial", hexpand=True, halign=Gtk.Align.END)
        tutorial.add_css_class("flat")
        tutorial.connect("clicked", lambda _: self.show_onboarding())
        head.append(tutorial)
        page.append(head)
        heading = label("todos", "num")
        heading.set_margin_top(10)
        page.append(heading)
        page.append(label("Delete asks for a second click to confirm.", "detail", "muted", wrap=True))
        self.settings_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(self.settings_list)
        self.deleted_heading = label("deleted default items", "num")
        self.deleted_heading.set_margin_top(14)
        page.append(self.deleted_heading)
        self.deleted_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(self.deleted_list)

        # Timer for en annen dag (glemt å føre, eller må rette)
        page.append(self.build_schedule())

        heading = label("hours for another day", "num")
        heading.set_margin_top(14)
        page.append(heading)
        self.past_cal = Gtk.Calendar()
        self.past_cal.connect("day-selected", self.on_past_day_selected)
        page.append(self.past_cal)
        row = Gtk.Box(spacing=8)
        self.past_hours = Gtk.SpinButton.new_with_range(0, 24, 0.25)
        self.past_hours.set_digits(2)
        row.append(self.past_hours)
        self.past_off = Gtk.CheckButton(label="day off")
        self.past_off.add_css_class("detail")
        row.append(self.past_off)
        save = self.past_save_btn = Gtk.Button(label="save", hexpand=True, halign=Gtk.Align.END, sensitive=False)
        save.add_css_class("flat")
        save.connect("clicked", self.on_past_save)
        row.append(save)
        page.append(row)
        self.past_status = label("", "detail", "muted", wrap=True)
        page.append(self.past_status)
        GLib.idle_add(lambda: self.on_past_day_selected(self.past_cal) and False)
        return page

    def build_schedule(self):
        """⚙ → schedule: når listen åpnes, påminnelser, lukketid, lunsj og ukedager."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        heading = label("schedule", "num")
        heading.set_margin_top(14)
        box.append(heading)
        sch = schedule.load()
        self.sched_widgets = {}  # nøkkel -> (av/på-knapp eller None, time, minutt)
        self.day_btns = {}  # påminnelse -> sju ukedagsknapper

        def time_picker(key):
            t = schedule.parse(sch[key])
            hh = Gtk.SpinButton.new_with_range(0, 23, 1)
            mm = Gtk.SpinButton.new_with_range(0, 59, 5)
            for spin, value in ((hh, t.hour), (mm, t.minute)):
                spin.set_value(value)
                spin.set_wrap(True)
                # Loddrett (+ over, − under) og to tegn bred, så fire felt får plass i sidepanelet
                spin.set_orientation(Gtk.Orientation.VERTICAL)
                spin.set_width_chars(2)
                spin.connect("output", lambda sp: sp.set_text(f"{int(sp.get_value()):02d}") or True)
            picker = Gtk.Box(spacing=2, hexpand=True, halign=Gtk.Align.END)
            picker.append(hh)
            picker.append(label(":", "detail"))
            picker.append(mm)
            return picker, hh, mm

        def row(widget, picker):
            r = Gtk.Box(spacing=8, margin_top=6)
            r.append(widget)
            r.append(picker)
            box.append(r)

        for key, text, with_days in [("morning", "open the list", True), ("hours", "remind me to log hours", True),
                                     ("close", "save & close", False)]:
            on = Gtk.CheckButton(label=text, active=sch[f"{key}_on"])
            on.add_css_class("detail")
            on.get_last_child().set_wrap(True)  # lang tekst brytes i stedet for å gjøre panelet bredere
            picker, hh, mm = time_picker(key)
            row(on, picker)
            self.sched_widgets[key] = (on, hh, mm)
            if with_days:
                days = Gtk.Box(spacing=2, margin_start=26)
                self.day_btns[key] = []
                for i, name in enumerate(schedule.DAY_NAMES):
                    b = Gtk.ToggleButton(label=name[:2], active=i in sch[f"{key}_days"])
                    b.add_css_class("flat")
                    days.append(b)
                    self.day_btns[key].append(b)
                box.append(days)

        # Lunsj fra–til
        lunch_from, lh, lm = time_picker("lunch")
        lunch_to, eh, em = time_picker("lunch_end")
        lunch_to.set_hexpand(False)
        lunch_from.append(label("–", "detail"))
        lunch_from.append(lunch_to)
        lunch_label = label("cat lunch", "detail")
        lunch_label.set_margin_start(26)
        row(lunch_label, lunch_from)
        self.sched_widgets["lunch"] = (None, lh, lm)
        self.sched_widgets["lunch_end"] = (None, eh, em)

        apply = Gtk.Button(label="apply", halign=Gtk.Align.END)
        apply.add_css_class("flat")
        apply.connect("clicked", self.on_schedule_apply)
        box.append(apply)
        self.sched_status = label("", "detail", "muted", wrap=True)
        box.append(self.sched_status)
        return box

    # --- første oppstart ---
    def show_onboarding(self):
        opening = getattr(self, "last_summary", {}).get("opening_balance", 0.0)
        self.onboarding = Onboarding(self, palette, self.on_onboarding_done, opening=opening)
        self.onboarding.present()

    def on_onboarding_done(self, opening, sch, problems):
        if opening is not None:
            self.db.submit(db.set_opening_balance, opening, callback=lambda *_: self.update_hours())
        else:
            self.update_hours()
        self.apply_schedule(sch)

        def timers_done(_, err):
            if err:
                self.set_status(False, f"● reminders could not be set – {err}")

        self.db.submit(schedule.apply_timers, sch, callback=timers_done)
        # Oppdater schedule-feltene på ⚙-siden med det som ble valgt
        for key, (on, hh, mm) in self.sched_widgets.items():
            t = schedule.parse(sch[key])
            hh.set_value(t.hour)
            mm.set_value(t.minute)
            if on is not None:
                on.set_active(sch[f"{key}_on"])
        if problems:
            self.set_status(False, "● setup: " + "; ".join(problems))
        self.title_cat.say("welcome!", 3)

    def on_schedule_apply(self, _):
        sch = dict(self.schedule)
        for key, (on, hh, mm) in self.sched_widgets.items():
            sch[key] = f"{int(hh.get_value()):02d}:{int(mm.get_value()):02d}"
            if on is not None:
                sch[f"{key}_on"] = on.get_active()
        for key, btns in self.day_btns.items():
            sch[f"{key}_days"] = [i for i, b in enumerate(btns) if b.get_active()]
        if sch["lunch_end"] <= sch["lunch"]:
            self.sched_status.set_label("not saved – lunch must end after it starts")
            return
        try:
            schedule.save(sch)
        except OSError as e:
            self.sched_status.set_label(f"not saved – {e}")
            return
        self.apply_schedule(sch)
        self.sched_status.set_label("saving…")

        def done(runs, err):
            if err:
                self.sched_status.set_label(f"saved, but reminders could not be set – {err}")
                return
            nxt = lambda v: v.rsplit(" ", 1)[0] if v != "off" else "off"
            close = f"{self.close_at:%a %H:%M}" if self.close_at else "off"
            self.sched_status.set_label(f"saved · next open: {nxt(runs['morning'])} · reminder: {nxt(runs['hours'])} · close: {close}")

        # systemctl kjøres i bakgrunnstråden, så vinduet ikke henger om systemd svarer tregt
        self.db.submit(schedule.apply_timers, sch, callback=done)

    def past_day(self):
        d = self.past_cal.get_date()
        return date(d.get_year(), d.get_month(), d.get_day_of_month())

    def on_past_day_selected(self, cal):
        day = self.past_day()
        self.past_save_btn.set_sensitive(False)  # låst til dagens verdier er hentet, så de ikke lagres på feil dag
        if day == self.day:
            self.past_status.set_label("Today: use the hours field in the list.")
            return
        self.past_status.set_label("loading…")

        def show(result, err):
            if err or day != self.past_day():
                self.past_status.set_label(f"could not read – {err}" if err else "")
                return
            self.past_hours.set_value(result["hours"] or 0)
            self.past_off.set_active(result["day_off"])
            logged = "not logged" if result["hours"] is None else f"logged {result['hours']:g} h"
            self.past_status.set_label(f"{day:%a %d %b}: {logged} · expected {db.expected_for(day, result['day_off']):g} h")
            self.past_save_btn.set_sensitive(True)

        self.db.submit(db.get_hours, day, callback=show)

    def on_past_save(self, _):
        day = self.past_day()
        if day == self.day:
            return
        hours, off = self.past_hours.get_value(), self.past_off.get_active()

        def done(_, err):
            self.past_status.set_label(f"not saved – {err}" if err else f"saved {hours:g} h for {day:%a %d %b}")
            self.update_hours()

        self.db.submit(db.set_hours, day, hours, off, callback=done)

    def item_title(self, key):
        if key in self.items:
            return dict((k, t) for k, t, _ in ITEMS)[key]
        return next(r["text"] for r in self.state["routine"] if f"r:{r['id']}" == key)

    def render_settings(self):
        for box in (self.settings_list, self.deleted_list):
            while child := box.get_first_child():
                box.remove(child)
        for n, key in enumerate(self.order(), 1):
            row = Gtk.Box(spacing=10)
            row.add_css_class("setrow")
            row.append(label(f"{n:02d}", "num"))
            title = label(self.item_title(key), "detail", wrap=True)
            title.set_hexpand(True)
            row.append(title)
            btn = Gtk.Button(label="delete", valign=Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", self.on_delete_clicked, key)
            row.append(btn)
            self.settings_list.append(row)
        hidden = [k for k in self.state["hidden"] if k in self.items]
        self.deleted_heading.set_visible(bool(hidden))
        for key in hidden:
            row = Gtk.Box(spacing=10)
            row.add_css_class("setrow")
            title = label(self.item_title(key), "detail", "muted", wrap=True)
            title.set_hexpand(True)
            row.append(title)
            btn = Gtk.Button(label="restore", valign=Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", self.on_restore, key)
            row.append(btn)
            self.deleted_list.append(row)

    def on_delete_clicked(self, btn, key):
        # Første klikk: be om bekreftelse i 3 sekunder. Andre klikk: slett.
        if btn.get_label() != "sure?":
            btn.set_label("sure?")
            btn.add_css_class("danger")
            GLib.timeout_add_seconds(3, lambda: (btn.set_label("delete"), btn.remove_css_class("danger"), False)[-1])
            return
        if key in self.items:
            self.state["hidden"] = self.state["hidden"] + [key]  # faste punkter skjules, kan gjenopprettes
        else:
            self.state["routine"] = [r for r in self.state["routine"] if f"r:{r['id']}" != key]
            self.state["order"] = [k for k in self.state["order"] if k != key]
        self.state["checks"].pop(key, None)
        self.render_routine()
        self.update_progress()
        self.save()

    def on_restore(self, _, key):
        self.state["hidden"] = [k for k in self.state["hidden"] if k != key]
        self.render_list()
        self.update_progress()
        self.save()

    def cheer(self, check):
        """Katten sier sin «check»-replikk når noe krysses av (ikke når listen lastes inn)."""
        if check.get_active() and not self.loading:
            self.title_cat.react("check")

    def on_todo_toggled(self, check, key):
        self.cheer(check)
        self.state["checks"][key] = check.get_active()
        self.render_routine()
        self.update_progress()
        self.save()

    def on_item_toggled(self, check, key):
        self.cheer(check)
        self.state["checks"][key] = check.get_active()
        self.update_progress()
        self.save()

    def on_plan_changed(self, buf):
        self.state["plan"] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if not self.loading:
            self.render_plan_items()
        self.save()

    def plan_items(self):
        lines = (l.strip() for l in self.state["plan"].splitlines())
        return [l[1:].strip() for l in lines if l.startswith("-") and l[1:].strip()]

    def render_plan_items(self):
        while child := self.plan_list.get_first_child():
            self.plan_list.remove(child)
        items = self.plan_items()
        for text in items:
            cb = Gtk.CheckButton(label=text, active=bool(self.state["checks"].get(f"p:{text}")))
            cb.get_last_child().set_wrap(True)
            set_struck(cb.get_last_child(), text, cb.get_active())
            cb.connect("toggled", self.on_plan_item_toggled, text)
            self.plan_list.append(cb)
        done = sum(bool(self.state["checks"].get(f"p:{t}")) for t in items)
        self.plan_count.set_label(f"{done}/{len(items)}" if items else "")
        self.plan_hint.set_visible(not items)

    def on_plan_item_toggled(self, cb, text):
        self.cheer(cb)
        self.state["checks"][f"p:{text}"] = cb.get_active()
        self.render_plan_items()
        self.save()

    def on_pomodoro_change(self, pomo):
        # Tiden vises på knappen mens klokka går, så du ser den selv når panelet er lukket
        self.pomo_btn.set_label(f"pomo {pomo.clock()}" if pomo.running() else "pomo")

    def side_buttons(self):
        return {"plan": self.side_btn, "pomo": self.pomo_btn, "cat": self.cat_btn, "settings": self.settings_btn}

    def on_side_toggled(self, btn, page):
        # Plan, pomodoro og katt deler sidepanelet: åpnes ett mens et annet er åpent, byttes bare innholdet
        if getattr(self, "switching", False):
            return
        others = [b for name, b in self.side_buttons().items() if name != page and b.get_active()]
        if btn.get_active():
            self.side_stack.set_visible_child_name(page)
            if others:
                self.switching = True
                for b in others:
                    b.set_active(False)
                self.switching = False
        self.side_btn.set_label("plan ◂" if self.side_btn.get_active() else "plan ▸")
        if btn.get_active() and others:
            return
        self.show_side(btn.get_active())

    def fix_start_size(self):
        """Første gang vinduet vises: sørg for at den synlige størrelsen blir MAIN_W × MAIN_H også der
        standardstørrelsen inkluderer usynlige kanter (X11 uten skygger)."""
        dw, dh = self.get_default_size()
        self.size_delta = max(0, dw - self.get_width())
        dy = max(0, dh - self.get_height())
        if (self.size_delta or dy) and not self.side.get_visible():
            self.set_default_size(MAIN_W + self.size_delta, MAIN_H + dy)
        return False

    def resize_to_width(self, width):
        """Sett synlig bredde. «Standardstørrelsen» GTK bruker kan være større enn det synlige vinduet
        (X11 uten skygger: 10 px), så forskjellen legges til, og høyden beholdes som den er."""
        dw, dh = self.get_default_size()
        self.set_default_size(round(width) + self.size_delta, dh)

    def show_side(self, opening):
        # Åpne: vinduet vokser mot høyre. Lukke: vinduet krymper fra høyre mot venstre.
        self.side_anim.pause()
        if self.get_mapped() and self.side_anim.get_state() != Adw.AnimationState.PLAYING:
            self.size_delta = max(0, self.get_default_size()[0] - self.get_width())  # oppdater, f.eks. etter tema-/skjermbytte
        if opening:
            self.side.set_visible(True)
            self.scroll.set_hexpand(False)
        self.side_anim.set_value_from(self.get_width() if self.get_mapped() else MAIN_W)
        self.side_anim.set_value_to(MAIN_W + SIDE_W if opening else MAIN_W)
        if not self.get_mapped():
            # Vinduet vises ikke ennå (oppstart): sett bredden direkte
            self.set_default_size(MAIN_W + SIDE_W if opening else MAIN_W, self.get_default_size()[1])
            self.side.set_visible(opening)
            self.scroll.set_hexpand(not opening)
            return
        self.side_anim.play()
        # Animasjonen drives av skjermoppdateringene; ligger vinduet bak et annet, kan den stå stille.
        # Er den ikke ferdig etter 0,4 s, hopp rett til slutten så panelet aldri blir stående halvveis.
        anim = self.side_anim
        GLib.timeout_add(400, lambda: anim.get_state() == Adw.AnimationState.PLAYING and anim.skip() and False)

    def on_side_anim_done(self, _):
        if not any(b.get_active() for b in self.side_buttons().values()):
            self.side.set_visible(False)
            self.scroll.set_hexpand(True)

    def on_add_meeting(self, _):
        self.state["meetings"].append({"name": "", "done": []})
        self.render_meetings()
        self.save()

    def render_meetings(self):
        while child := self.meeting_box.get_first_child():
            self.meeting_box.remove(child)
        for i, m in enumerate(self.state["meetings"]):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            head = Gtk.Box(spacing=4)
            name = Gtk.Entry(text=m["name"], placeholder_text="10:00 sprint review", hexpand=True)
            name.connect("changed", lambda e, m=m: (m.__setitem__("name", e.get_text()), self.save()))
            head.append(name)
            rm = Gtk.Button(label="×")
            rm.add_css_class("flat")
            rm.connect("clicked", self.on_remove_meeting, i)
            head.append(rm)
            box.append(head)
            for j, p in enumerate(PREP):
                cb = Gtk.CheckButton(label=p, active=j < len(m["done"]) and bool(m["done"][j]))
                set_struck(cb.get_last_child(), p, cb.get_active())
                cb.connect("toggled", self.on_prep_toggled, m, j)
                box.append(cb)
            self.meeting_box.append(box)

    def on_remove_meeting(self, _, i):
        del self.state["meetings"][i]
        self.render_meetings()
        self.save()

    def on_prep_toggled(self, cb, m, j):
        set_struck(cb.get_last_child(), PREP[j], cb.get_active())
        self.cheer(cb)
        m["done"] += [False] * (j + 1 - len(m["done"]))
        m["done"][j] = cb.get_active()
        self.save()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="no.zivid.MorgenTodo", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, cmd):
        # Kun ett vindu: åpner man på nytt, vises det eksisterende. --hours = påminnelsen kl 15:00
        win = getattr(self, "win", None)
        if not win:
            display = Gdk.Display.get_default()
            self.colors = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(display, self.colors, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            css = Gtk.CssProvider()
            css.load_from_string(CSS + POMODORO_CSS)
            Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            # --cat=<navn> tvinger en bestemt katteanimasjon (for testing)
            cat = next((a.split("=", 1)[1] for a in cmd.get_arguments() if a.startswith("--cat=")), None)
            win = self.win = Widget(self, cat)
            Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self.apply_colors())
            try:
                theme = THEME_FILE.read_text().strip()
            except OSError:
                theme = "system"
            self.set_theme(theme)
            if not db.load_config().get("onboarded"):
                GLib.timeout_add(600, lambda: win.show_onboarding() and False)  # første gang: velkomst
        else:
            win.check_new_day()  # f.eks. 08:00-timeren henter fram et vindu som har stått åpent siden i går
        win.present()
        if "--hours" in cmd.get_arguments():
            win.focus_hours()
        return 0

    def set_theme(self, name):
        name = name if name in [t[0] for t in THEMES] else "system"
        self.theme = name
        _, icon, scheme = next(t for t in THEMES if t[0] == name)
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        if win := getattr(self, "win", None):
            win.theme_btn.set_label(icon)
            win.theme_btn.set_tooltip_text(f"Theme: {name}")
        self.apply_colors()

    def cycle_theme(self):
        names = [t[0] for t in THEMES]
        self.set_theme(names[(names.index(self.theme) + 1) % len(names)])
        try:
            THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_FILE.write_text(self.theme)
        except OSError:
            pass

    def apply_colors(self):
        self.colors.load_from_string("".join(f"@define-color mt_{k} {v};\n" for k, v in palette().items()))
        if win := getattr(self, "win", None):
            win.update_progress()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
