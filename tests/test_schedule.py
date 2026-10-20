import unittest

from tests import env
import schedule


class ScheduleTest(unittest.TestCase):
    def test_full_timer_without_package(self):
        sch = dict(schedule.DEFAULTS, morning="08:07", hours_days=[0, 2])
        schedule.apply_reminders(sch)
        text = (schedule.TIMER_DIR / "morgen-todo-hours.timer").read_text()
        self.assertIn("OnCalendar=Mon,Wed 15:00", text)
        self.assertIn("OnCalendar=Mon,Tue,Wed,Thu,Fri 08:07", (schedule.TIMER_DIR / "morgen-todo.timer").read_text())

    def test_dropin_with_package_and_old_file_removed(self):
        pkg = schedule.PACKAGED_DIR
        pkg.mkdir(parents=True, exist_ok=True)
        for unit in ("morgen-todo.timer", "morgen-todo-hours.timer"):
            (pkg / unit).write_text("[Timer]\n")
        schedule.TIMER_DIR.mkdir(parents=True, exist_ok=True)
        (schedule.TIMER_DIR / "morgen-todo.timer").write_text("[Unit]\nDescription=Morgen-todo: old\n")
        try:
            schedule.apply_reminders(dict(schedule.DEFAULTS))
            self.assertFalse((schedule.TIMER_DIR / "morgen-todo.timer").exists())
            conf = (schedule.TIMER_DIR / "morgen-todo.timer.d" / "schedule.conf").read_text()
            self.assertEqual(conf, "[Timer]\nOnCalendar=\nOnCalendar=Mon,Tue,Wed,Thu,Fri 08:00\n")
        finally:
            for p in pkg.iterdir():
                p.unlink()

    def test_disabled_without_days(self):
        env.SYSTEMCTL_CALLS.clear()
        schedule.apply_reminders(dict(schedule.DEFAULTS, hours_days=[]))
        self.assertIn(("disable", "--now", "morgen-todo-hours.timer"), env.SYSTEMCTL_CALLS)

    def test_old_shared_days_migrate(self):
        schedule.save({"days": [1, 3]})
        s = schedule.load()
        self.assertEqual((s["morning_days"], s["hours_days"]), ([1, 3], [1, 3]))


if __name__ == "__main__":
    unittest.main()


class FlatpakSchedulerTest(unittest.TestCase):
    """In Flatpak the app itself opens the list and reminds about hours (App.fire_due_reminders)."""

    def run_tick(self, now, fired=None):
        import database as db
        from datetime import datetime  # noqa: F401
        db.update_config(fired=fired or {})
        schedule.save(dict(schedule.DEFAULTS))
        import app
        calls = []

        class FakeApp:
            def send_notification(self, key, note):
                calls.append(("notify", key))

            def open_window(self, hours=False, cat=None):
                calls.append(("open", hours))

        app.App.fire_due_reminders(FakeApp(), now)
        return calls

    def test_morning_fires_once_also_when_late(self):
        from datetime import datetime
        tue = datetime(2026, 10, 20, 9, 30)
        self.assertEqual(self.run_tick(tue), [("notify", "morning"), ("open", False)])
        self.assertEqual(self.run_tick(tue, fired={"morning": "2026-10-20"}), [])

    def test_hours_only_within_half_an_hour(self):
        from datetime import datetime
        self.assertIn(("open", True), self.run_tick(datetime(2026, 10, 20, 15, 10), fired={"morning": "2026-10-20"}))
        self.assertEqual(self.run_tick(datetime(2026, 10, 20, 17, 0), fired={"morning": "2026-10-20"}), [])

    def test_weekend_quiet(self):
        from datetime import datetime
        self.assertEqual(self.run_tick(datetime(2026, 10, 24, 9, 0)), [])

    def test_next_time(self):
        from datetime import datetime
        sch = dict(schedule.DEFAULTS)
        self.assertEqual(schedule.next_reminder_time(sch, "morning", datetime(2026, 10, 23, 9, 0)), "Mon 2026-10-26 08:00:00")
        self.assertEqual(schedule.next_reminder_time(dict(sch, hours_on=False), "hours"), "off")
