"""Felles oppsett for testene: egne midlertidige mapper for config/data/timere, så testene aldri
rører ekte brukerdata, og en falsk systemctl. Importeres før appens moduler."""
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
# Pikselfontene, så tittel og mål blir som i appen (fontconfig leter i $XDG_DATA_HOME/fonts)
(TMP / "data" / "fonts").mkdir(parents=True)
for ttf in (ROOT / "packaging" / "fonts").glob("*.ttf"):
    (TMP / "data" / "fonts" / ttf.name).write_bytes(ttf.read_bytes())
sys.path.insert(0, str(ROOT))

import schedule  # noqa: E402

SYSTEMCTL_CALLS = []
schedule.TIMER_DIR = TMP / "systemd"
schedule.PACKAGED_DIR = TMP / "packaged-units"
schedule.systemctl = lambda *args: (SYSTEMCTL_CALLS.append(args), "Wed 2026-10-21 08:00:00 CEST" if "show" in args else "")[1]

import database as db  # noqa: E402

assert str(db.DB_PATH).startswith(str(TMP)), "testene må aldri bruke den ekte databasen"
