"""Databasen for morgen-todo (SQLite), brukt direkte av vinduet via en bakgrunnstråd.

Plassering: ~/.local/share/morgen-todo/morgen-todo.db som standard. Kan overstyres med
"db_path" i ~/.config/morgen-todo/config.json eller miljøvariabelen MORGEN_TODO_DB.
Ligger databasen på en nettverksdisk (CIFS/NFS/SSHFS), brukes lock-filer i stedet for vanlig
SQLite-låsing, og gjenglemte låser etter et krasj ryddes bort automatisk.
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
IN_FLATPAK = Path("/.flatpak-info").exists()  # kjører som Flatpak: ingen systemd-timere, appen planlegger selv
NETWORK_FS = {"cifs", "smb3", "smbfs", "nfs", "nfs4", "fuse.sshfs", "9p"}
STALE_LOCK_SECONDS = 60  # en lås eldre enn dette er etter et krasj (lagringer tar under ett sekund)


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def update_config(**changes):
    """Slå sammen endringer inn i config.json (resten av fila beholdes)."""
    config = load_config()
    config.update(changes)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    return config


CONFIG = load_config()
DB_PATH = Path(os.environ.get("MORGEN_TODO_DB") or CONFIG.get("db_path") or DATA_DIR / "morgen-todo.db").expanduser()
EXPECTED_HOURS = float(CONFIG.get("expected_hours", 8))  # forventet arbeidstid på hverdager


def is_on_network_drive(path):
    """Ligger stien på en nettverksdisk? (lengste treff i /proc/mounts)"""
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
    """Klokka på filserveren (mtime på en fil vi lager der), så maskiner med feil klokke ikke tar andres låser."""
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
        pass  # låsen ble frigjort (eller ryddet av en annen) i mellomtiden


def add_column_if_missing(conn, sql):
    """ALTER TABLE som tåler at en annen maskin la til kolonnen samtidig (delt database)."""
    try:
        conn.execute(sql)
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e):
            raise


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if is_on_network_drive(DB_PATH.parent):
        # Vanlig SQLite-låsing virker ikke på CIFS; bruk lock-filer, og fjern en lås som er blitt liggende
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
        # Fridag (ferie, syk, helligdag): ingen forventet arbeidstid den dagen
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN day_off INTEGER NOT NULL DEFAULT 0")
    if "complete" not in cols:
        # Hele listen ferdig den dagen (brukes til streaks)
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN complete INTEGER NOT NULL DEFAULT 0")
    if "expected" not in cols:
        # Forventet tid lagres per dag, så en ny arbeidsdag-lengde ikke endrer gammel overtid.
        # Eksisterende dager får dagens regel.
        add_column_if_missing(conn, "ALTER TABLE days ADD COLUMN expected REAL")
        conn.execute(
            """UPDATE days SET expected = CASE WHEN day_off = 1 OR strftime('%w', date) IN ('0', '6')
                                               THEN 0 ELSE ? END
               WHERE expected IS NULL AND hours IS NOT NULL""", (EXPECTED_HOURS,))
        conn.commit()
    # Rekkefølgen på punktene i listen (faste punkter og rutinepunkter), lik for alle dager
    conn.execute("CREATE TABLE IF NOT EXISTS item_order (key TEXT PRIMARY KEY, position INTEGER NOT NULL)")
    # Faste punkter (01–05) som er slettet i settings; kan gjenopprettes
    conn.execute("CREATE TABLE IF NOT EXISTS hidden_items (key TEXT PRIMARY KEY)")
    # Egne rutinepunkter som kommer tilbake hver dag; avkryssing lagres per dag i days.checks
    conn.execute(
        """CREATE TABLE IF NOT EXISTS routine (
               id       TEXT PRIMARY KEY,
               text     TEXT NOT NULL,
               position INTEGER NOT NULL
           )"""
    )
    # Innstillinger, f.eks. opening_balance = overtid opparbeidet før timeføringen startet
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    return conn


@contextmanager
def session():
    """Én transaksjon; tilkoblingen lukkes etterpå (ingen åpne filer på nettverksdisken)."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def expected_hours_for(day, day_off=False):
    """Forventet arbeidstid en gitt dag: 0 i helgen og på fridager."""
    return 0.0 if day_off or day.weekday() >= 5 else EXPECTED_HOURS


