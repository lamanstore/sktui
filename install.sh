#!/usr/bin/env bash
# ==============================================================================
# SKTUI — Professional Terminal Trading Workstation Installer
# Installs SKTUI into an isolated venv and symlinks `sktui` to ~/.local/bin
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/sktui/venv"
BIN="$HOME/.local/bin"

# 1. Detect Python 3.10+
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        ver="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
        major="$(echo "$ver" | cut -d. -f1)"
        minor="$(echo "$ver" | cut -d. -f2)"
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "✗ Error: Python 3.10 or higher is required to run SKTUI."
    echo "  Please install Python 3.10+ using your package manager:"
    echo "    - Debian/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "    - Arch Linux:     sudo pacman -S python python-pip"
    echo "    - Fedora:         sudo dnf install -y python3 python3-pip"
    echo "    - macOS:          brew install python3"
    exit 1
fi

echo "✓ Using Python: $("$PYTHON_BIN" --version) ($PYTHON_BIN)"

# 2. Check for venv module
if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
    echo "✗ Error: Python 'venv' module is missing."
    echo "  On Ubuntu/Debian, install it with: sudo apt install python3-venv"
    exit 1
fi

# 3. Create or update virtual environment
echo "⚙ Setting up isolated virtual environment in: $VENV"
mkdir -p "$(dirname "$VENV")"
"$PYTHON_BIN" -m venv "$VENV"

# 4. Install dependencies in editable mode
echo "⚙ Installing SKTUI dependencies in editable mode..."
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install -e "$HERE"

# 5. Link executable into ~/.local/bin
mkdir -p "$BIN"
ln -sf "$VENV/bin/sktui" "$BIN/sktui"

echo
echo "=============================================================================="
echo "✓ SKTUI Workstation installed successfully!"
echo "=============================================================================="
echo "Run SKTUI:"
echo "  sktui --paper        # Launch in Paper Trading / Dry-Run Mode"
echo "  sktui                # Launch Live Trading Mode"
echo "  sktui --profile live # Launch with specific environment profile"
echo

case ":$PATH:" in
    *":$BIN:"*)
        ;;
    *)
        echo "⚠ Notice: '$BIN' is not in your current PATH."
        echo "  Add it to your shell configuration (~/.bashrc or ~/.zshrc):"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo
        ;;
esac
