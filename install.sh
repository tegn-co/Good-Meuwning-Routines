#!/bin/sh
# Installs or updates Morning Routine from the latest GitHub release.
#   curl -fsSL https://raw.githubusercontent.com/tegn-co/Good-Meuwning-Routines/main/install.sh | sh
# Your data (~/.local/share/morgen-todo, ~/.config/morgen-todo) is never touched.
set -eu

REPO="tegn-co/Good-Meuwning-Routines"
URL="https://github.com/$REPO/releases/latest/download/morgen-todo_all.deb"
FLATPAK_URL="https://github.com/$REPO/releases/latest/download/morgen-todo.flatpak"

say() { printf '\033[38;5;209m=^.^=\033[0m %s\n' "$*"; }
fail() { printf '\033[31m=x.x=\033[0m %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "Please install curl first."

# Not Ubuntu/Debian: use the Flatpak build (works on all distros)
if ! command -v apt-get >/dev/null 2>&1; then
  command -v flatpak >/dev/null 2>&1 || fail "Morning Routine needs Ubuntu/Debian (apt) or Flatpak – see https://flatpak.org/setup/"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "Downloading Morning Routine (Flatpak)…"
  curl -fL --progress-bar -o "$TMP/morgen-todo.flatpak" "$FLATPAK_URL" || fail "Download failed: $FLATPAK_URL"
  say "Installing (this may download the GNOME runtime the first time)…"
  flatpak install --user -y --noninteractive "$TMP/morgen-todo.flatpak"
  say "Done! Open «Morning Routine» from the app menu – the cat is waiting."
  exit 0
fi
if [ -r /etc/os-release ]; then
  . /etc/os-release
  if [ "${ID:-}" = "ubuntu" ] && [ "$(printf '%s\n' "${VERSION_ID:-0}" 24.04 | sort -V | head -1)" != "24.04" ]; then
    fail "Ubuntu ${VERSION_ID:-?} is too old – Morning Routine needs Ubuntu 24.04 or newer."
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 755 "$TMP"  # apt reads the file as its own user

say "Downloading Morning Routine…"
curl -fL --progress-bar -o "$TMP/morgen-todo_all.deb" "$URL" || fail "Download failed: $URL"
chmod 644 "$TMP/morgen-todo_all.deb"

say "Installing (you may be asked for your password)…"
sudo apt-get install -y "$TMP/morgen-todo_all.deb"

say "Done! Open «Morning Routine» from the app menu – the cat is waiting."