def unfinished_plan_tasks(plan, checks):
    """Plan-oppgaver (linjer som starter med «-») som ikke ble krysset av; tas med til neste dag."""
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
        # En rad uten noe i listen (bare timer ført under ⚙, f.eks. på forhånd) regnes som en ny dag
        fresh = not row or (row[0] == "{}" and row[1] == "" and row[2] == "[]")
        if fresh:
            # Siste dag listen faktisk ble brukt (ikke rader som bare har timer ført i settings)
            prev = conn.execute(
                """SELECT plan, checks FROM days WHERE date < ? AND (plan != '' OR checks != '{}')
                   ORDER BY date DESC LIMIT 1""", (day.isoformat(),)
            ).fetchone()
    shared = {"routine": routine, "order": order, "hidden": hidden}
    if fresh:
        # Ny dag: uferdige plan-oppgaver fra forrige dag blir med (timer ført på forhånd beholdes)
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
    """Før timer for en annen dag (endrer bare timer og fridag, ikke listen)."""
    with session() as conn:
        conn.execute(
            """INSERT INTO days (date, updated_at, hours, day_off, expected) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET hours = excluded.hours, day_off = excluded.day_off,
                                               updated_at = excluded.updated_at, expected = excluded.expected""",
            (day.isoformat(), datetime.now().isoformat(timespec="seconds"), hours, int(day_off),
             expected_hours_for(day, day_off)),
        )


def set_opening_balance(hours):
    """Overtid opparbeidet før man begynte å føre timer her (settes i oppstartsveiviseren)."""
    with session() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('opening_balance', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (hours,))


def streak_info(day, today_complete):
    """Hvor mange arbeidsdager på rad hele listen er gjort (helg og fridager hoppes over, bryter ikke).
    I dag teller bare når den er ferdig; ellers lever rekka fortsatt fra i går. Beste streak lagres."""
    since = (day - timedelta(days=400)).isoformat()
    with session() as conn:
        rows = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT date, complete, day_off FROM days WHERE date >= ? AND date < ?", (since, day.isoformat()))}
        streak = 1 if today_complete else 0
        d = day - timedelta(days=1)
        for _ in range(400):
            complete, day_off = rows.get(d.isoformat(), (0, 0))
            if d.weekday() >= 5 or day_off:
                pass  # helg/fridag: hopp over
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
    """Overtid (timer minus forventet tid) totalt, denne uka og denne måneden; bare dager med førte timer,
    og ikke dager fram i tid. Helg og fridager har forventet tid 0, så timer da teller som overtid."""
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


# --- Sikkerhetskopi og eksport ---
BACKUP_CONFIG = ["config.json", "cat.json", "theme", "pomodoro-settings.json", "pomodoro.json"]


def export_backup(path):
    """Zip med en konsistent kopi av databasen og innstillingsfilene."""
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
    """Erstatt databasen og innstillingene med en sikkerhetskopi. Den nåværende databasen
    lagres først som <navn>.before-restore.db. Hvor databasen ligger (db_path) beholdes."""
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
        names = z.namelist()
        if "morgen-todo.db" not in names:
            raise ValueError("this is not a Morning Routine backup")
        z.extract("morgen-todo.db", tmp)
        incoming = sqlite3.connect(Path(tmp) / "morgen-todo.db")
        try:
            incoming.execute("SELECT count(*) FROM days").fetchone()  # er det en gyldig database?
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
    """Alle førte timer som CSV (til timelister)."""
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
    """Kjører databasekall i rekkefølge på en egen tråd, så vinduet ikke fryser når disken er treg.
    Resultatet leveres tilbake på GTK-tråden: callback(resultat, feil)."""

    def __init__(self):
        self.jobs = queue.Queue()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        from gi.repository import GLib
        while True:
            fn, args, callback, done = self.jobs.get()
            try:
                result, error = fn(*args), None
            except Exception as e:  # noqa: BLE001 – feilen vises i statuslinja
                result, error = None, e
            if done:
                done.append((result, error))
                done[0].set()
            elif callback:
                GLib.idle_add(lambda r=result, e=error, cb=callback: cb(r, e) and False)

    def submit(self, fn, *args, callback=None):
        self.jobs.put((fn, args, callback, None))

    def run_sync(self, fn, *args, timeout=10):
        """Vent på resultatet (brukes når vinduet lukkes). Køen foran kjøres ferdig først."""
        done = [threading.Event()]
        self.jobs.put((fn, args, None, done))
        if not done[0].wait(timeout):
            raise TimeoutError("database did not answer")
        result, error = done[1]
        if error:
            raise error
        return result
