"""SQLite database for morgen-todo, used by the window through a background thread.

Default location: ~/.local/share/morgen-todo/morgen-todo.db. Override with "db_path" in
~/.config/morgen-todo/config.json or the MORGEN_TODO_DB environment variable.
On a network drive (CIFS/NFS/SSHFS) lock files are used instead of normal SQLite locking,
and stale locks left after a crash are removed automatically.
"""
import csv
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
import queue
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "morgen-todo"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "morgen-todo"
IN_FLATPAK = Path("/.flatpak-info").exists()  # Flatpak has no systemd timers, so the app schedules itself
NETWORK_FS = {"cifs", "smb3", "smbfs", "nfs", "nfs4", "fuse.sshfs", "9p"}
STALE_LOCK_SECONDS = 60  # older locks are left from a crash (saves take under a second)


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def update_config(**changes):
    """Merge changes into config.json, keeping the other keys."""
    config = load_config()
    config.update(changes)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    return config


CONFIG = load_config()
DB_PATH = Path(os.environ.get("MORGEN_TODO_DB") or CONFIG.get("db_path") or DATA_DIR / "morgen-todo.db").expanduser()
EXPECTED_HOURS = float(CONFIG.get("expected_hours", 8))  # expected hours on weekdays


def is_on_network_drive(path):
    """Is the path on a network drive? (longest match in /proc/mounts)"""
    try:
        mounts = [line.split()[1:3] for line in Path("/proc/mounts").read_text().splitlines()]
    except OSError:
        return False
    path = str(path.resolve())
    best, fstype = "", ""
    for mountpoint, fs in mounts:
        mountpoint = mountpoint.replace("\\040", " ")
        if (path == mountpoint or path.startswith(mountpoint.rstrip("/") + "/")) and len(mountpoint) > len(best):
            best, fstype = mountpoint, fs
    return fstype in NETWORK_FS


def file_server_time(directory):
    """File server time (mtime of a probe file), so machines with a wrong clock don't steal live locks."""
    probe = directory / f".morgen-todo-clock-{os.getpid()}"
    probe.touch()
    try:
        return probe.stat().st_mtime
    finally:
        probe.unlink(missing_ok=True)


def remove_stale_lock(lock):
    try:
        if lock.exists() and file_server_time(lock.parent) - lock.stat().st_mtime > STALE_LOCK_SECONDS:
            lock.rmdir() if lock.is_dir() else lock.unlink()
    except FileNotFoundError:
        pass  # released (or cleaned up by another machine) in the meantime


def add_column_if_missing(conn, sql):
    """ALTER TABLE that tolerates another machine adding the column at the same time (shared database)."""
    try:
        conn.execute(sql)
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e):
            raise


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if is_on_network_drive(DB_PATH.parent):
        # Normal SQLite locking does not work on CIFS; use lock files and clear stale ones
        remove_stale_lock(Path(f"{DB_PATH}.lock"))
        conn = sqlite3.connect(f"file:{DB_PATH}?vfs=unix-dotfile", uri=True, timeout=5)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS days (
               date       TEXT PRIMARY KEY,
               checks     TEXT NOT NULL DEFAULT '{}',
               plan       TEXT NOT NULL DEFAULT '',
               meetings   TEXT NOT NULL DEFAULT '[]',
               updated_at TEXT NOT NULL
           )"""
    )
    cols = [c[1] for c in conn.execute("PRAGMA table_info(days)")]
    if "hours" not in cols:
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN hours REAL")
    if "day_off" not in cols:
        # Day off (vacation, sick, holiday): no expected hours
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN day_off INTEGER NOT NULL DEFAULT 0")
    if "complete" not in cols:
        # Whole list done that day (used for streaks)
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN complete INTEGER NOT NULL DEFAULT 0")
    if "expected" not in cols:
        # Expected hours are stored per day so changing the workday length doesn't alter past overtime.
        # Existing days get the current rule.
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN expected REAL")
        conn.execute(
            """UPDATE days SET expected = CASE WHEN day_off = 1 OR strftime('%w', date) IN ('0', '6')
                                               THEN 0 ELSE ? END
               WHERE expected IS NULL AND hours IS NOT NULL""", (EXPECTED_HOURS,))
        conn.commit()
    # Item order (fixed and routine items), shared by all days
    conn.execute("CREATE TABLE IF NOT EXISTS item_order (key TEXT PRIMARY KEY, position INTEGER NOT NULL)")
    # Fixed items (01–05) deleted in settings; can be restored
    conn.execute("CREATE TABLE IF NOT EXISTS hidden_items (key TEXT PRIMARY KEY)")
    # Custom routine items that recur daily; checks are stored per day in days.checks
    conn.execute(
        """CREATE TABLE IF NOT EXISTS routine (
               id       TEXT PRIMARY KEY,
               text     TEXT NOT NULL,
               position INTEGER NOT NULL
           )"""
    )
    # Settings, e.g. opening_balance = overtime earned before hour logging started
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    return conn


@contextmanager
def session():
    """One transaction; the connection is closed afterwards (no open files on a network drive)."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def expected_hours_for(day, day_off=False):
    """Expected hours for a day: 0 on weekends and days off."""
    return 0.0 if day_off or day.weekday() >= 5 else EXPECTED_HOURS


