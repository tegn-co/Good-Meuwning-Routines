import unittest

from tests import env
import schedule


class ScheduleTest(unittest.TestCase):
    def test_full_timer_without_package(self):
        sch = dict(schedule.DEFAULTS, morning="08:07", hours_days=[0, 2])
        schedule.apply_timers(sch)
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
            schedule.apply_timers(dict(schedule.DEFAULTS))
            self.assertFalse((schedule.TIMER_DIR / "morgen-todo.timer").exists())
            conf = (schedule.TIMER_DIR / "morgen-todo.timer.d" / "schedule.conf").read_text()
            self.assertEqual(conf, "[Timer]\nOnCalendar=\nOnCalendar=Mon,Tue,Wed,Thu,Fri 08:00\n")
        finally:
            for p in pkg.iterdir():
                p.unlink()

    def test_disabled_without_days(self):
        env.SYSTEMCTL_CALLS.clear()
        schedule.apply_timers(dict(schedule.DEFAULTS, hours_days=[]))
        self.assertIn(("disable", "--now", "morgen-todo-hours.timer"), env.SYSTEMCTL_CALLS)

    def test_old_shared_days_migrate(self):
        schedule.save({"days": [1, 3]})
        s = schedule.load()
        self.assertEqual((s["morning_days"], s["hours_days"]), ([1, 3], [1, 3]))


if __name__ == "__main__":
    unittest.main()
