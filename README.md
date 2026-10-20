# Good-Meuwning-Routines
Dont forget you morning routines, and dont forget to feed you cat!

**Morning Routine** is a small GTK4 desktop app for Ubuntu with a morning checklist,
a plan for the day, hours and overtime tracking, a pomodoro timer and an animated
pixel cat that lives on the title.

## Install
Download `morgen-todo_<version>_all.deb` and run:

```sh
sudo apt install ./morgen-todo_1.0.0_all.deb
```

Then open **Morning Routine** from the app menu. On the first start a short tutorial
explains everything and lets you choose your work day, reminders and whether to pin
the app to the dock.

Requires Ubuntu 24.04 or newer (GTK ≥ 4.12, libadwaita ≥ 1.4).

## Your data
Every user gets a fresh local database – nothing is shared:

| What | Where |
|---|---|
| Checklist, plan, hours | `~/.local/share/morgen-todo/morgen-todo.db` |
| Settings (work day, schedule, cat, theme) | `~/.config/morgen-todo/` |

To keep the database somewhere else (e.g. a network drive), set `"db_path"` in
`~/.config/morgen-todo/config.json` or the `MORGEN_TODO_DB` environment variable.

## Build the .deb
```sh
./packaging/build-deb.sh 1.0.0      # -> packaging/dist/morgen-todo_1.0.0_all.deb
```

## Run from source
```sh
python3 widget.py              # the app
python3 widget.py --cat=climb  # force a cat animation (walk, play, sleep, sit, jump, climb, eat)
```

| File | |
|---|---|
| `widget.py` | main window: list, plan, hours, settings |
| `cat.py` | the pixel cat and title animations |
| `cat_settings.py` | cat breed, colors and phrases |
| `pomodoro.py` | pomodoro panel |
| `db.py` | SQLite database |
| `schedule.py` | times for opening, reminders, auto close and lunch |
| `onboarding.py` | first-start tutorial and setup |
| `packaging/` | .deb build script, icon generator, fonts (SIL OFL 1.1) |
