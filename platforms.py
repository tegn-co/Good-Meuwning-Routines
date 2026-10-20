"""Everything that differs between Linux (.deb / Flatpak) and Windows.

Folders, how reminders are scheduled, start at login, notifications, bundled fonts and restarting.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IN_FLATPAK = Path("/.flatpak-info").exists()
FROZEN = getattr(sys, "frozen", False)  # Windows build made with PyInstaller

# Linux .deb uses systemd timers; Flatpak and Windows have none, so the app schedules reminders itself
USES_APP_SCHEDULER = IN_FLATPAK or IS_WINDOWS

APP_ID = "no.zivid.MorgenTodo"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"  # Windows: programs started at login


def _windows_dir(var, fallback):
    return Path(os.environ.get(var) or Path.home() / fallback) / "Morning Routine"


def config_dir():
    if IS_WINDOWS and not os.environ.get("XDG_CONFIG_HOME"):  # XDG_* still wins, e.g. in tests
        return _windows_dir("APPDATA", "AppData/Roaming")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "morgen-todo"


def data_dir():
    if IS_WINDOWS and not os.environ.get("XDG_DATA_HOME"):
        return _windows_dir("LOCALAPPDATA", "AppData/Local")
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "morgen-todo"


def cache_dir():
    if IS_WINDOWS:
        return data_dir() / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "morgen-todo"


def app_dir():
    """Folder with the app's own files (next to the code, or inside the Windows bundle)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def launch_command(*args):
    """Command line that starts the app again."""
    if FROZEN:
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve().with_name("app.py")), *args]


def restart():
    """Replace this process with a fresh copy of the app."""
    cmd = launch_command()
    if IS_WINDOWS:
        subprocess.Popen(cmd, close_fds=True)
        os._exit(0)
    os.execv(cmd[0], cmd)


def set_autostart(enabled):
    """Start the app hidden at login, so it can open the list and remind about hours on time."""
    if IS_WINDOWS:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                command = " ".join(f'"{part}"' for part in launch_command("--background"))
                winreg.SetValueEx(key, "Morning Routine", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "Morning Routine")
                except FileNotFoundError:
                    pass
    elif IN_FLATPAK:
        _request_flatpak_background(enabled)


def _request_flatpak_background(autostart):
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


def resize_window(window, width_change):
    """Windows: GTK only applies a new default size when the window is next laid out, so resize the
    native window directly (SetWindowPos) by the same amount. No-op elsewhere."""
    if not IS_WINDOWS or not width_change:
        return
    try:
        import ctypes
        from ctypes import wintypes
        import gi
        gi.require_version("GdkWin32", "4.0")
        from gi.repository import GdkWin32
        hwnd = GdkWin32.Win32Surface.get_handle(window.get_surface())
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        scale = window.get_surface().get_scale()
        new_width = rect.right - rect.left + round(width_change * scale)
        SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x2, 0x4, 0x10
        user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, new_width, rect.bottom - rect.top,
                            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
    except Exception:  # noqa: BLE001 – fall back to GTK's default size
        pass


def notify(title, body, urgent=False):
    """Desktop notification. notify-send on Linux; elsewhere through GApplication (may be ignored)."""
    if not IS_WINDOWS and shutil.which("notify-send"):
        cmd = ["notify-send", "-i", APP_ID, title, body] + (["-u", "critical"] if urgent else [])
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    from gi.repository import Gio
    app = Gio.Application.get_default()
    if app:
        note = Gio.Notification.new(title)
        note.set_body(body)
        app.send_notification(None, note)


def register_fonts():
    """Windows: make the bundled pixel fonts available (on Linux the package installs them system-wide)."""
    if not IS_WINDOWS:
        return
    import ctypes
    import winreg
    fonts = sorted((app_dir() / "fonts").glob("*.ttf"))
    try:  # Pango 1.56+ can load a font file directly
        from gi.repository import PangoCairo
        fontmap = PangoCairo.FontMap.get_default()
        if hasattr(fontmap, "add_font_file") and all(fontmap.add_font_file(str(f)) for f in fonts):
            return
    except Exception:  # noqa: BLE001
        pass
    # Otherwise install them for this user; DirectWrite (used by GTK) sees per-user fonts, no admin needed
    user_fonts = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"
    user_fonts.mkdir(parents=True, exist_ok=True)
    key_path = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        for ttf in fonts:
            target = user_fonts / ttf.name
            if not target.exists():
                shutil.copyfile(ttf, target)
            winreg.SetValueEx(key, f"{ttf.stem} (TrueType)", 0, winreg.REG_SZ, str(target))
            ctypes.windll.gdi32.AddFontResourceW(str(target))
