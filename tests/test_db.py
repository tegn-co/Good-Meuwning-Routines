import unittest
from datetime import date, timedelta

from tests import env  # noqa: F401  (temporary dirs)
import database as db

MON = date(2026, 10, 12)


def state(**kw):
    s = {"checks": {}, "plan": "", "meetings": [], "hours": None, "day_off": False,
         "routine": [], "order": [], "hidden": []}
    s.update(kw)
    return s


class DbTest(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = env.TMP / f"{self.id()}.db"
        db.EXPECTED_HOURS = 8.0

    def test_fresh_day_is_empty(self):
        d = db.load_day(MON)
        self.assertEqual((d["checks"], d["plan"], d["hours"], d["routine"]), ({}, "", None, []))

    def test_water_is_saved_per_day(self):
        db.save_day(MON, state(water=5, water_at="2026-10-12T13:05:00"))
        self.assertEqual((db.load_day(MON)["water"], db.load_day(MON)["water_at"]), (5, "2026-10-12T13:05:00"))
        tue = db.load_day(MON + timedelta(days=1))
        self.assertEqual((tue["water"], tue["water_at"]), (0, None))  # a new day starts with empty glasses

    def test_overtime_weekend_and_day_off(self):
        db.save_day(MON, state(hours=9))                     # +1
        db.set_logged_hours(MON + timedelta(days=1), 3, True)        # day off: +3
        db.set_logged_hours(MON + timedelta(days=2), 6, False)       # -2
        db.set_logged_hours(MON + timedelta(days=5), 2, False)       # Saturday: +2
        s = db.overtime_summary(MON + timedelta(days=6))
        self.assertAlmostEqual(s["total"], 4.0)
        self.assertEqual(s["days_logged"], 4)

    def test_future_days_not_counted(self):
        db.set_logged_hours(MON + timedelta(days=30), 8, False)
        self.assertEqual(db.overtime_summary(MON)["days_logged"], 0)

    def test_changing_work_day_keeps_past_overtime(self):
        db.save_day(MON, state(hours=9))
        db.EXPECTED_HOURS = 7.0
        self.assertAlmostEqual(db.overtime_summary(MON)["total"], 1.0)

    def test_opening_balance(self):
        db.set_opening_balance(5)
        self.assertAlmostEqual(db.overtime_summary(MON)["total"], 5.0)

    def test_unfinished_plan_carries_over(self):
        db.save_day(MON, state(plan="- open\n- done\nnote", checks={"p:done": True}))
        self.assertEqual(db.load_day(MON + timedelta(days=1))["plan"], "- open")

    def test_carry_over_survives_prelogged_hours(self):
        db.save_day(MON, state(plan="- open"))
        db.set_logged_hours(MON + timedelta(days=1), 0, True)
        d = db.load_day(MON + timedelta(days=1))
        self.assertEqual((d["plan"], d["day_off"]), ("- open", True))

    def test_routine_order_hidden_are_shared(self):
        db.save_day(MON, state(routine=[{"id": "a", "text": "Water"}], order=["r:a", "email"], hidden=["jira"]))
        d = db.load_day(MON + timedelta(days=3))
        self.assertEqual((d["routine"][0]["text"], d["order"], d["hidden"]), ("Water", ["r:a", "email"], ["jira"]))

    def test_streak_skips_weekend_and_day_off(self):
        fri = MON + timedelta(days=4)
        db.save_day(MON + timedelta(days=3), state(complete=True))   # Thursday
        db.save_day(fri, state(complete=True))                          # Friday
        db.set_logged_hours(MON + timedelta(days=7), 0, True)                  # Monday: day off
        tue = MON + timedelta(days=8)
        self.assertEqual(db.streak_info(tue, False)["streak"], 2)      # weekend + day off don't break it
        self.assertEqual(db.streak_info(tue, True), {"streak": 3, "best": 3})
        self.assertEqual(db.streak_info(tue + timedelta(days=2), False), {"streak": 0, "best": 3})  # Wednesday missing

    def test_backup_restore_and_csv(self):
        db.save_day(MON, state(hours=9, routine=[{"id": "a", "text": "Water"}]))
        (db.CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        (db.CONFIG_DIR / "theme").write_text("dark", encoding="utf-8")
        zip_path = env.TMP / "backup.zip"
        db.export_backup(zip_path)
        db.save_day(MON, state(hours=1, routine=[]))                 # changes after the backup
        (db.CONFIG_DIR / "theme").write_text("light", encoding="utf-8")
        db.restore_backup(zip_path)
        d = db.load_day(MON)
        self.assertEqual((d["hours"], d["routine"][0]["text"]), (9, "Water"))
        self.assertEqual((db.CONFIG_DIR / "theme").read_text(encoding="utf-8"), "dark")
        self.assertTrue(db.DB_PATH.with_name(db.DB_PATH.stem + ".before-restore.db").exists())
        csv_path = env.TMP / "hours.csv"
        self.assertEqual(db.export_hours_csv(csv_path), 1)
        self.assertIn("2026-10-12,Monday,9.0,8.0,1.0,", csv_path.read_text(encoding="utf-8"))
        bad = env.TMP / "bad.zip"
        import zipfile
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("x.txt", "nope")
        with self.assertRaises(ValueError):
            db.restore_backup(bad)

    def test_stale_lock_removed_fresh_kept(self):
        import os, time
        lock = env.TMP / "x.db.lock"
        lock.mkdir()
        db.remove_stale_lock(lock)
        self.assertTrue(lock.exists())
        os.utime(lock, (time.time() - 600,) * 2)
        db.remove_stale_lock(lock)
        self.assertFalse(lock.exists())
        db.remove_stale_lock(lock)  # already gone: no error


if __name__ == "__main__":
    unittest.main()
