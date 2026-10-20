import unittest
from datetime import date, timedelta

from tests import env  # noqa: F401  (midlertidige mapper)
import db

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

    def test_overtime_weekend_and_day_off(self):
        db.save_day(MON, state(hours=9))                     # +1
        db.set_hours(MON + timedelta(days=1), 3, True)        # fridag: +3
        db.set_hours(MON + timedelta(days=2), 6, False)       # -2
        db.set_hours(MON + timedelta(days=5), 2, False)       # lørdag: +2
        s = db.summary(MON + timedelta(days=6))
        self.assertAlmostEqual(s["total"], 4.0)
        self.assertEqual(s["days_logged"], 4)

    def test_future_days_not_counted(self):
        db.set_hours(MON + timedelta(days=30), 8, False)
        self.assertEqual(db.summary(MON)["days_logged"], 0)

    def test_changing_work_day_keeps_past_overtime(self):
        db.save_day(MON, state(hours=9))
        db.EXPECTED_HOURS = 7.0
        self.assertAlmostEqual(db.summary(MON)["total"], 1.0)

    def test_opening_balance(self):
        db.set_opening_balance(5)
        self.assertAlmostEqual(db.summary(MON)["total"], 5.0)

    def test_unfinished_plan_carries_over(self):
        db.save_day(MON, state(plan="- open\n- done\nnote", checks={"p:done": True}))
        self.assertEqual(db.load_day(MON + timedelta(days=1))["plan"], "- open")

    def test_carry_over_survives_prelogged_hours(self):
        db.save_day(MON, state(plan="- open"))
        db.set_hours(MON + timedelta(days=1), 0, True)
        d = db.load_day(MON + timedelta(days=1))
        self.assertEqual((d["plan"], d["day_off"]), ("- open", True))

    def test_routine_order_hidden_are_shared(self):
        db.save_day(MON, state(routine=[{"id": "a", "text": "Water"}], order=["r:a", "email"], hidden=["jira"]))
        d = db.load_day(MON + timedelta(days=3))
        self.assertEqual((d["routine"][0]["text"], d["order"], d["hidden"]), ("Water", ["r:a", "email"], ["jira"]))

    def test_streak_skips_weekend_and_day_off(self):
        fri = MON + timedelta(days=4)
        db.save_day(MON + timedelta(days=3), state(complete=True))   # torsdag
        db.save_day(fri, state(complete=True))                          # fredag
        db.set_hours(MON + timedelta(days=7), 0, True)                  # mandag: fri
        tue = MON + timedelta(days=8)
        self.assertEqual(db.streak_info(tue, False)["streak"], 2)      # helg + fridag bryter ikke
        self.assertEqual(db.streak_info(tue, True), {"streak": 3, "best": 3})
        self.assertEqual(db.streak_info(tue + timedelta(days=2), False), {"streak": 0, "best": 3})  # onsdag mangler

    def test_stale_lock_removed_fresh_kept(self):
        import os, time
        lock = env.TMP / "x.db.lock"
        lock.mkdir()
        db.remove_stale_lock(lock)
        self.assertTrue(lock.exists())
        os.utime(lock, (time.time() - 600,) * 2)
        db.remove_stale_lock(lock)
        self.assertFalse(lock.exists())
        db.remove_stale_lock(lock)  # finnes ikke: ingen feil


if __name__ == "__main__":
    unittest.main()
