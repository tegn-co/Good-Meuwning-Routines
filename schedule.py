"""Schedule times, editable under ⚙ → schedule.

Stored under "schedule" in ~/.config/morgen-todo/config.json:
  morning – window opens (systemd timer morgen-todo.timer)
  hours   – reminder to log hours (morgen-todo-hours.timer)
  close   – window saves and closes itself
  lunch / lunch_end – the cat eats between these times
  morning_days / hours_days – weekdays for each reminder (0 = Monday)
apply_reminders() writes changes into the timers.
"""
import json
import os
import subprocess
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import database as db
import platforms

DEFAULTS = {
    "morning": "08:00", "morning_on": True,
    "hours": "15:00", "hours_on": True,
    "close": "16:30", "close_on": True,
    "lunch": "11:00", "lunch_end": "12:00",
    "morning_days": [0, 1, 2, 3, 4],
    "hours_days": [0, 1, 2, 3, 4],
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIMER_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
PACKAGED_DIR = Path("/usr/lib/systemd/user")  # timers installed by the package
TIMERS = {  # setting -> (timer file, description, Persistent)
    "morning": ("morgen-todo.timer", "Morning Routine: open the list", True),
    # Not Persistent: skip the reminder if the machine was off, or it could fire the next morning
    "hours": ("morgen-todo-hours.timer", "Morning Routine: remind to log hours", False),
}


def load():
    saved = db.load_config().get("schedule", {})
    if "days" in saved:  # older config: shared weekdays for both reminders
        saved.setdefault("morning_days", saved["days"])
        saved.setdefault("hours_days", saved.pop("days"))
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


def save(schedule):
    config = db.load_config()
    config["schedule"] = schedule
    db.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    db.CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def parse_hhmm(hhmm):
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


def next_reminder_time(sch, key, now=None):
    """Next time a reminder fires (used when the app schedules itself, as in Flatpak)."""
    if not sch[f"{key}_on"] or not sch[f"{key}_days"]:
        return "off"
    now = now or datetime.now()
    for add in range(8):
        day = now.date() + timedelta(days=add)
        at = datetime.combine(day, parse_hhmm(sch[key]))
        if day.weekday() in sch[f"{key}_days"] and at > now:
            return at.strftime("%a %Y-%m-%d %H:%M:%S")
    return "off"


def apply_reminders(schedule):
    """Write the times into the systemd timers and enable/disable them. Returns the next run per timer.
    Flatpak has no systemd timers: the app schedules itself (App.fire_due_reminders) and only
    asks to be started at login."""
    if platforms.USES_APP_SCHEDULER:
        platforms.set_autostart(any(schedule[f"{k}_on"] and schedule[f"{k}_days"] for k in TIMERS))
        return {k: next_reminder_time(schedule, k) for k in TIMERS}
    TIMER_DIR.mkdir(parents=True, exist_ok=True)  # missing for new users
    for key, (unit, description, persistent) in TIMERS.items():
        days = ",".join(DAY_NAMES[d] for d in sorted(schedule[f"{key}_days"])) or "Mon"  # no days = disabled below
        own = TIMER_DIR / unit
        if (PACKAGED_DIR / unit).exists():
            # Installed package: the timer comes from the package; we only put the time in a drop-in.
            # If the package is removed, the timer goes with it instead of pointing at nothing.
            if own.exists() and own.read_text(encoding="utf-8").startswith(("[Unit]\nDescription=Morgen-todo:", "[Unit]\nDescription=Morning Routine:")):
                own.unlink()  # full timer file written by older versions
            dropin = TIMER_DIR / f"{unit}.d" / "schedule.conf"
            dropin.parent.mkdir(exist_ok=True)
            dropin.write_text(f"[Timer]\nOnCalendar=\nOnCalendar={days} {schedule[key]}\n", encoding="utf-8")
        else:
            # Running from source: write the whole timer
            own.write_text(
                f"[Unit]\nDescription={description}\n\n"
                f"[Timer]\nOnCalendar={days} {schedule[key]}\n"
                + ("Persistent=true\n" if persistent else "")
                + "\n[Install]\nWantedBy=timers.target\n",
                encoding="utf-8",
            )
    systemctl("daemon-reload")
    for key, (unit, _, _) in TIMERS.items():
        on = schedule[f"{key}_on"] and schedule[f"{key}_days"]
        # daemon-reload is enough to apply the new time; a restart would make a Persistent timer
        # fire immediately
        systemctl("enable" if on else "disable", "--now", unit)
    return next_timer_runs()


def next_timer_runs():
    out = {}
    for key, (unit, _, _) in TIMERS.items():
        r = systemctl("show", unit, "--property=NextElapseUSecRealtime", "--value")
        out[key] = r.strip() or "off"
    return out


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=5).stdout
