"""Checks GitHub for a newer version and updates the installed package.

The version is read from the VERSION file next to the code (added by build-deb.sh). When running
from source the file is missing, so no check is done.
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
        return None  # Flatpak updates via "flatpak update" / a new bundle, not from here
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return None  # running from source


def parse_version(version):
    return tuple(int(p) for p in version.lstrip("v").split(".") if p.isdigit())


def latest_version():
    """Latest GitHub release, e.g. "1.1.2" (called on the background thread)."""
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())["tag_name"].lstrip("v")


def check_for_newer_version():
    """(installed, latest) if a newer version exists, else None."""
    current = installed_version()
    if not current:
        return None
    latest = latest_version()
    return (current, latest) if parse_version(latest) > parse_version(current) else None


def download_latest_package():
    """Download the latest .deb to the cache dir (background thread). Returns the path."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "morgen-todo_all.deb"
    req = urllib.request.Request(DEB_URL, headers={"User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    path.chmod(0o644)  # apt reads the file as its own user
    CACHE.chmod(0o755)
    return path


def install_command(path):
    """Command that installs the package with a graphical password prompt (pkexec), or None."""
    pkexec = shutil.which("pkexec")
    return [pkexec, "apt-get", "install", "-y", str(path)] if pkexec else None
