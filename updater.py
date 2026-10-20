"""Checks GitHub for a newer version and updates the installed package.

The version is read from the VERSION file next to the code (added by build-deb.sh). When running
from source the file is missing, so no check is done.
"""
import json
import os
import shutil
import urllib.request
from pathlib import Path

import platforms

REPO = "tegn-co/Good-Meuwning-Routines"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
DEB_URL = f"https://github.com/{REPO}/releases/latest/download/morgen-todo_all.deb"
SETUP_URL = f"https://github.com/{REPO}/releases/latest/download/MorningRoutine-Setup.exe"
INSTALL_COMMAND = f"curl -fsSL https://raw.githubusercontent.com/{REPO}/main/install.sh | sh"
VERSION_FILE = platforms.app_dir() / "VERSION"
CACHE = platforms.cache_dir()


def installed_version():
    if platforms.IN_FLATPAK:
        return None  # Flatpak updates via "flatpak update" / a new bundle, not from here
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
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
    """Download the latest .deb (Linux) or installer (Windows) to the cache dir. Returns the path."""
    CACHE.mkdir(parents=True, exist_ok=True)
    url, name = (SETUP_URL, "MorningRoutine-Setup.exe") if platforms.IS_WINDOWS else (DEB_URL, "morgen-todo_all.deb")
    path = CACHE / name
    req = urllib.request.Request(url, headers={"User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    if not platforms.IS_WINDOWS:
        path.chmod(0o644)  # apt reads the file as its own user
        CACHE.chmod(0o755)
    return path


def install_command(path):
    """Command that installs the update: the installer itself on Windows, apt via a graphical
    password prompt (pkexec) on Linux, or None."""
    if platforms.IS_WINDOWS:
        return [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    pkexec = shutil.which("pkexec")
    return [pkexec, "apt-get", "install", "-y", str(path)] if pkexec else None