def unfinished_plan_tasks(plan, checks):
    """Unchecked plan tasks (lines starting with "-"); carried over to the next day."""
    checks = json.loads(checks)
    lines = (l.strip() for l in plan.splitlines())
    tasks = [l[1:].strip() for l in lines if l.startswith("-") and l[1:].strip()]
    return [t for t in tasks if not checks.get(f"p:{t}")]


def load_day(day):
    with session() as conn:
        row = conn.execute(
            "SELECT checks, plan, meetings, hours, day_off FROM days WHERE date = ?", (day.isoformat(),)
        ).fetchone()
        routine = [{"id": r[0], "text": r[1]} for r in conn.execute("SELECT id, text FROM routine ORDER BY position")]
        order = [r[0] for r in conn.execute("SELECT key FROM item_order ORDER BY position")]
        hidden = [r[0] for r in conn.execute("SELECT key FROM hidden_items")]
        prev = None
        # A row with an empty list (only hours logged under ⚙, e.g. in advance) counts as a new day
        fresh = not row or (row[0] == "{}" and row[1] == "" and row[2] == "[]")
        if fresh:
            # Last day the list was actually used (skip rows with only logged hours)
            prev = conn.execute(
                """SELECT plan, checks FROM days WHERE date < ? AND (plan != '' OR checks != '{}')
                   ORDER BY date DESC LIMIT 1""", (day.isoformat(),)
            ).fetchone()
    shared = {"routine": routine, "order": order, "hidden": hidden}
    if fresh:
        # New day: carry over unfinished plan tasks (keep hours logged in advance)
        plan = "\n".join(f"- {t}" for t in unfinished_plan_tasks(*prev)) if prev else ""
        hours, day_off = (row[3], bool(row[4])) if row else (None, False)
        return {"checks": {}, "plan": plan, "meetings": [], "hours": hours, "day_off": day_off, **shared}
    return {"checks": json.loads(row[0]), "plan": row[1], "meetings": json.loads(row[2]),
            "hours": row[3], "day_off": bool(row[4]), **shared}


