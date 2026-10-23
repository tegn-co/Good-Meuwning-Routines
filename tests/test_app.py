"""Runs the whole app (needs a display; in CI: xvfb-run) through a new user's flow."""
import json
import traceback
import unittest
from datetime import date, datetime, timedelta

from tests import env
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

import cat  # noqa: E402
import platforms  # noqa: E402
import database as db  # noqa: E402
import tutorial  # noqa: E402
import app as W  # noqa: E402

tutorial.pin_to_dock = lambda: True
WAIT = object()  # returned by a step that should run again shortly


class AppTest(unittest.TestCase):
    def test_new_user_flow(self):
        app = W.App()
        app.set_application_id("no.zivid.MorgenTodoTests")
        failures, steps = [], []

        def check(cond, msg):
            if not cond:
                failures.append(msg)

        def step(f):
            steps.append(f)
            return f

        @step
        def onboarding_shown(w):
            check(w.tutorial.get_visible(), "tutorial not shown for a new user")
            check(w.state["routine"] == [] and not any(w.state["checks"].values()), "new user list not empty")
            ob = w.tutorial
            ob.carousel.scroll_to(ob.carousel.get_nth_page(ob.carousel.get_n_pages() - 1), False)
            ob.expected.set_value(7.5)
            ob.opening.set_value(3)

        @step
        def finish_onboarding(w):
            w.tutorial.go_to_page(1)

        @step
        def after_onboarding(w):
            cfg = db.load_config()
            check(cfg.get("onboarded") and cfg.get("expected_hours") == 7.5, f"setup not saved: {cfg}")
            if platforms.USES_APP_SCHEDULER:
                check(env.AUTOSTART_CALLS[-1:] == [True], "start at login not requested")
            else:
                check((env.TMP / "systemd" / "morgen-todo.timer").exists(), "timers not written")
            check(w.bal_total.get_label() == "+3.00 h", f"opening balance: {w.bal_total.get_label()}")

        @step
        def relaunch_reuses_window(w):
            class Cmd:
                def get_arguments(self):
                    return ["morgen-todo"]
            app.do_command_line(Cmd())
            check(app.window is w, "launching again opened a second window instead of reusing the open one")

        @step
        def list_and_plan(w):
            w.items["email"][1].set_active(True)
            check(w.titles["email"].get_label().startswith("<s>"), "checked item not struck through")
            w.items["email"][1].set_active(False)
            check(not w.titles["email"].get_label().startswith("<s>"), "strike-through stays after uncheck")
            w.items["email"][1].set_active(True)
            w.new_todo.set_text("Water the plants")
            w.on_add_todo(w.new_todo)
            rid = "r:" + w.state["routine"][0]["id"]
            w.move_item(rid, "email", after=False)
            check(w.item_order()[0] == rid, "reorder failed")
            w.move_item("random dragged text", "email", after=False)  # must be ignored
            w.plan.get_buffer().set_text("- write report\n- call Ola\nnote")
            check(w.plan_items() == ["write report", "call Ola"], "plan items")
            w.hours.set_value(9)
            w.save_now()

        @step
        def saved(w):
            d = db.load_day(date.today())
            check(d["checks"].get("email") and d["hours"] == 9 and len(d["routine"]) == 1, f"not saved: {d}")
            check(w.bal_total.get_label() in ("+4.50 h", "+3.00 h"), f"balance {w.bal_total.get_label()}")

        @step
        def list_fits(w):
            from gi.repository import Gtk
            w.streak_lbl.set_label("12 days in a row")
            w.streak_lbl.set_visible(True)
            w.title_cat.say("unlocked: coffee cup!")
            need = w.scroll.get_child().measure(Gtk.Orientation.HORIZONTAL, -1)[0]
            check(need <= W.MAIN_W, f"the list needs {need} px, more than the {W.MAIN_W} px window")

        @step
        def update_banner(w):
            import updater
            self.real_newer = updater.check_for_newer_version
            updater.check_for_newer_version = lambda: ("1.1.1", "9.9.9")
            db.update_config(update_checked=None)
            w.check_for_update()

        @step
        def update_banner_shown(w):
            check(w.update_bar.get_reveal_child() and "9.9.9" in w.update_lbl.get_label(),
                  f"update banner not shown: {w.update_lbl.get_label()!r}")
            w.update_bar.set_reveal_child(False)
            import updater
            updater.check_for_newer_version = self.real_newer

        @step
        def weather_row(w):
            import weather as wmod
            check(not w.weather_row.get_visible(), "weather shown without a chosen place")
            self.real_fetch = wmod.fetch_forecast
            wmod.fetch_forecast = lambda lat, lon: {"temp": 7, "kind": "rain", "day_kind": "rain", "min": 3, "max": 9, "rain": 80}
            w.choose_place({"name": "Oslo, Norge", "lat": 59.9, "lon": 10.7})

        @step
        def weather_shown(w):
            import weather as wmod
            check(w.weather_row.get_visible() and w.weather_lbl.get_label() == "7° · 3–9° · rain 80%",
                  f"weather row: {w.weather_lbl.get_label()!r}")
            wmod.fetch_forecast = self.real_fetch

        @step
        def water(w):
            box = w.water_box
            check(box.get_visible() and box.count == 0, "water row missing or not empty")
            box.on_glass(3)  # any empty glass: drink one
            check((w.state["water"], w.title_cat.animation()) == (1, "drink"), f"drinking: {w.state.get('water')}, cat {w.title_cat.animation()}")
            check("1 / 8" in box.amount.get_label(), f"water amount: {box.amount.get_label()!r}")
            box.on_glass(0)  # the last full glass: undo
            check(w.state["water"] == 0, "undo did not empty the glass")
            box.since = box.last = datetime.now() - timedelta(hours=2)
            box.check()
            check(w.title_cat.thirsty and box.has_css_class("attention"), "not thirsty after two hours")
            box.drink()
            check(not w.title_cat.thirsty and not box.has_css_class("attention"), "still thirsty after a glass")
            box.undo()

        @step
        def window_moved(w):
            import cat_tricks
            w.on_header_drag(None, 2, 1)
            check(w.title_cat.treat not in cat_tricks.MOVE_TRICKS, "the cat reacted to a click, not a move")
            w.on_header_drag(None, 30, 10)
            check(w.title_cat.animation() in cat_tricks.MOVE_TRICKS, f"no reaction to moving: {w.title_cat.animation()}")
            w.title_cat.treat = None

        @step
        def nothing_cut_off(w):
            # Every animation, prop and bubble fits in the cat's canvas, on the title and elsewhere
            import cairo
            import cat_tricks
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            t, width, height = w.title_cat, r.area_width(), r.area_height()

            def cut(label):
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
                r.draw(None, cairo.Context(surf), width, height)
                surf.flush()
                data, stride = bytes(surf.get_data()), surf.get_stride()
                x, y, cw, ch = r.canvas_rect()
                outside = data[:max(0, y) * stride].strip(b"\0") or data[max(0, y + ch) * stride:].strip(b"\0")
                if outside:
                    failures.append(f"{label} is drawn outside the cat's canvas")

            extra = list(cat_tricks.WATER_TRICKS) + list(cat_tricks.MOVE_TRICKS)
            for i, anim in enumerate(cat.ANIMATIONS + ["eat"] + extra):
                t.forced, t.treat = (None, None) if anim in extra else (anim, None)
                if anim in extra:
                    t.play(anim, 10)
                if i % 2:
                    t.say("this is a rather long thing for a cat to say!", 10)
                for frame in range(48):
                    t.last -= 0.05
                    t.tick(None, None)
                    if frame % 8 == 7:
                        cut(f"{anim} (frame {frame})")
            t.forced, t.treat = None, None
            t.say("and a long bubble out in the window as well", 10)
            for r.mode, r.s, r.d, r.enter in [("frame", s * r.perimeter() / 8, 1, 0.0) for s in range(8)]:
                cut(f"the cat on the frame at {r.s:.0f}")
            r.mode, r.anchor, r.rest = "roam", (None, r.area_width() / 2), 0.0
            cut("the cat on the floor")
            r.recover()

        @step
        def productivity_mode(w):
            class Check:
                def __init__(self, on):
                    self.get_active = lambda: on
            self.data_before = json.dumps(w.state, sort_keys=True)
            w.on_productivity_mode(Check(True))
            check(db.load_config().get("productivity_mode") is True, "productivity mode not saved")
            check(not w.cat_btn.get_visible() and not w.water_box.get_visible() and not w.weather_row.get_visible()
                  and not w.streak_lbl.get_visible() and w.title_cat.cat_off, "something playful is still shown")

        @step
        def productivity_mode_shown(w):
            # What is actually on screen: the cat's layer as GTK renders it now (not a fresh draw)
            import io
            import cairo
            from gi.repository import Gtk

            class Check:
                def __init__(self, on):
                    self.get_active = lambda: on
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            snap = Gtk.Snapshot()
            Gtk.WidgetPaintable.new(r).snapshot(snap, r.get_width(), r.get_height())
            node = snap.to_node()
            if node is not None:
                png = w.get_native().get_renderer().render_texture(node, None).save_to_png_bytes().get_data()
                surf = cairo.ImageSurface.create_from_png(io.BytesIO(png))
                check(not bytes(surf.get_data()).strip(b"\0"), "the cat is still on screen in productivity mode")
            before = self.data_before
            w.on_productivity_mode(Check(False))
            check(w.cat_btn.get_visible() and w.water_box.get_visible() and w.weather_row.get_visible()
                  and not w.title_cat.cat_off, "turning productivity mode off did not bring everything back")
            check(json.dumps(w.state, sort_keys=True) == before, "productivity mode changed the data")

        @step
        def cat_page(w):
            w.cat_btn.set_active(True)

        @step
        def cat_colors_fit(w):
            # Every color can be changed without scrolling the cat page (fonts and widgets are bigger on Windows)
            last = list(w.cat_panel.color_btns.values())[-1]
            ok, box = last.compute_bounds(w.side)
            if not (ok and w.side.get_width() > 200) and not self.last_try:
                return WAIT  # the panel is still sliding open
            bottom = box.get_y() + box.get_height() if ok else -1
            check(ok and 0 < bottom <= w.side.get_height(),
                  f"cat colors need scrolling: last color ends at {bottom:.0f}, panel is {w.side.get_height()} high")
            w.cat_btn.set_active(False)

        @step
        def side_panels(w):
            for b in (w.cat_btn, w.settings_btn, w.pomo_btn, w.side_btn):
                b.set_active(True)

        @step
        def no_sideways_scroll(w):
            adj = w.side.get_hadjustment()
            check(round(adj.get_upper()) <= w.side.get_width() + 1,
                  f"side panel scrolls sideways: content {adj.get_upper():.0f} > panel {w.side.get_width()} "
                  f"(window {w.get_width()}, page {w.side_stack.get_visible_child_name()})")
            w.pomodoro.set_phase("long", autostart=True)
            w.pomodoro.refresh()
            check(w.title_cat.animation() == "eat", "cat not eating in long break")
            w.pomodoro.on_reset(None)

        @step
        def new_day(w):
            w.side_btn.set_active(False)
            w.day = date.today() - timedelta(days=1)
            w.check_new_day()

        @step
        def after_new_day(w):
            check(w.day == date.today() and w.loaded, "day did not change")
            check(w.get_width() == W.MAIN_W and w.get_height() == W.MAIN_H,
                  f"window size {w.get_width()}x{w.get_height()} (default {w.get_default_size()}, side visible {w.side.get_visible()})")

        @step
        def roamer_in_bounds(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            w.title_cat.forced = "climb"
            r.SPEED = 600
            self.lap = []

            def sample():
                self.lap.append(r.paw_position())
                return len(self.lap) < 40
            GLib.timeout_add(80, sample)

        @step
        def roamer_checked(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            xs, ys = [p[0] for p in self.lap], [p[1] for p in self.lap]
            check(min(xs) >= 0 and max(xs) <= r.area_width() and min(ys) >= -1 and max(ys) <= r.area_height(),
                  f"cat left the window: x {min(xs):.0f}..{max(xs):.0f} y {min(ys):.0f}..{max(ys):.0f}")
            check(w.overlay.get_height() == r.area_height(), "overlay grew")
            # Easter egg next: 5 clicks on the cat -> playtime
            w.title_cat.forced = "sit"

        @step
        def roam_start(w):
            # Title scrolled away: the cat explores the window, always standing on something
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            adj = w.scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            self.roam = []

            def sample():
                self.roam.append((r.mode, r.mode != "roam" or r.on_surface(), r.paw_position()))
                return len(self.roam) < 40
            GLib.timeout_add(100, sample)

        @step
        def roam_checked(w):
            if len(self.roam) < 40 and not self.last_try:
                return WAIT
            roaming = [s for s in self.roam if s[0] == "roam"]
            check(roaming, f"the cat never explored the window: {sorted(set(m for m, _o, _p in self.roam))}")
            floating = [p for m, ok, p in roaming if not ok]
            check(not floating, f"the cat stood on thin air at {floating[:3]}")
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            for x, y in ((-30, r.area_height() + 30), (r.area_width() + 30, -30), (40, r.area_height())):
                check(r.surface_below(x, y) is not None, f"nothing below {x},{y}")  # the floor at least
            # A bug in one animation step must not freeze the cat (GLib drops a timer that raises)
            real, r.roam_tick = r.roam_tick, None  # calling None raises a TypeError
            r.mode = "roam"
            check(r.tick(None, None) is True and r.mode == "title", "an error stopped the cat's animation")
            r.roam_tick = real
            check((platforms.cache_dir() / "errors.log").exists(), "the error was not logged")
            w.scroll.get_vadjustment().set_value(0)

        @step
        def playtime_start(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            if r.mode != "title" and not self.last_try:
                return WAIT  # still hopping back from the window frame (slow CI machines)
            t = w.title_cat
            if not hasattr(t, "cat_box"):  # the window may not have been painted yet (unfocused test window)
                import cairo
                t.draw_cat(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 120)), 400)
            bx, by, bw, bh = t.cat_box
            for _ in range(4):
                t.on_click(None, 1, bx + bw / 2, by + bh / 2)
            check(r.mode == "title", "playtime started before 5 clicks")
            t.on_click(None, 1, bx + bw / 2, by + bh / 2)
            check(r.play_until > 0, "5 clicks on the cat did not start playtime")
            import time as _time
            check(abs(r.play_until - _time.monotonic() - cat.PLAYTIME_SECONDS) < 1, "playtime should last 30 s")
            r.pointer = (r.area_width() - 40, r.area_height() - 40)

        @step
        def playtime_chase(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            x, y = r.paw_position()
            sx, sy, _ok = r.anchor_pos(r.playtime_landing_spot())  # on whatever is under the pointer
            reached = r.mode == "playtime" and abs(x - sx) < 25 and abs(y - sy) < 2 and r.on_surface()
            if not reached and not self.last_try:
                return WAIT
            check(reached, f"cat is not on what's under the pointer: paws {x:.0f},{y:.0f}, spot {sx:.0f},{sy:.0f}, {r.mode}")
            r.on_pointer_leave(None)
            r.pointer_left -= 5

        @step
        def playtime_end(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatOverlay))
            back = r.mode == "title" and not w.title_cat.away
            if not back and not self.last_try:
                return WAIT
            check(back, f"cat did not return after playtime: {r.mode}")
            w.title_cat.forced = None
            w.hours.set_value(6.5)
            w.close()

        def run(i=0, tries=0):
            try:
                self.last_try = tries >= 50  # then the step checks and reports instead of waiting
                if steps[i](app.window) is WAIT:  # the step isn't ready: try again shortly
                    GLib.timeout_add(200, lambda: run(i, tries + 1) and False)
                    return False
            except Exception:
                failures.append(f"{steps[i].__name__}: {traceback.format_exc()}")
            if i + 1 < len(steps):
                wait = {roamer_in_bounds: 3500, roam_start: 1000, side_panels: 1500, new_day: 1500,
                        playtime_start: 2500, playtime_chase: 2000}.get(steps[i], 900)
                GLib.timeout_add(wait, lambda: run(i + 1) and False)
            else:
                GLib.timeout_add(500, lambda: app.quit() and False)
            return False

        GLib.timeout_add(2500, lambda: run() and False)
        app.run(["morgen-todo"])
        check(db.load_day(date.today())["hours"] == 6.5, "hours not saved on close")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
