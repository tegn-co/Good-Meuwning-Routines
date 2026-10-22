#!/usr/bin/env python3
"""Small, movable morning-todo window (GTK4). Stores data in SQLite via database.py (see there for the DB location)."""
import json
import os
import random
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from cat import CatOverlay, TitleCat  # noqa: E402
from pomodoro_panel import CSS as POMODORO_CSS, PomodoroPanel  # noqa: E402
from cat_panel import CatPanel  # noqa: E402
import cat as catmod  # noqa: E402
import database as db  # noqa: E402
import hydration  # noqa: E402
import schedule  # noqa: E402
from tutorial import Tutorial  # noqa: E402
import updater  # noqa: E402
import platforms  # noqa: E402
import weather  # noqa: E402
from translations import LANG, LANGUAGES, _  # noqa: E402

SAVE_DELAY = 10  # seconds without changes before saving
MAIN_H = 600  # the window always starts at MAIN_W x MAIN_H with the side panel closed
MAIN_W, SIDE_W = 360, 317  # width of the main list and the side panel (incl. margins and border)

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

# Light and dark palettes (used as @mt_* in the CSS above)
PALETTES = {
    "light": {"bg": "#f4f4f0", "fg": "#111111", "muted": "#8a8a85", "line": "#dcdcd6", "accent": "#ff4f1f"},
    "dark": {"bg": "#0e0e0e", "fg": "#ededea", "muted": "#6b6b66", "line": "#262624", "accent": "#ff6a3d"},
}
THEME_FILE = db.CONFIG_DIR / "theme"
THEMES = [("system", "◐", Adw.ColorScheme.DEFAULT), ("light", "☀", Adw.ColorScheme.FORCE_LIGHT), ("dark", "☾", Adw.ColorScheme.FORCE_DARK)]


def palette():
    return PALETTES["dark" if Adw.StyleManager.get_default().get_dark() else "light"]


def set_strikethrough(lbl, text, on):
    """Strike through via markup, not CSS: GTK didn't always redraw when only a CSS strike was removed."""
    escaped = GLib.markup_escape_text(text)
    lbl.set_markup(f"<s>{escaped}</s>" if on else escaped)


