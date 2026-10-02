#!/usr/bin/env bash
# Installs SKTUI into an isolated venv and links `sktui` into ~/.local/bin.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/sktui/venv"
BIN="$HOME/.local/bin"

command -v python >/dev/null || { echo "python not found: sudo pacman -S python"; exit 1; }

python -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install "$HERE"

mkdir -p "$BIN"
ln -sf "$VENV/bin/sktui" "$BIN/sktui"

echo
echo "Installed. Run:  sktui --paper   (dry-run)   |   sktui   (live)"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Add to PATH:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;; esac
