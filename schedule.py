"""Tidspunktene programmet bruker, redigerbare under ⚙ → schedule.

Lagres under "schedule" i ~/.config/morgen-todo/config.json:
  morning – vinduet åpnes (systemd-timeren morgen-todo.timer)
  hours   – påminnelse om timeføring (morgen-todo-hours.timer)
  close   – vinduet lagrer og lukker seg selv
  lunch / lunch_end – katten spiser mellom disse tidene
  morning_days / hours_days – ukedagene hver påminnelse gjelder (0 = mandag)
Endringer skrives inn i timerne med apply_reminders().
"""
import json
import os
import subprocess
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import database as db

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
PACKAGED_DIR = Path("/usr/lib/systemd/user")  # timerne pakken installerer
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


def parse_hhmm(hhmm):
    h, m = hhmm.split(":")
    return dtime(int(h), int(m))


def next_reminder_time(sch, key, now=None):
    """Neste gang en påminnelse skal gå (brukes når appen planlegger selv, som Flatpak)."""
    if not sch[f"{key}_on"] or not sch[f"{key}_days"]:
        return "off"
    now = now or datetime.now()
    for add in range(8):
        day = now.date() + timedelta(days=add)
        at = datetime.combine(day, parse_hhmm(sch[key]))
        if day.weekday() in sch[f"{key}_days"] and at > now:
            return at.strftime("%a %Y-%m-%d %H:%M:%S")
    return "off"


def request_autostart(autostart):
    """Flatpak: be systemet om å starte appen usynlig ved innlogging (Background-portalen)."""
    from gi.repository import Gio, GLib
    opts = {
        "reason": GLib.Variant("s", "Open your morning list and remind you to log hours"),
        "autostart": GLib.Variant("b", autostart),
        "commandline": GLib.Variant("as", ["morgen-todo", "--background"]),
        "dbus-activatable": GLib.Variant("b", False),
    }
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                  "org.freedesktop.portal.Background", "RequestBackground",
                  GLib.Variant("(sa{sv})", ("", opts)), None, Gio.DBusCallFlags.NONE, 5000, None)


def apply_reminders(schedule):
    """Skriv tidene inn i systemd-timerne og slå dem av/på. Returnerer neste kjøring per timer.
    Som Flatpak finnes ingen systemd-timere: appen planlegger selv (App.fire_due_reminders), og ber bare
    om å bli startet ved innlogging."""
    if db.IN_FLATPAK:
        request_autostart(any(schedule[f"{k}_on"] and schedule[f"{k}_days"] for k in TIMERS))
        return {k: next_reminder_time(schedule, k) for k in TIMERS}
    TIMER_DIR.mkdir(parents=True, exist_ok=True)  # finnes ikke hos nye brukere
    for key, (unit, description, persistent) in TIMERS.items():
        days = ",".join(DAY_NAMES[d] for d in sorted(schedule[f"{key}_days"])) or "Mon"  # ingen dager = slått av under
        own = TIMER_DIR / unit
        if (PACKAGED_DIR / unit).exists():
            # Installert pakke: timeren kommer fra pakken, vi legger bare tidspunktet i en drop-in.
            # Fjernes pakken, forsvinner timeren med den i stedet for å stå igjen og peke på ingenting.
            if own.exists() and own.read_text().startswith("[Unit]\nDescription=Morgen-todo:"):
                own.unlink()  # hel timer-fil skrevet av eldre versjoner
            dropin = TIMER_DIR / f"{unit}.d" / "schedule.conf"
            dropin.parent.mkdir(exist_ok=True)
            dropin.write_text(f"[Timer]\nOnCalendar=\nOnCalendar={days} {schedule[key]}\n")
        else:
            # Kjørt fra kildekoden: skriv hele timeren selv
            own.write_text(
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
    return next_timer_runs()


def next_timer_runs():
    out = {}
    for key, (unit, _, _) in TIMERS.items():
        r = systemctl("show", unit, "--property=NextElapseUSecRealtime", "--value")
        out[key] = r.strip() or "off"
    return out


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=5).stdout
