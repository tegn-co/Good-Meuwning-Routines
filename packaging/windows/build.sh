#!/bin/sh
# Builds the Windows app folder with PyInstaller. Run inside an MSYS2 UCRT64 shell:
#   packaging/windows/build.sh 1.6.0   ->  packaging/windows/dist/MorningRoutine/
# The installer is then made with Inno Setup: iscc /DAppVersion=1.6.0 packaging\windows\installer.iss
set -eu
VERSION="${1:-0.0.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../.."
echo "$VERSION" > "$HERE/VERSION"
python packaging/make_icon.py "$HERE/icons" --ico "$HERE/morning-routine.ico"
python -m PyInstaller --noconfirm --clean --distpath "$HERE/dist" --workpath "$HERE/build" "$HERE/morning-routine.spec"
echo "$HERE/dist/MorningRoutine"
