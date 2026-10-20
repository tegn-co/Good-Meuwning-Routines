"""Kjører hele appen (trenger en skjerm; i CI: xvfb-run) og går gjennom det en ny bruker gjør."""
import traceback
import unittest
from datetime import date, timedelta

from tests import env
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

import cat  # noqa: E402
import db  # noqa: E402
import onboarding  # noqa: E402
import widget as W  # noqa: E402

onboarding.pin_to_dock = lambda: True


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
            check(w.onboarding.get_visible(), "tutorial not shown for a new user")
            check(w.state["routine"] == [] and not any(w.state["checks"].values()), "new user list not empty")
            ob = w.onboarding
            ob.carousel.scroll_to(ob.carousel.get_nth_page(ob.carousel.get_n_pages() - 1), False)
            ob.expected.set_value(7.5)
            ob.opening.set_value(3)

        @step
        def finish_onboarding(w):
            w.onboarding.go(1)

        @step
        def after_onboarding(w):
            cfg = db.load_config()
            check(cfg.get("onboarded") and cfg.get("expected_hours") == 7.5, f"setup not saved: {cfg}")
            check((env.TMP / "systemd" / "morgen-todo.timer").exists(), "timers not written")
            check(w.bal_total.get_label() == "+3.00 h", f"opening balance: {w.bal_total.get_label()}")

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
            check(w.order()[0] == rid, "reorder failed")
            w.move_item("random dragged text", "email", after=False)  # skal ignoreres
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
            import updates
            self.real_newer = updates.newer_available
            updates.newer_available = lambda: ("1.1.1", "9.9.9")
            db.update_config(update_checked=None)
            w.check_for_update()

        @step
        def update_banner_shown(w):
            check(w.update_bar.get_reveal_child() and "9.9.9" in w.update_lbl.get_label(),
                  f"update banner not shown: {w.update_lbl.get_label()!r}")
            w.update_bar.set_reveal_child(False)
            import updates
            updates.newer_available = self.real_newer

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
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatRoamer))
            w.title_cat.forced = "climb"
            r.SPEED = 600
            self.lap = []

            def sample():
                self.lap.append(r.anchor())
                return len(self.lap) < 40
            GLib.timeout_add(80, sample)

        @step
        def roamer_checked(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatRoamer))
            xs, ys = [p[0] for p in self.lap], [p[1] for p in self.lap]
            check(min(xs) >= 0 and max(xs) <= r.area_w() and min(ys) >= -1 and max(ys) <= r.area_h(),
                  f"cat left the window: x {min(xs):.0f}..{max(xs):.0f} y {min(ys):.0f}..{max(ys):.0f}")
            check(w.overlay.get_height() == r.area_h(), "overlay grew")
            # Påskeegget: 5 klikk på katten -> playtime
            w.title_cat.forced = "sit"

        @step
        def playtime_start(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatRoamer))
            t = w.title_cat
            bx, by, bw, bh = t.cat_box
            for _ in range(4):
                t.on_click(None, 1, bx + bw / 2, by + bh / 2)
            check(r.mode == "title", "playtime started before 5 clicks")
            t.on_click(None, 1, bx + bw / 2, by + bh / 2)
            check(r.play_until > 0, "5 clicks on the cat did not start playtime")
            r.pointer = (r.area_w() - 40, r.area_h() - 40)

        @step
        def playtime_chase(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatRoamer))
            x, y = r.anchor()
            check(abs(x - (r.area_w() - 40)) < 25 and abs(y - (r.area_h() - 40)) < 25, f"cat did not reach the pointer: {x:.0f},{y:.0f}")
            r.on_pointer_leave(None)
            r.pointer_left -= 5

        @step
        def playtime_end(w):
            r = next(c for c in [w.overlay.get_last_child()] if isinstance(c, cat.CatRoamer))
            check(r.mode == "title" and not w.title_cat.away, f"cat did not return after playtime: {r.mode}")
            w.title_cat.forced = None
            w.hours.set_value(6.5)
            w.close()

        def run(i=0):
            try:
                steps[i](app.win)
            except Exception:
                failures.append(f"{steps[i].__name__}: {traceback.format_exc()}")
            if i + 1 < len(steps):
                wait = {roamer_in_bounds: 3500, side_panels: 1500, new_day: 1500,
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
