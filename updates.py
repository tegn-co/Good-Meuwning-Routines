"""Sjekker om det finnes en nyere versjon på GitHub, og oppdaterer den installerte pakken.

Versjonen står i fila VERSION ved siden av koden (legges inn av build-deb.sh). Kjøres appen fra
kildekoden, finnes ikke fila, og da sjekkes det ikke.
"""
import json
import os
import shutil
import urllib.request
from pathlib import Path

REPO = "tegn-co/Good-Meuwning-Routines"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
DEB_URL = f"https://github.com/{REPO}/releases/latest/download/morgen-todo_all.deb"
INSTALL_COMMAND = f"curl -fsSL https://raw.githubusercontent.com/{REPO}/main/install.sh | sh"
VERSION_FILE = Path(__file__).with_name("VERSION")
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "morgen-todo"


def installed_version():
    if Path("/.flatpak-info").exists():
        return None  # Flatpak oppdateres med «flatpak update» / ny pakke, ikke herfra
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return None  # kjører fra kildekoden


def parse(version):
    return tuple(int(p) for p in version.lstrip("v").split(".") if p.isdigit())


def latest_version():
    """Siste release på GitHub, f.eks. «1.1.2» (kalles i bakgrunnstråden)."""
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())["tag_name"].lstrip("v")


def newer_available():
    """(installert, nyeste) hvis det finnes en nyere versjon, ellers None."""
    current = installed_version()
    if not current:
        return None
    latest = latest_version()
    return (current, latest) if parse(latest) > parse(current) else None


def download():
    """Last ned nyeste .deb til cache-mappa (bakgrunnstråden). Returnerer stien."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "morgen-todo_all.deb"
    req = urllib.request.Request(DEB_URL, headers={"User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    path.chmod(0o644)  # apt leser fila som sin egen bruker
    CACHE.chmod(0o755)
    return path


def install_command(path):
    """Kommando som installerer pakken med et grafisk passordvindu (pkexec), eller None."""
    pkexec = shutil.which("pkexec")
    return [pkexec, "apt-get", "install", "-y", str(path)] if pkexec else None