def label(text, *classes, wrap=False):
    lbl = Gtk.Label(label=_(text), xalign=0, wrap=wrap)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, cat=None):
        super().__init__(application=app, title="Morning Routine", default_width=MAIN_W, default_height=MAIN_H)
        self.state = {"checks": {}, "plan": "", "meetings": [], "hours": None, "day_off": False, "routine": [], "order": [], "hidden": []}
        self.save_id = 0
        self.loading = True

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("bg")
        header = Adw.HeaderBar(show_title=False)
        # Cycles system / light / dark theme
        self.theme_btn = Gtk.Button()
        self.theme_btn.add_css_class("flat")
        self.theme_btn.connect("clicked", lambda _: app.cycle_theme())
        header.pack_start(self.theme_btn)
        # Toggles the pomodoro panel; shows the remaining time while the timer runs
        self.pomo_btn = Gtk.ToggleButton(label="pomo", tooltip_text=_("Pomodoro timer"))
        self.pomo_btn.add_css_class("flat")
        self.pomo_btn.connect("toggled", self.on_side_toggled, "pomo")
        header.pack_start(self.pomo_btn)
        self.cat_btn = Gtk.ToggleButton(label=_("cat"), tooltip_text=_("Customize the cat"))
        self.cat_btn.add_css_class("flat")
        self.cat_btn.connect("toggled", self.on_side_toggled, "cat")
        header.pack_start(self.cat_btn)
        # Items are deleted in settings, not in the list itself, so nothing disappears on a misclick
        self.settings_btn = Gtk.ToggleButton(label="⚙", tooltip_text=_("Settings"))
        self.settings_btn.add_css_class("flat")
        self.settings_btn.connect("toggled", self.on_side_toggled, "settings")
        header.pack_start(self.settings_btn)
        root.append(header)

        self.scroll = scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=MAIN_W)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=18, margin_end=18, margin_bottom=14)
        scroll.set_child(body)
        main = Gtk.Box()
        main.append(scroll)

        # --- Side panel: a stack of pages (plan, pomodoro, cat, settings) ---
        self.side_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, width_request=280,
                                    margin_start=18, margin_end=18)
        # Plan: item 05 as a todo list (lines starting with "-")
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
        # EXTERNAL: the panel may be narrower than its content, so the window width alone decides how much shows
        self.side = Gtk.ScrolledWindow(vexpand=True, hexpand=True, visible=False,
                                       hscrollbar_policy=Gtk.PolicyType.EXTERNAL)
        self.side_stack.add_named(side, "plan")
        # Clamp: pages never exceed the panel width, so long text wraps instead of widening the panel
        self.side.set_child(Adw.Clamp(child=self.side_stack, maximum_size=SIDE_W - 1, tightening_threshold=SIDE_W - 1))
        self.side.add_css_class("side")
        main.append(self.side)
        # One animation drives the window width, so the panel slides in/out with the window edge
        self.side_anim = Adw.TimedAnimation.new(
            self, MAIN_W, MAIN_W + SIDE_W, 220,
            Adw.CallbackAnimationTarget.new(self.resize_to_width),
        )
        self.side_anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.side_anim.connect("done", self.on_side_anim_done)
        # The cat is drawn on a transparent overlay above all content, so it can climb around the frame
        self.overlay = Gtk.Overlay(child=main)
        root.append(self.overlay)
        self.set_content(root)

        # Banner shown when a newer version exists (see check_for_update)
        bar = Gtk.Box(spacing=6, margin_top=8)
        bar.add_css_class("planbox")
        self.update_lbl = label("", "detail", wrap=True)
        self.update_lbl.set_hexpand(True)
        bar.append(self.update_lbl)
        self.update_btn = Gtk.Button(label=_("update"), valign=Gtk.Align.CENTER)
        self.update_btn.add_css_class("flat")
        self.update_btn.connect("clicked", self.on_update_clicked)
        bar.append(self.update_btn)
        close = Gtk.Button(label="×", valign=Gtk.Align.CENTER, tooltip_text=_("Not now"))
        close.add_css_class("flat")
        close.connect("clicked", lambda _: self.update_bar.set_reveal_child(False))
        bar.append(close)
        self.update_bar = Gtk.Revealer(child=bar)
        body.append(self.update_bar)

        # The "good morning" title, with the pixel cat living on top of the letters
        self.title_cat = TitleCat(palette, forced=cat)
        body.append(self.title_cat)
        CatOverlay(self.title_cat, self.overlay)  # adds itself to the overlay
        self.pomodoro = PomodoroPanel(self.title_cat, palette, on_change=self.on_pomodoro_change)
        self.side_stack.add_named(self.pomodoro, "pomo")
        self.cat_panel = CatPanel(self.title_cat)
        self.side_stack.add_named(self.cat_panel, "cat")
        self.side_stack.add_named(self.build_settings_page(), "settings")

        meta = Gtk.Box(margin_bottom=16)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)  # date, with the streak on its own line below
        self.date_lbl = label("", "muted", "detail")
        left.append(self.date_lbl)
        self.streak_lbl = label("", "detail", "muted", wrap=True)  # e.g. "3 days in a row"
        self.streak_lbl.set_visible(False)
        left.append(self.streak_lbl)
        # Weather (shown when a place is chosen under ⚙ → weather)
        self.weather_row = Gtk.Box(spacing=6, visible=False, margin_top=2)
        self.weather_icon = Gtk.DrawingArea(content_width=26, content_height=20)
        self.weather_icon.set_draw_func(self.draw_weather_icon)
        self.weather_row.append(self.weather_icon)
        self.weather_lbl = label("", "detail", "muted", wrap=True)
        self.weather_row.append(self.weather_lbl)
        left.append(self.weather_row)
        meta.append(left)
        self.blocks = Gtk.Label(use_markup=True, hexpand=True, xalign=1)
        self.blocks.add_css_class("blocks")
        meta.append(self.blocks)
        body.append(meta)

        # All items (default and routine) share one list, reordered by dragging the number
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.list_box)
        self.items = {}
        self.titles = {}  # title labels of the default items (struck through when checked)
        self.nums = {}  # number label per item (updated when the order changes)
        self.routine_widgets = {}
        for i, (key, text, details) in enumerate(ITEMS, 1):
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            item.add_css_class("item")
            row = Gtk.Box(spacing=10)
            row.append(self.make_drag_handle(key, item))
            self.titles[key] = label(text, "title", wrap=True)
            row.append(self.titles[key])
            check = Gtk.CheckButton(hexpand=True, halign=Gtk.Align.END)
            check.connect("toggled", self.on_item_toggled, key)
            if key == "plan":
                # Toggles the plan side panel; lives in the row so it stays visible when 05 is checked
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
                extra.append(label("› " + _(d), "detail", wrap=True))
            if key == "prep":
                self.meeting_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                extra.append(self.meeting_box)
                add = Gtk.Button(label=_("+ add meeting"), halign=Gtk.Align.START)
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

        # --- Custom routine items recur every day; added here ---
        add_row = Gtk.Box(spacing=10, margin_top=6, margin_bottom=10)
        add_row.append(label("+", "num"))
        self.new_todo = Gtk.Entry(placeholder_text=_("add to routine and press enter"), hexpand=True)
        self.new_todo.connect("activate", self.on_add_todo)
        add_row.append(self.new_todo)
        body.append(add_row)

        # --- Hours logging (reminder at 15:00) ---
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
        # Enter logs the hours even if the value didn't change (otherwise exactly 0 can't be logged)
        self.hours.connect("activate", lambda spin: self.state["hours"] is None and self.on_hours_changed(spin))
        row.append(self.hours)
        self.hours_box.append(row)
        self.today_diff = label("", "detail")
        self.today_diff.set_margin_start(30)
        self.hours_box.append(self.today_diff)
        self.day_off = Gtk.CheckButton(label=_("day off (vacation, sick, holiday)"), margin_start=26)
        self.day_off.add_css_class("detail")
        self.day_off.get_last_child().set_wrap(True)
        self.day_off.connect("toggled", self.on_day_off_changed)
        self.hours_box.append(self.day_off)
        bal = Gtk.Box(margin_start=30, spacing=16)
        self.bal_total = label("", "big")
        bal.append(self.bal_total)
        self.bal_detail = label("", "detail", "muted", wrap=True)
        self.bal_detail.set_hexpand(True)
        bal.append(self.bal_detail)
        self.hours_box.append(bal)
        body.append(self.hours_box)

        # --- Water: click a glass per drink; the cat drinks along (hydration.py) ---
        self.water_box = hydration.WaterBox(self.title_cat, self.on_water_changed)
        body.append(self.water_box)

        self.footer = label("", "pixel", "muted", "detail")
        self.footer.set_xalign(0.5)
        self.footer.set_margin_top(14)
        body.append(self.footer)
        self.status = label("", "detail", "muted")
        self.status.set_xalign(0.5)
        body.append(self.status)

        self.connect("close-request", self.on_close)
        self.db_worker = db.DatabaseWorker()
        self.loaded = False  # save nothing until today's data is loaded (else an empty list could overwrite everything)
        self.size_delta = 0  # default size minus visible size (see resize_to_width)
        self.connect("map", lambda *_: GLib.timeout_add(150, self.fix_start_size))
        self.day = date.today()
        self.load()

        self.apply_schedule(schedule.load())
        GLib.timeout_add_seconds(5, self.check_for_update)  # then once a day via on_clock_tick
        self.show_weather(db.load_config().get("weather_cache", {}).get("w"))  # last known weather right away
        GLib.timeout_add_seconds(2, lambda: self.refresh_weather() and False)
        GLib.timeout_add_seconds(30 * 60, self.refresh_weather)
        # Poll the wall clock every 30 s (a plain long timer stops while the machine sleeps)
        GLib.timeout_add_seconds(30, self.on_clock_tick)

    def apply_schedule(self, sch):
        """Apply the ⚙ → schedule times to the window (close time and the cat's lunch)."""
        self.schedule = sch
        start, end = schedule.parse_hhmm(sch["lunch"]), schedule.parse_hhmm(sch["lunch_end"])
        catmod.LUNCH = (start.hour * 60 + start.minute, end.hour * 60 + end.minute)
        # Next close time after opening or changing it (if already passed today, it applies tomorrow)
        self.close_at = None
        if sch["close_on"]:
            self.close_at = datetime.combine(date.today(), schedule.parse_hhmm(sch["close"]))
            if datetime.now() >= self.close_at:
                self.close_at += timedelta(days=1)

    # --- streaks and mood ---
    def refresh_streak(self):
        self.db_worker.submit(db.streak_info, self.day, bool(self.state.get("complete")), callback=self.show_streak)

    def show_streak(self, info, err):
        if err or not info:
            return
        n = info["streak"]
        self.streak_lbl.set_label(_("{n} days in a row").format(n=n) if n >= 2 else "")
        self.streak_lbl.set_visible(n >= 2)
        (self.streak_lbl.add_css_class if self.state.get("complete") else self.streak_lbl.remove_css_class)("plus")
        unlocked = {k for k, days, _ in catmod.UNLOCKS if info["best"] >= days}
        new = unlocked - catmod.UNLOCKED
        first = not hasattr(self, "streak_seen")  # on startup: no celebration for what's already unlocked
        catmod.UNLOCKED.clear()
        catmod.UNLOCKED.update(unlocked)
        self.cat_panel.refresh_wear()
        if not first and new:
            name = next(label for k, _, label in catmod.UNLOCKS if k in new)
            self.title_cat.say(_("unlocked: {name}!").format(name=_(name)), 3)
        elif not first and self.state.get("complete") and n >= 2 and n != getattr(self, "streak_seen", 0):
            self.title_cat.say(_("{n} days in a row!").format(n=n), 3)
        self.streak_seen = n

    def react_to_progress(self):
        """The cat reacts to how the day is going (checked every 30 s)."""
        if not self.loaded or self.pomodoro.running() or random.random() > 0.12:
            return
        now = datetime.now()
        keys = self.item_order()
        done = sum(bool(self.state["checks"].get(k)) for k in keys)
        if done == 0 and now.hour >= 10:
            self.title_cat.say(_(random.choice(["meow?", "*stares at list*", "mrrp?"])), 2)
        elif keys and done == len(keys):
            self.title_cat.say("", 0)  # just a heart: happy cat

    def on_clock_tick(self):
        self.check_new_day()
        self.react_to_progress()
        self.water_box.check()
        self.check_for_update()
        if self.close_at is None or datetime.now() < self.close_at:
            return True
        # Save first; close only if the save succeeded, otherwise retry in 30 s
        if not self.loaded:
            return True
        self.hours.update()
        self.save_now(then=self.close)
        return True

    def check_new_day(self):
        """If open past midnight: save yesterday, then load today (with carried-over plan items)."""
        if date.today() == self.day or getattr(self, "changing_day", False):
            return

        def switch_day():
            self.changing_day = False
            self.day = date.today()
            self.load()

        def retry():
            self.changing_day = False  # yesterday wasn't saved; on_clock_tick retries in 30 s

        if self.loaded:
            self.changing_day = True
            self.hours.update()
            self.save_now(then=switch_day, failed=retry)
        else:
            switch_day()

    def on_close(self, _):
        # Save synchronously before closing (max 10 s), even if a save is already running;
        # otherwise the worker thread could be killed mid-write when the app exits.
        if self.loaded:
            self.hours.update()  # commit a value typed into the hours field without Enter
            if self.save_id:
                GLib.source_remove(self.save_id)
                self.save_id = 0
            try:
                self.db_worker.run_sync(db.save_day, self.day, self.state_copy())
            except Exception:
                pass
        return False

    # --- data (all DB access goes through self.db_worker, a background thread) ---
    def state_copy(self):
        return json.loads(json.dumps(self.state))  # deep copy, so the thread never reads a list being modified

    def set_status(self, ok, text):
        self.status.set_label(text)
        (self.status.remove_css_class if ok else self.status.add_css_class)("err")

    def load(self):
        self.loaded = False
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = 0
        d = self.day
        self.date_lbl.set_label(f"{_(DAYS[d.weekday()])} {d.day}{'.' if LANG == 'nb' else ''} {_(MONTHS[d.month - 1])}")
        self.set_status(True, "○ loading…")
        self.scroll.set_sensitive(False)  # anything typed now would be overwritten when the data arrives
        self.db_worker.submit(db.load_day, d, callback=lambda result, err: self.on_loaded(d, result, err))

    def on_loaded(self, day, result, err):
        if day != self.day:
            return  # result for a day we've already moved past
        if err:
            # Block edits that can't be saved safely; retry shortly
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
        self.water_box.show_day(self.state.get("water", 0), self.state.get("water_at"))
        self.loading = False
        self.loaded = True
        self.scroll.set_sensitive(True)
        self.set_status(True, "● saved")
        self.update_progress()
        self.refresh_overtime()
        self.refresh_streak()

    def save(self):
        if self.loading or not self.loaded:
            return
        self.set_status(True, "○ unsaved changes")
        if self.save_id:
            GLib.source_remove(self.save_id)
        # Debounce: write only after SAVE_DELAY seconds without changes
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
                self.refresh_overtime()
                self.refresh_streak()
            if then:
                then()

        self.db_worker.submit(db.save_day, day, self.state_copy(), callback=done)
        return False

    # --- UI ---
    def update_progress(self):
        keys = self.item_order()
        done = sum(bool(self.state["checks"].get(k)) for k in keys)
        total = len(keys)
        self.blocks.set_markup("■" * done + f'<span foreground="{palette()["line"]}">{"■" * (total - done)}</span>')
        self.footer.set_label(_("[ all done – have a great day ]") if done == total else f"{done}/{total}")
        # React only when the list was just completed, not when it loads already complete
        if done == total and not getattr(self, "all_done", True) and not self.loading:
            self.title_cat.react_to("all_done", 3)
        self.all_done = done == total
        self.state["complete"] = total > 0 and done == total  # stored per day, used for streaks
        for key, (item, check, extra) in self.items.items():
            on = check.get_active()
            (item.add_css_class if on else item.remove_css_class)("done")
            set_strikethrough(self.titles[key], _(dict((k, t) for k, t, _d in ITEMS)[key]), on)
            extra.set_visible(not on)

    def refresh_overtime(self):
        self.db_worker.submit(db.overtime_summary, self.day, callback=self.show_overtime)

    def show_overtime(self, sm, err):
        if sm and not err:
            self.last_summary = sm
        fmt = lambda h: f"{h:+.2f} {_('h')}"
        h = self.state.get("hours")
        expected = db.expected_hours_for(self.day, self.state.get("day_off"))
        if h is None:
            self.today_diff.set_label(_("not logged yet · expected {h} h").format(h=f"{expected:g}"))
        else:
            self.today_diff.set_label(_("today {diff} vs {h} h").format(diff=fmt(h - expected), h=f"{expected:g}"))
        if sm and not err:
            self.bal_total.set_label(fmt(sm["total"]))
            (self.bal_total.add_css_class if sm["total"] > 0 else self.bal_total.remove_css_class)("plus")
            self.bal_detail.set_label(_("overtime balance\nweek {week} · month {month}").format(week=fmt(sm["week"]), month=fmt(sm["month"])))

    def focus_hours(self):
        """Called at 15:00: highlight hours logging and focus the field."""
        self.hours_box.add_css_class("attention")
        self.hours.grab_focus()
        GLib.idle_add(lambda: self.scroll_to(self.hours_box))

    def scroll_to(self, widget):
        adj = self.scroll.get_vadjustment()
        ok, point = widget.compute_point(self.scroll.get_child(), Graphene.Point())
        if ok:
            adj.set_value(point.y - 20)
        return False

    def on_water_changed(self, glasses, last_glass):
        self.state["water"], self.state["water_at"] = glasses, last_glass
        self.save()

    def on_day_off_changed(self, check):
        if self.loading:
            return
        self.state["day_off"] = check.get_active()
        self.show_overtime(None, None)
        self.save()

    def on_hours_changed(self, spin):
        if self.loading:
            return
        self.state["hours"] = spin.get_value()
        self.hours_box.remove_css_class("attention")
        self.show_overtime(None, None)
        self.save()

    # --- ordering and drag-and-drop ---
    def item_order(self):
        """All item keys in display order; new items go at the bottom."""
        keys = [k for k in self.items if k not in self.state["hidden"]] + [f"r:{r['id']}" for r in self.state["routine"]]
        saved = [k for k in self.state["order"] if k in keys]
        return saved + [k for k in keys if k not in saved]

    def render_list(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        for n, key in enumerate(self.item_order(), 1):
            widget = self.items[key][0] if key in self.items else self.routine_widgets[key]
            self.list_box.append(widget)
            self.nums[key].set_label(f"{n:02d}")
        self.render_settings()

    def make_drag_handle(self, key, item):
        """The number ("01") is the drag handle for the item."""
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
        order = self.item_order()
        if dragged == target or dragged not in order or target not in order:
            return  # e.g. text dragged in from a text field
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
            row.append(self.make_drag_handle(key, item))
            title = label(r["text"], "title", wrap=True)
            set_strikethrough(title, r["text"], done)
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

    # --- settings: delete and restore items ---
    def build_settings_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head = Gtk.Box()
        head.append(label("settings", "big"))
        tutorial = Gtk.Button(label=_("show tutorial"), hexpand=True, halign=Gtk.Align.END)
        tutorial.add_css_class("flat")
        tutorial.connect("clicked", lambda _: self.show_tutorial())
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

        page.append(self.build_schedule_settings())

        # Hours for another day (forgot to log, or need to correct)
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
        self.past_off = Gtk.CheckButton(label=_("day off"))
        self.past_off.add_css_class("detail")
        row.append(self.past_off)
        save = self.past_save_btn = Gtk.Button(label=_("save"), hexpand=True, halign=Gtk.Align.END, sensitive=False)
        save.add_css_class("flat")
        save.connect("clicked", self.on_past_save)
        row.append(save)
        page.append(row)
        self.past_status = label("", "detail", "muted", wrap=True)
        page.append(self.past_status)
        GLib.idle_add(lambda: self.on_past_day_selected(self.past_cal) and False)

        heading = label("backup", "num")
        heading.set_margin_top(14)
        page.append(heading)
        buttons = Gtk.Box(spacing=4)
        for text, handler in (("export…", self.on_export_backup), ("restore…", self.on_restore_backup),
                              ("hours as CSV…", self.on_export_csv)):
            b = Gtk.Button(label=_(text))
            b.add_css_class("flat")
            b.connect("clicked", handler)
            buttons.append(b)
        page.append(buttons)
        self.backup_status = label("", "detail", "muted", wrap=True)
        page.append(self.backup_status)

        self.build_weather_settings(page)
        hydration.build_settings(page, lambda: self.water_box.apply_settings())

        heading = label("language", "num")
        heading.set_margin_top(14)
        page.append(heading)
        codes = [c for c, _n in LANGUAGES]
        lang = Gtk.DropDown.new_from_strings([n for _c, n in LANGUAGES])
        lang.set_selected(codes.index(LANG))
        lang.connect("notify::selected", lambda d, _p: codes[d.get_selected()] != LANG and (
            db.update_config(language=codes[d.get_selected()]), self.restart()))
        page.append(lang)

        heading = label("updates", "num")
        heading.set_margin_top(14)
        page.append(heading)
        version = updater.installed_version()
        where = _("installed as Flatpak") if platforms.IN_FLATPAK else _("running from source")
        page.append(label(_("version {version}").format(version=version) if version else where, "detail", "muted"))
        self.check_updates = Gtk.CheckButton(label=_("check for new versions"), active=db.load_config().get("check_updates", True))
        self.check_updates.add_css_class("detail")
        self.check_updates.connect("toggled", lambda b: db.update_config(check_updates=b.get_active()))
        page.append(self.check_updates)
        return page

    # --- backup ---
    def choose_file(self, title, save_name, on_chosen, pattern=None):
        dialog = Gtk.FileDialog(title=title, modal=True)
        if pattern:
            f = Gtk.FileFilter()
            f.add_pattern(pattern)
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(f)
            dialog.set_filters(store)

        def done(d, result):
            try:
                gfile = d.save_finish(result) if save_name else d.open_finish(result)
            except GLib.Error:
                return  # cancelled
            on_chosen(gfile.get_path())

        if save_name:
            dialog.set_initial_name(save_name)
            dialog.save(self, None, done)
        else:
            dialog.open(self, None, done)

    def on_export_backup(self, _widget):
        def chosen(path):
            self.backup_status.set_label(_("saving backup…"))
            self.db_worker.submit(db.export_backup, path, callback=lambda r, e: self.backup_status.set_label(
                _("could not save – {err}").format(err=e) if e else _("backup saved: {path}").format(path=path)))
        self.choose_file(_("Save backup"), f"morning-routine-backup-{date.today()}.zip", chosen)

    def on_export_csv(self, _widget):
        def chosen(path):
            self.db_worker.submit(db.export_hours_csv, path, callback=lambda n, e: self.backup_status.set_label(
                _("could not save – {err}").format(err=e) if e else _("{n} days of hours saved: {path}").format(n=n, path=path)))
        self.choose_file(_("Save hours"), f"hours-{date.today()}.csv", chosen)

    def on_restore_backup(self, _widget):
        def chosen(path):
            alert = Adw.AlertDialog(heading=_("Restore this backup?"),
                                    body=_("Your current list, hours and settings are replaced by the backup. "
                                           "A copy of the current database is kept next to it."))
            alert.add_response("cancel", _("Cancel"))
            alert.add_response("restore", _("Restore"))
            alert.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
            alert.connect("response", lambda _, r: r == "restore" and self.restore_from(path))
            alert.present(self)
        self.choose_file(_("Restore backup"), None, chosen, pattern="*.zip")

    def restore_from(self, path):
        if self.save_id:  # a pending save must not overwrite the restored data afterwards
            GLib.source_remove(self.save_id)
            self.save_id = 0
        self.loaded = False
        self.backup_status.set_label(_("restoring…"))

        def done(_result, err):
            if err:
                self.backup_status.set_label(_("could not restore – {err}").format(err=err))
                self.load()
                return
            self.restart()  # settings (cat, theme, times) are only read at startup

        self.db_worker.submit(db.restore_backup, path, callback=done)

    def restart(self):
        """Restart the app (after a restore or update)."""
        if self.loaded:
            self.on_close(None)
        platforms.restart()

    # --- weather ---
    def refresh_weather(self):
        place = db.load_config().get("weather_place")
        if not place:
            self.show_weather(None)
            return True

        def done(w, err):
            if err or not w:
                return  # keep the last known weather
            db.update_config(weather_cache={"date": str(date.today()), "w": w})
            self.show_weather(w)
            self.weather_remark(w)

        self.run_in_thread(lambda: weather.fetch_forecast(place["lat"], place["lon"]), done)
        return True

    def show_weather(self, w):
        self.weather = w if db.load_config().get("weather_place") else None
        self.weather_row.set_visible(bool(self.weather))
        if not self.weather:
            return
        text = f"{w['temp']}° · {w['min']}–{w['max']}°"
        if (w.get("rain") or 0) >= 20:
            text += " · " + _("rain {p}%").format(p=w["rain"])
        self.weather_lbl.set_label(text)
        self.weather_icon.queue_draw()

    def draw_weather_icon(self, area, cr, width, height):
        if not getattr(self, "weather", None):
            return
        icon = catmod.add_outline(weather.ICONS[self.weather["kind"]])
        px = 2
        ox = (width - len(icon[0]) * px) // 2
        oy = (height - len(icon) * px) // 2
        for r, row in enumerate(icon):
            for c, ch in enumerate(row):
                if ch != ".":
                    cr.set_source_rgb(*catmod.hex_to_rgb(weather.COLORS[ch]))
                    cr.rectangle(ox + c * px, oy + r * px, px, px)
                    cr.fill()

    def weather_remark(self, w):
        """Once each morning, the cat comments on today's weather (umbrella, snow, nice day)."""
        today = str(date.today())
        if not 5 <= datetime.now().hour < 12 or db.load_config().get("weather_remark") == today:
            return
        db.update_config(weather_remark=today)
        if text := weather.cat_remark(w):
            self.title_cat.say(_(text), 4)

    def build_weather_settings(self, page):
        heading = label("weather", "num")
        heading.set_margin_top(14)
        page.append(heading)
        self.place_lbl = label("", "detail", "muted", wrap=True)
        page.append(self.place_lbl)
        row = Gtk.Box(spacing=6)
        self.place_entry = Gtk.Entry(placeholder_text=_("city, e.g. Oslo"), hexpand=True)
        self.place_entry.connect("activate", self.on_place_search)
        row.append(self.place_entry)
        find = Gtk.Button(label=_("search"))
        find.add_css_class("flat")
        find.connect("clicked", self.on_place_search)
        row.append(find)
        page.append(row)
        self.place_results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(self.place_results)
        self.show_place()

    def show_place(self):
        place = db.load_config().get("weather_place")
        self.place_lbl.set_label(_("showing weather for {place}").format(place=place["name"]) if place
                                 else _("Pick a city to show the weather under the date. Only its coordinates are sent to open-meteo.com."))

    def on_place_search(self, _widget):
        query = self.place_entry.get_text().strip()
        if not query:
            return
        while child := self.place_results.get_first_child():
            self.place_results.remove(child)
        self.place_results.append(label("searching…", "detail", "muted"))

        def done(results, err):
            while child := self.place_results.get_first_child():
                self.place_results.remove(child)
            if err or not results:
                self.place_results.append(label(_("no places found") if not err else
                                                _("could not search – {err}").format(err=err), "detail", "muted"))
                return
            for r in results:
                name = ", ".join(x for x in (r["name"], r["region"], r["country"]) if x)
                b = Gtk.Button(label=name, halign=Gtk.Align.START)
                b.add_css_class("flat")
                b.connect("clicked", lambda _b, r=r, name=name: self.choose_place(dict(r, name=name)))
                self.place_results.append(b)
            if db.load_config().get("weather_place"):
                off = Gtk.Button(label=_("turn weather off"), halign=Gtk.Align.START)
                off.add_css_class("flat")
                off.connect("clicked", lambda _b: self.choose_place(None))
                self.place_results.append(off)

        lang = "nb" if LANG == "nb" else "en"
        self.run_in_thread(lambda: weather.search(query, lang), done)

    def choose_place(self, place):
        db.update_config(weather_place=place, weather_cache=None)
        while child := self.place_results.get_first_child():
            self.place_results.remove(child)
        self.place_entry.set_text("")
        self.show_place()
        self.refresh_weather()

    # --- updates ---
    def check_for_update(self):
        cfg = db.load_config()
        if not cfg.get("check_updates", True) or cfg.get("update_checked") == str(date.today()):
            return False
        db.update_config(update_checked=str(date.today()))

        def done(result, err):
            if err or not result:
                return
            current, latest = result
            if db.load_config().get("skip_version") == latest:
                return
            self.update_latest = latest
            self.update_lbl.set_label(_("Version {latest} is available (you have {current}).").format(latest=latest, current=current))
            self.update_btn.set_sensitive(True)
            self.update_btn.set_label(_("update"))
            self.update_bar.set_reveal_child(True)

        self.run_in_thread(updater.check_for_newer_version, done)
        return False

    def run_in_thread(self, fn, callback):
        """Run fn on its own thread (keeps network calls off the DB queue); callback(result, error) runs on the GTK thread."""
        def work():
            try:
                result, err = fn(), None
            except Exception as e:  # noqa: BLE001
                result, err = None, e
            GLib.idle_add(lambda: callback(result, err) and False)

        threading.Thread(target=work, daemon=True).start()

    def on_update_clicked(self, btn):
        if btn.get_label() == _("restart"):
            self.restart()
            return
        btn.set_sensitive(False)
        self.update_lbl.set_label(_("Downloading…"))

        def downloaded(path, err):
            if err:
                self.update_lbl.set_label(_("Download failed – {err}").format(err=err))
                btn.set_sensitive(True)
                return
            cmd = updater.install_command(path)
            if not cmd:
                self.update_lbl.set_label(_("Run this in a terminal to update:\n{cmd}").format(cmd=updater.INSTALL_COMMAND))
                return
            if platforms.IS_WINDOWS:
                # The installer replaces the app's files, so close first; it starts the app again when done
                self.update_lbl.set_label(_("Installing…"))
                subprocess.Popen(cmd, close_fds=True)
                if self.loaded:
                    self.on_close(None)
                self.get_application().quit()
                return
            self.update_lbl.set_label(_("Installing – enter your password in the dialog…"))
            proc = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)

            def finished(p, res):
                try:
                    ok = p.wait_check_finish(res)
                except GLib.Error:
                    ok = False
                if ok:
                    self.update_lbl.set_label(_("Updated to {version}. Restart to use it.").format(version=self.update_latest))
                    btn.set_label(_("restart"))
                else:
                    self.update_lbl.set_label(_("Not updated (cancelled or failed). Try again, or run:\n{cmd}").format(
                        cmd=updater.INSTALL_COMMAND))
                    btn.set_label(_("update"))
                btn.set_sensitive(True)

            proc.wait_check_async(None, finished)

        self.run_in_thread(updater.download_latest_package, downloaded)

    def build_schedule_settings(self):
        """⚙ → schedule: list opening time, reminders, close time, lunch and weekdays."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        heading = label("schedule", "num")
        heading.set_margin_top(14)
        box.append(heading)
        sch = schedule.load()
        self.sched_widgets = {}  # key -> (on/off checkbox or None, hour, minute)
        self.day_btns = {}  # reminder key -> seven weekday buttons

        def time_picker(key):
            t = schedule.parse_hhmm(sch[key])
            hh = Gtk.SpinButton.new_with_range(0, 23, 1)
            mm = Gtk.SpinButton.new_with_range(0, 59, 5)
            for spin, value in ((hh, t.hour), (mm, t.minute)):
                spin.set_value(value)
                spin.set_wrap(True)
                # Vertical (+ above, − below) and two chars wide, so four fields fit in the side panel
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
            on = Gtk.CheckButton(label=_(text), active=sch[f"{key}_on"])
            on.add_css_class("detail")
            on.get_last_child().set_wrap(True)  # wrap long text instead of widening the panel
            picker, hh, mm = time_picker(key)
            row(on, picker)
            self.sched_widgets[key] = (on, hh, mm)
            if with_days:
                days = Gtk.Box(spacing=2, margin_start=26)
                self.day_btns[key] = []
                for i, name in enumerate(schedule.DAY_NAMES):
                    b = Gtk.ToggleButton(label=_(name)[:2], active=i in sch[f"{key}_days"])
                    b.add_css_class("flat")
                    days.append(b)
                    self.day_btns[key].append(b)
                box.append(days)

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

        apply = Gtk.Button(label=_("apply"), halign=Gtk.Align.END)
        apply.add_css_class("flat")
        apply.connect("clicked", self.on_schedule_apply)
        box.append(apply)
        self.sched_status = label("", "detail", "muted", wrap=True)
        box.append(self.sched_status)
        return box

    # --- first launch ---
    def show_tutorial(self):
        opening = getattr(self, "last_summary", {}).get("opening_balance", 0.0)
        self.tutorial = Tutorial(self, palette, self.on_tutorial_done, opening=opening)
        self.tutorial.present()

    def on_tutorial_done(self, opening, sch, problems):
        if opening is not None:
            self.db_worker.submit(db.set_opening_balance, opening, callback=lambda *_: self.refresh_overtime())
        else:
            self.refresh_overtime()
        self.apply_schedule(sch)

        def timers_done(_, err):
            if err:
                self.set_status(False, f"● reminders could not be set – {err}")

        self.db_worker.submit(schedule.apply_reminders, sch, callback=timers_done)
        # Sync the ⚙ schedule fields with what was chosen in the tutorial
        for key, (on, hh, mm) in self.sched_widgets.items():
            t = schedule.parse_hhmm(sch[key])
            hh.set_value(t.hour)
            mm.set_value(t.minute)
            if on is not None:
                on.set_active(sch[f"{key}_on"])
        if problems:
            self.set_status(False, "● setup: " + "; ".join(problems))
        self.title_cat.say(_("welcome!"), 3)

    def on_schedule_apply(self, _widget):
        sch = dict(self.schedule)
        for key, (on, hh, mm) in self.sched_widgets.items():
            sch[key] = f"{int(hh.get_value()):02d}:{int(mm.get_value()):02d}"
            if on is not None:
                sch[f"{key}_on"] = on.get_active()
        for key, btns in self.day_btns.items():
            sch[f"{key}_days"] = [i for i, b in enumerate(btns) if b.get_active()]
        if sch["lunch_end"] <= sch["lunch"]:
            self.sched_status.set_label(_("not saved – lunch must end after it starts"))
            return
        try:
            schedule.save(sch)
        except OSError as e:
            self.sched_status.set_label(_("not saved – {err}").format(err=e))
            return
        self.apply_schedule(sch)
        self.sched_status.set_label(_("saving…"))

        def done(runs, err):
            if err:
                self.sched_status.set_label(_("saved, but reminders could not be set – {err}").format(err=err))
                return
            nxt = lambda v: v.rsplit(" ", 1)[0] if v != "off" else _("off")
            close = f"{self.close_at:%a %H:%M}" if self.close_at else _("off")
            self.sched_status.set_label(_("saved · next open: {open} · reminder: {reminder} · close: {close}").format(
                open=nxt(runs["morning"]), reminder=nxt(runs["hours"]), close=close))

        # systemctl runs on the worker thread so the window doesn't hang if systemd is slow
        self.db_worker.submit(schedule.apply_reminders, sch, callback=done)

    def selected_past_day(self):
        d = self.past_cal.get_date()
        return date(d.get_year(), d.get_month(), d.get_day_of_month())

    def on_past_day_selected(self, cal):
        day = self.selected_past_day()
        self.past_save_btn.set_sensitive(False)  # disabled until this day's values load, so they can't be saved to the wrong day
        if day == self.day:
            self.past_status.set_label(_("Today: use the hours field in the list."))
            return
        self.past_status.set_label(_("loading…"))

        def show(result, err):
            if err or day != self.selected_past_day():
                self.past_status.set_label(_("could not read – {err}").format(err=err) if err else "")
                return
            self.past_hours.set_value(result["hours"] or 0)
            self.past_off.set_active(result["day_off"])
            logged = _("not logged") if result["hours"] is None else _("logged {h} h").format(h=f"{result['hours']:g}")
            self.past_status.set_label(_("{day}: {logged} · expected {h} h").format(
                day=f"{day:%a %d %b}", logged=logged, h=f"{db.expected_hours_for(day, result['day_off']):g}"))
            self.past_save_btn.set_sensitive(True)

        self.db_worker.submit(db.get_logged_hours, day, callback=show)

    def on_past_save(self, _widget):
        day = self.selected_past_day()
        if day == self.day:
            return
        hours, off = self.past_hours.get_value(), self.past_off.get_active()

        def done(_result, err):
            self.past_status.set_label(_("not saved – {err}").format(err=err) if err
                                       else _("saved {h} h for {day}").format(h=f"{hours:g}", day=f"{day:%a %d %b}"))
            self.refresh_overtime()

        self.db_worker.submit(db.set_logged_hours, day, hours, off, callback=done)

    def item_title(self, key):
        if key in self.items:
            return _(dict((k, t) for k, t, _d in ITEMS)[key])
        return next(r["text"] for r in self.state["routine"] if f"r:{r['id']}" == key)

    def render_settings(self):
        for box in (self.settings_list, self.deleted_list):
            while child := box.get_first_child():
                box.remove(child)
        for n, key in enumerate(self.item_order(), 1):
            row = Gtk.Box(spacing=10)
            row.add_css_class("setrow")
            row.append(label(f"{n:02d}", "num"))
            title = label(self.item_title(key), "detail", wrap=True)
            title.set_hexpand(True)
            row.append(title)
            btn = Gtk.Button(label=_("delete"), valign=Gtk.Align.CENTER)
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
            btn = Gtk.Button(label=_("restore"), valign=Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", self.on_restore, key)
            row.append(btn)
            self.deleted_list.append(row)

    def on_delete_clicked(self, btn, key):
        # First click asks for confirmation (for 3 s); the second click deletes
        if btn.get_label() != _("sure?"):
            btn.set_label(_("sure?"))
            btn.add_css_class("danger")
            GLib.timeout_add_seconds(3, lambda: (btn.set_label(_("delete")), btn.remove_css_class("danger"), False)[-1])
            return
        if key in self.items:
            self.state["hidden"] = self.state["hidden"] + [key]  # default items are only hidden, so they can be restored
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

    def react_to_check(self, check):
        """The cat says its "check" line when something is checked (not while the list loads)."""
        if check.get_active() and not self.loading:
            self.title_cat.react_to("check")

    def on_todo_toggled(self, check, key):
        self.react_to_check(check)
        self.state["checks"][key] = check.get_active()
        self.render_routine()
        self.update_progress()
        self.save()

    def on_item_toggled(self, check, key):
        self.react_to_check(check)
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
            set_strikethrough(cb.get_last_child(), text, cb.get_active())
            cb.connect("toggled", self.on_plan_item_toggled, text)
            self.plan_list.append(cb)
        done = sum(bool(self.state["checks"].get(f"p:{t}")) for t in items)
        self.plan_count.set_label(f"{done}/{len(items)}" if items else "")
        self.plan_hint.set_visible(not items)

    def on_plan_item_toggled(self, cb, text):
        self.react_to_check(cb)
        self.state["checks"][f"p:{text}"] = cb.get_active()
        self.render_plan_items()
        self.save()

    def on_pomodoro_change(self, pomo):
        # Show the time on the button while running, so it's visible with the panel closed
        self.pomo_btn.set_label(f"pomo {pomo.clock_text()}" if pomo.running() else "pomo")

    def side_buttons(self):
        return {"plan": self.side_btn, "pomo": self.pomo_btn, "cat": self.cat_btn, "settings": self.settings_btn}

    def on_side_toggled(self, btn, page):
        # All pages share the side panel: opening one while another is open only swaps the content
        if getattr(self, "switching", False):
            return
        others = [b for name, b in self.side_buttons().items() if name != page and b.get_active()]
        if btn.get_active():
            self.side_stack.set_visible_child_name(page)
            self.side.get_vadjustment().set_value(0)  # the pages share one scroll position; always start at the top
            if others:
                self.switching = True
                for b in others:
                    b.set_active(False)
                self.switching = False
        self.side_btn.set_label(_("plan ◂") if self.side_btn.get_active() else _("plan ▸"))
        if btn.get_active() and others:
            return
        self.animate_side_panel(btn.get_active())

    def fix_start_size(self):
        """On first map, make the visible size MAIN_W x MAIN_H even if the default size includes invisible borders (X11)."""
        dw, dh = self.get_default_size()
        self.size_delta = max(0, dw - self.get_width())
        dy = max(0, dh - self.get_height())
        if (self.size_delta or dy) and not self.side.get_visible():
            self.set_default_size(MAIN_W + self.size_delta, MAIN_H + dy)
        return False

    def resize_to_width(self, width):
        """Set the visible width, compensating for GTK's larger default size (X11 without shadows: 10 px); keep the height."""
        dw, dh = self.get_default_size()
        self.set_default_size(round(width) + self.size_delta, dh)
        if self.get_mapped():
            platforms.resize_window(self, round(width) - self.get_width())

    def animate_side_panel(self, opening):
        # Opening grows the window to the right; closing shrinks it from the right
        self.side_anim.pause()
        if self.get_mapped() and self.side_anim.get_state() != Adw.AnimationState.PLAYING:
            self.size_delta = max(0, self.get_default_size()[0] - self.get_width())  # refresh, e.g. after a theme or monitor change
        if opening:
            self.side.set_visible(True)
            self.scroll.set_hexpand(False)
        self.side_anim.set_value_from(self.get_width() if self.get_mapped() else MAIN_W)
        self.side_anim.set_value_to(MAIN_W + SIDE_W if opening else MAIN_W)
        if not self.get_mapped():
            # Not mapped yet (startup): set the width directly
            self.set_default_size(MAIN_W + SIDE_W if opening else MAIN_W, self.get_default_size()[1])
            self.side.set_visible(opening)
            self.scroll.set_hexpand(not opening)
            return
        self.side_anim.play()
        # The animation runs on the frame clock and can stall if the window is behind another one;
        # if it isn't done after 0.4 s, skip to the end so the panel never stays half open.
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
            name = Gtk.Entry(text=m["name"], placeholder_text=_("10:00 sprint review"), hexpand=True)
            name.connect("changed", lambda e, m=m: (m.__setitem__("name", e.get_text()), self.save()))
            head.append(name)
            rm = Gtk.Button(label="×")
            rm.add_css_class("flat")
            rm.connect("clicked", self.on_remove_meeting, i)
            head.append(rm)
            box.append(head)
            for j, p in enumerate(PREP):
                cb = Gtk.CheckButton(label=_(p), active=j < len(m["done"]) and bool(m["done"][j]))
                set_strikethrough(cb.get_last_child(), _(p), cb.get_active())
                cb.connect("toggled", self.on_prep_toggled, m, j)
                box.append(cb)
            self.meeting_box.append(box)

    def on_remove_meeting(self, _, i):
        del self.state["meetings"][i]
        self.render_meetings()
        self.save()

    def on_prep_toggled(self, cb, m, j):
        set_strikethrough(cb.get_last_child(), _(PREP[j]), cb.get_active())
        self.react_to_check(cb)
        m["done"] += [False] * (j + 1 - len(m["done"]))
        m["done"][j] = cb.get_active()
        self.save()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="no.zivid.MorgenTodo", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_command_line(self, cmd):
        # Single window: launching again presents the existing one. --hours = the 15:00 reminder
        args = cmd.get_arguments()
        if platforms.USES_APP_SCHEDULER:
            # Flatpak and Windows have no systemd timers: the app stays in the background and fires reminders itself
            if not getattr(self, "held", False):
                self.hold()
                self.held = True
                GLib.timeout_add_seconds(30, self.fire_due_reminders)
                GLib.timeout_add_seconds(3, lambda: self.fire_due_reminders() and False)
            if "--background" in args:
                return 0  # started at login: just wait for the clock
        cat = next((a.split("=", 1)[1] for a in args if a.startswith("--cat=")), None)
        self.open_window(cat=cat, hours="--hours" in args)
        return 0

    def open_window(self, cat=None, hours=False):
        win = getattr(self, "window", None)
        if not win:
            if not getattr(self, "colors", None):
                display = Gdk.Display.get_default()
                self.colors = Gtk.CssProvider()
                Gtk.StyleContext.add_provider_for_display(display, self.colors, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                css = Gtk.CssProvider()
                css.load_from_string(platforms.with_symbol_fonts(CSS + POMODORO_CSS + hydration.CSS))
                Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
                Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self.apply_colors())
            # --cat=<name> forces a specific cat animation (for testing)
            win = self.window = MainWindow(self, cat)
            win.connect("destroy", lambda *_: setattr(self, "window", None))  # in background mode a new window may be opened later
            try:
                theme = THEME_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                theme = "system"
            self.set_theme(theme)
            if not db.load_config().get("onboarded"):
                GLib.timeout_add(600, lambda: win.show_tutorial() and False)  # first run: welcome tutorial
            if smoke := os.environ.get("MORGEN_TODO_SMOKE_TEST"):
                # Used by the Windows build check: prove the installed app starts, then quit
                GLib.timeout_add(4000, lambda: (Path(smoke).write_text(f"ok {updater.installed_version()}", encoding="utf-8"),
                                                self.quit(), False)[-1])
        else:
            win.check_new_day()  # e.g. the 08:00 timer raises a window left open since yesterday
        win.present()
        if hours:
            win.focus_hours()

    def fire_due_reminders(self, now=None):
        """Flatpak stand-in for the systemd timers: open the list / hours reminder at the ⚙ → schedule times.

        A missed morning opening still fires later; the hours reminder only within 30 min.
        """
        now = now or datetime.now()
        sch = schedule.load()
        fired = db.load_config().get("fired", {})
        texts = {"morning": (_("Good morning ☀️"), _("Time for your morning routine.")),
                 "hours": (_("⏱ Log your hours"), _("How many hours did you work today?"))}
        for key in ("morning", "hours"):
            if not sch[f"{key}_on"] or now.weekday() not in sch[f"{key}_days"] or fired.get(key) == str(now.date()):
                continue
            at = datetime.combine(now.date(), schedule.parse_hhmm(sch[key]))
            if now < at:
                continue
            fired[key] = str(now.date())
            db.update_config(fired=fired)
            if key == "hours" and now - at > timedelta(minutes=30):
                continue
            note = Gio.Notification.new(texts[key][0])
            note.set_body(texts[key][1])
            note.set_icon(Gio.ThemedIcon.new("no.zivid.MorgenTodo"))
            self.send_notification(key, note)
            self.open_window(hours=key == "hours")
        return True

    def set_theme(self, name):
        name = name if name in [t[0] for t in THEMES] else "system"
        self.theme = name
        _name, icon, scheme = next(t for t in THEMES if t[0] == name)
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        if win := getattr(self, "window", None):
            win.theme_btn.set_label(icon)
            win.theme_btn.set_tooltip_text(_("Theme: {name}").format(name=_(name)))
        self.apply_colors()

    def cycle_theme(self):
        names = [t[0] for t in THEMES]
        self.set_theme(names[(names.index(self.theme) + 1) % len(names)])
        try:
            THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_FILE.write_text(self.theme, encoding="utf-8")
        except OSError:
            pass

    def apply_colors(self):
        self.colors.load_from_string("".join(f"@define-color mt_{k} {v};\n" for k, v in palette().items()))
        if win := getattr(self, "window", None):
            win.update_progress()


if __name__ == "__main__":
    platforms.register_fonts()
    sys.exit(App().run(sys.argv))