def save_day(day, state):
    with session() as conn:
        conn.execute(
            """INSERT INTO days (date, checks, plan, meetings, updated_at, hours, day_off, expected, complete)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                 checks = excluded.checks, plan = excluded.plan, meetings = excluded.meetings,
                 updated_at = excluded.updated_at, hours = excluded.hours, day_off = excluded.day_off,
                 expected = excluded.expected, complete = excluded.complete""",
            (
                day.isoformat(),
                json.dumps(state["checks"]),
                state["plan"],
                json.dumps(state["meetings"], ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
                state["hours"],
                int(bool(state.get("day_off"))),
                expected_hours_for(day, state.get("day_off")),
                int(bool(state.get("complete"))),
            ),
        )
        conn.execute("DELETE FROM hidden_items")
        conn.executemany("INSERT INTO hidden_items (key) VALUES (?)", [(k,) for k in state["hidden"]])
        conn.execute("DELETE FROM item_order")
        conn.executemany("INSERT INTO item_order (key, position) VALUES (?, ?)",
                         [(k, i) for i, k in enumerate(state["order"])])
        conn.execute("DELETE FROM routine")
        conn.executemany("INSERT INTO routine (id, text, position) VALUES (?, ?, ?)",
                         [(r["id"], r["text"], i) for i, r in enumerate(state["routine"])])


def get_logged_hours(day):
    with session() as conn:
        row = conn.execute("SELECT hours, day_off FROM days WHERE date = ?", (day.isoformat(),)).fetchone()
    return {"hours": row[0], "day_off": bool(row[1])} if row else {"hours": None, "day_off": False}


def set_logged_hours(day, hours, day_off):
    """Log hours for another day (only hours and day off, not the list)."""
    with session() as conn:
        conn.execute(
            """INSERT INTO days (date, updated_at, hours, day_off, expected) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET hours = excluded.hours, day_off = excluded.day_off,
                                               updated_at = excluded.updated_at, expected = excluded.expected""",
            (day.isoformat(), datetime.now().isoformat(timespec="seconds"), hours, int(day_off),
             expected_hours_for(day, day_off)),
        )


def set_opening_balance(hours):
    """Overtime earned before logging hours here (set in the setup wizard)."""
    with session() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('opening_balance', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (hours,))


def streak_info(day, today_complete):
    """Workdays in a row with the whole list done (weekends and days off are skipped, not breaks).
    Today counts only once complete; otherwise the streak lives on from yesterday. Stores the best streak."""
    since = (day - timedelta(days=400)).isoformat()
    with session() as conn:
        rows = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT date, complete, day_off FROM days WHERE date >= ? AND date < ?", (since, day.isoformat()))}
        streak = 1 if today_complete else 0
        d = day - timedelta(days=1)
        for _ in range(400):
            complete, day_off = rows.get(d.isoformat(), (0, 0))
            if d.weekday() >= 5 or day_off:
                pass  # weekend/day off: skip
            elif complete:
                streak += 1
            else:
                break
            d -= timedelta(days=1)
        row = conn.execute("SELECT value FROM settings WHERE key = 'best_streak'").fetchone()
        best = max(int(row[0]) if row else 0, streak)
        conn.execute("INSERT INTO settings (key, value) VALUES ('best_streak', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (best,))
    return {"streak": streak, "best": best}


def overtime_summary(day):
    """Overtime (hours minus expected) in total, this week and this month; only logged, non-future days.
    Weekends and days off expect 0, so hours worked then count as overtime."""
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    month_start = day.replace(day=1).isoformat()
    with session() as conn:
        total, week, month, days = conn.execute(
            """WITH d AS (
                 SELECT date, hours - COALESCE(expected, CASE WHEN day_off = 1 OR strftime('%w', date) IN ('0', '6')
                                                         THEN 0 ELSE :e END) AS diff
                 FROM days WHERE hours IS NOT NULL AND date <= :d
               )
               SELECT COALESCE(SUM(diff), 0),
                      COALESCE(SUM(CASE WHEN date >= :w THEN diff END), 0),
                      COALESCE(SUM(CASE WHEN date >= :m THEN diff END), 0),
                      COUNT(*)
               FROM d""",
            {"e": EXPECTED_HOURS, "w": week_start, "m": month_start, "d": day.isoformat()},
        ).fetchone()
        row = conn.execute("SELECT value FROM settings WHERE key = 'opening_balance'").fetchone()
    opening = row[0] if row else 0
    return {"opening_balance": opening, "total": total + opening, "week": week, "month": month, "days_logged": days}


# --- Backup and export ---
BACKUP_CONFIG = ["config.json", "cat.json", "theme", "pomodoro-settings.json", "pomodoro.json"]


def export_backup(path):
    """Zip a consistent copy of the database and the settings files."""
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "morgen-todo.db"
        src, dst = connect(), sqlite3.connect(snap)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "morgen-todo.db")
            for name in BACKUP_CONFIG:
                if (CONFIG_DIR / name).exists():
                    z.write(CONFIG_DIR / name, f"config/{name}")
            z.writestr("README.txt", "Morning Routine backup. Restore it under ⚙ → backup → restore.\n")
    return str(path)


def restore_backup(path):
    """Replace the database and settings with a backup. The current database is first
    saved as <name>.before-restore.db. The database location (db_path) is kept."""
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
        names = z.namelist()
        if "morgen-todo.db" not in names:
            raise ValueError("this is not a Morning Routine backup")
        z.extract("morgen-todo.db", tmp)
        incoming = sqlite3.connect(Path(tmp) / "morgen-todo.db")
        try:
            incoming.execute("SELECT count(*) FROM days").fetchone()  # is it a valid database?
            if DB_PATH.exists():
                shutil.copy2(DB_PATH, DB_PATH.with_name(DB_PATH.stem + ".before-restore.db"))
            target = connect()
            try:
                incoming.backup(target)
            finally:
                target.close()
        finally:
            incoming.close()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        for name in BACKUP_CONFIG:
            if f"config/{name}" not in names:
                continue
            data = z.read(f"config/{name}")
            if name == "config.json":
                restored, current = json.loads(data), load_config()
                if "db_path" in current:
                    restored["db_path"] = current["db_path"]
                else:
                    restored.pop("db_path", None)
                data = json.dumps(restored, indent=2).encode()
            (CONFIG_DIR / name).write_bytes(data)


def export_hours_csv(path):
    """All logged hours as CSV (for timesheets)."""
    with session() as conn:
        rows = conn.execute(
            """SELECT date, hours, COALESCE(expected, ?), day_off FROM days
               WHERE hours IS NOT NULL ORDER BY date""", (EXPECTED_HOURS,)).fetchall()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "weekday", "hours", "expected", "overtime", "day_off"])
        for d, hours, expected, day_off in rows:
            w.writerow([d, date.fromisoformat(d).strftime("%A"), hours, expected, round(hours - expected, 2),
                        "yes" if day_off else ""])
    return len(rows)


class DatabaseWorker:
    """Runs database calls in order on a worker thread so the window doesn't freeze on a slow disk.
    Results are delivered on the GTK thread: callback(result, error)."""

    def __init__(self):
        self.jobs = queue.Queue()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        from gi.repository import GLib
        while True:
            fn, args, callback, done = self.jobs.get()
            try:
                result, error = fn(*args), None
            except Exception as e:  # noqa: BLE001 – shown in the status bar
                result, error = None, e
            if done:
                done.append((result, error))
                done[0].set()
            elif callback:
                GLib.idle_add(lambda r=result, e=error, cb=callback: cb(r, e) and False)

    def submit(self, fn, *args, callback=None):
        self.jobs.put((fn, args, callback, None))

    def run_sync(self, fn, *args, timeout=10):
        """Wait for the result (used when the window closes). Queued jobs run first."""
        done = [threading.Event()]
        self.jobs.put((fn, args, None, done))
        if not done[0].wait(timeout):
            raise TimeoutError("database did not answer")
        result, error = done[1]
        if error:
            raise error
        return result
