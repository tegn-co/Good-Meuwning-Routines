"""Tidspunktene programmet bruker, redigerbare under ⚙ → schedule.

Lagres under "schedule" i ~/.config/morgen-todo/config.json:
  morning – vinduet åpnes (systemd-timeren morgen-todo.timer)
  hours   – påminnelse om timeføring (morgen-todo-hours.timer)
  close   – vinduet lagrer og lukker seg selv
  lunch / lunch_end – katten spiser mellom disse tidene
  morning_days / hours_days – ukedagene hver påminnelse gjelder (0 = mandag)
Endringer skrives inn i timerne med apply_timers().
"""
import json
import os
import subprocess
from datetime import time as dtime
from pathlib import Path

import db

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
TIMERS = {  # innstilling -> (timer-fil, beskrivelse, Persistent)
    "morning": ("morgen-todo.timer", "Morgen-todo: åpne listen", True),
    # Påminnelsen hoppes over hvis maskinen var av, ellers kunne den kommet neste morgen
    "hours": ("morgen-todo-hours.timer", "Morgen-todo: påminnelse om timeføring", False),
}


def load():
    saved = db.load_config().get("schedule", {})
    if "days" in saved:  # eldre oppsett: felles ukedager for begge påminnelsene
        saved.setdefault("morning_days", saved["days"])
        saved.setdefault("hours_days", saved.pop("days"))
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


def save(schedule):
    config = db.load_config()
    config["schedule"] = schedule
    db.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    db.CONFIG_FILE.write_text(json.dumps(config, indent=2))


def parse(hhmm):
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


def apply_timers(schedule):
    """Skriv tidene inn i systemd-timerne og slå dem av/på. Returnerer neste kjøring per timer."""
    TIMER_DIR.mkdir(parents=True, exist_ok=True)  # finnes ikke hos nye brukere
    for key, (unit, description, persistent) in TIMERS.items():
        days = ",".join(DAY_NAMES[d] for d in sorted(schedule[f"{key}_days"])) or "Mon"  # ingen dager = slått av under
        (TIMER_DIR / unit).write_text(
            f"[Unit]\nDescription={description}\n\n"
            f"[Timer]\nOnCalendar={days} {schedule[key]}\n"
            + ("Persistent=true\n" if persistent else "")
            + "\n[Install]\nWantedBy=timers.target\n"
        )
    systemctl("daemon-reload")
    for key, (unit, _, _) in TIMERS.items():
        on = schedule[f"{key}_on"] and schedule[f"{key}_days"]
        # daemon-reload over er nok til at nytt tidspunkt gjelder; restart ville fått en Persistent-timer
        # til å kjøre med en gang
        systemctl("enable" if on else "disable", "--now", unit)
    return next_runs()


def next_runs():
    out = {}
    for key, (unit, _, _) in TIMERS.items():
        r = systemctl("show", unit, "--property=NextElapseUSecRealtime", "--value")
        out[key] = r.strip() or "off"
    return out


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=10).stdout
