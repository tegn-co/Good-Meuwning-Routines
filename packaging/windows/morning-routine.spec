# PyInstaller recipe for the Windows build (run by packaging/windows/build.sh inside MSYS2 UCRT64)
import os

root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
modules = ["cat", "cat_tricks", "cat_panel", "pomodoro_panel", "database", "schedule", "tutorial", "updater",
           "translations", "weather", "platforms"]

a = Analysis(
    [os.path.join(root, "app.py")],
    pathex=[root],
    datas=[(os.path.join(root, "packaging", "fonts"), "fonts"),
           (os.path.join(SPECPATH, "VERSION"), ".")],
    hiddenimports=modules + ["winreg", "gi.repository.Adw", "gi.repository.Graphene", "gi.repository.PangoCairo"],
    hookspath=[os.path.join(SPECPATH, "hooks")],
    hooksconfig={"gi": {"module-versions": {"Gtk": "4.0", "Gdk": "4.0"},
                        "icons": ["Adwaita"], "themes": ["Adwaita"], "languages": ["nb", "en"]}},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MorningRoutine",
          icon=os.path.join(SPECPATH, "morning-routine.ico"), console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MorningRoutine")
