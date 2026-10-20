"""Shared test setup: temporary config/data/timer dirs so tests never touch real user data,
plus a fake systemctl. Import before the app modules."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="morgen-todo-test-"))
os.environ["XDG_CONFIG_HOME"] = str(TMP / "config")
os.environ["XDG_DATA_HOME"] = str(TMP / "data")
os.environ.pop("MORGEN_TODO_DB", None)
os.environ.setdefault("GTK_A11Y", "none")
# Pixel fonts, so titles and sizes match the app (fontconfig looks in $XDG_DATA_HOME/fonts)
(TMP / "data" / "fonts").mkdir(parents=True)
for ttf in (ROOT / "packaging" / "fonts").glob("*.ttf"):
    (TMP / "data" / "fonts" / ttf.name).write_bytes(ttf.read_bytes())
sys.path.insert(0, str(ROOT))

import platforms  # noqa: E402
import schedule  # noqa: E402

AUTOSTART_CALLS = []
platforms.set_autostart = AUTOSTART_CALLS.append  # never touch the real login items / registry

SYSTEMCTL_CALLS = []
schedule.TIMER_DIR = TMP / "systemd"
schedule.PACKAGED_DIR = TMP / "packaged-units"
schedule.systemctl = lambda *args: (SYSTEMCTL_CALLS.append(args), "Wed 2026-10-21 08:00:00 CEST" if "show" in args else "")[1]

import database as db  # noqa: E402

assert str(db.DB_PATH).startswith(str(TMP)), "tests must never use the real database"
