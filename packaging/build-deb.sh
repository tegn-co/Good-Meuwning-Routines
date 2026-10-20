#!/bin/sh
# Bygger morgen-todo_<versjon>_all.deb fra koden i mappa over.
# Bare kode, fonter og ikon kommer med – ingen database, config eller personlige innstillinger.
set -eu
VERSION="${1:-1.0.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(dirname "$HERE")"
OUT="$HERE/dist"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

install -d "$ROOT/DEBIAN" "$ROOT/usr/share/morgen-todo" "$ROOT/usr/bin" "$ROOT/usr/lib/morgen-todo" \
  "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/applications" "$ROOT/usr/share/fonts/truetype/morgen-todo" \
  "$ROOT/usr/share/doc/morgen-todo" "$ROOT/usr/share/icons/hicolor"

for f in widget.py cat.py cat_settings.py pomodoro.py db.py schedule.py onboarding.py; do
  install -m 644 "$SRC/$f" "$ROOT/usr/share/morgen-todo/$f"
done
install -m 755 "$HERE/files/morgen-todo" "$ROOT/usr/bin/morgen-todo"
install -m 755 "$HERE/files/morgen-todo-remind" "$ROOT/usr/lib/morgen-todo/morgen-todo-remind"
install -m 644 "$HERE/files/morgen-todo.service" "$HERE/files/morgen-todo-hours.service" "$ROOT/usr/lib/systemd/user/"
install -m 644 "$HERE/files/no.zivid.MorgenTodo.desktop" "$ROOT/usr/share/applications/"
install -m 644 "$HERE/fonts/Silkscreen-Regular.ttf" "$HERE/fonts/JetBrainsMono.ttf" "$ROOT/usr/share/fonts/truetype/morgen-todo/"
python3 "$HERE/make_icon.py" "$ROOT/usr/share/icons/hicolor"
find "$ROOT/usr/share/icons" -type f -exec chmod 644 {} +

cat > "$ROOT/usr/share/doc/morgen-todo/copyright" <<COPY
Morning Routine (morgen-todo)
Fonts: Silkscreen and JetBrains Mono, SIL Open Font License 1.1 (licence texts below).

==== Silkscreen ====
$(cat "$HERE/OFL-silkscreen.txt")

==== JetBrains Mono ====
$(cat "$HERE/OFL-jetbrainsmono.txt")
COPY

chmod 644 "$ROOT/usr/share/doc/morgen-todo/copyright"
SIZE="$(du -sk "$ROOT/usr" | cut -f1)"
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: morgen-todo
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, python3-cairo, gir1.2-gtk-4.0 (>= 4.12), gir1.2-adw-1 (>= 1.4), libnotify-bin, fontconfig
Maintainer: John Thein <john.thein@zivid.com>
Description: Morning checklist with a pixel cat
 Morning Routine opens a small window every morning with a checklist,
 a plan for the day, hours and overtime tracking and a pomodoro timer,
 with an animated pixel cat living on the title.
 Each user gets a fresh local database in ~/.local/share/morgen-todo.
CTRL
install -m 755 "$HERE/files/postinst" "$HERE/files/prerm" "$HERE/files/postrm" "$ROOT/DEBIAN/"

mkdir -p "$OUT"
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$OUT/morgen-todo_${VERSION}_all.deb" >/dev/null
echo "$OUT/morgen-todo_${VERSION}_all.deb"
