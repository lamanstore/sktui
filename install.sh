#!/usr/bin/env bash
# ==============================================================================
# SKTUI — Professional Terminal Trading Workstation Installer
# Installs SKTUI into an isolated venv and links `sktui` to ~/.local/bin
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/sktui/venv"
BIN="$HOME/.local/bin"

# Styling tokens
BOLD="\033[1m"
GREEN="\033[38;2;0;229;255m"
SUCCESS="\033[38;2;0;255;135m"
AMBER="\033[38;2;245;158;11m"
RED="\033[38;2;255;71;87m"
RESET="\033[0m"

INSTALL_DEV=false
DO_UNINSTALL=false

# Argument parsing
for arg in "$@"; do
    case "$arg" in
        --dev)
            INSTALL_DEV=true
            ;;
        --uninstall)
            DO_UNINSTALL=true
            ;;
        --help|-h)
            echo -e "${BOLD}SKTUI Workstation Installer${RESET}"
            echo
            echo "Usage: ./install.sh [OPTIONS]"
            echo
            echo "Options:"
            echo "  --dev         Install development & test dependencies (pytest, ruff, mypy)"
            echo "  --uninstall   Remove SKTUI venv and binary symlink"
            echo "  --help, -h    Show this help message"
            echo
            exit 0
            ;;
        *)
            echo -e "${RED}✗ Unknown option: $arg${RESET}"
            echo "Run ./install.sh --help for available options."
            exit 1
            ;;
    esac
done

# Handle uninstall
if [ "$DO_UNINSTALL" = true ]; then
    echo -e "${BOLD}Removing SKTUI Workstation...${RESET}"
    if [ -L "$BIN/sktui" ] || [ -f "$BIN/sktui" ]; then
        rm -f "$BIN/sktui"
        echo -e "${SUCCESS}✓ Removed $BIN/sktui${RESET}"
    fi
    if [ -d "$VENV" ]; then
        rm -rf "$VENV"
        echo -e "${SUCCESS}✓ Removed $VENV${RESET}"
    fi
    echo -e "${GREEN}SKTUI has been completely uninstalled.${RESET}"
    echo "Note: Configuration files in ~/.config/sktui and audit logs in ~/.local/share/sktui were preserved."
    exit 0
fi

echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
echo -e "${BOLD}${GREEN}⚡ SKTUI — Professional Terminal Trading Workstation Installer${RESET}"
echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
echo

# 1. Detect Python 3.10+
PYTHON_BIN=""
for candidate in python3 python python3.14 python3.13 python3.12 python3.11 python3.10; do
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
    echo -e "${RED}✗ Error: Python 3.10 or higher is required to run SKTUI.${RESET}"
    echo "  Please install Python 3.10+ using your system package manager:"
    echo "    - Debian/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "    - Arch Linux:     sudo pacman -S python python-pip"
    echo "    - Fedora:         sudo dnf install -y python3 python3-pip"
    echo "    - macOS:          brew install python3"
    exit 1
fi

echo -e "${SUCCESS}✓ Found Python:${RESET} $("$PYTHON_BIN" --version) ($PYTHON_BIN)"

# 2. Check for venv module
if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
    echo -e "${RED}✗ Error: Python 'venv' module is missing.${RESET}"
    echo "  On Ubuntu/Debian, install it with: sudo apt install -y python3-venv"
    exit 1
fi

# 3. Create or update virtual environment
echo -e "${GREEN}⚙ Creating isolated virtual environment in:${RESET} $VENV"
mkdir -p "$(dirname "$VENV")"
"$PYTHON_BIN" -m venv "$VENV"

# 4. Install dependencies in editable mode
echo -e "${GREEN}⚙ Upgrading pip, setuptools, wheel...${RESET}"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true

if [ "$INSTALL_DEV" = true ]; then
    echo -e "${GREEN}⚙ Installing SKTUI with [dev] test dependencies in editable mode...${RESET}"
    "$VENV/bin/python" -m pip install -e "${HERE}[dev]"
else
    echo -e "${GREEN}⚙ Installing SKTUI in editable mode...${RESET}"
    "$VENV/bin/python" -m pip install -e "$HERE"
fi

# 5. Link executable into ~/.local/bin
mkdir -p "$BIN"
ln -sf "$VENV/bin/sktui" "$BIN/sktui"
chmod +x "$BIN/sktui"

# 6. Verify installation
echo -e "${GREEN}⚙ Verifying installation...${RESET}"
if "$BIN/sktui" --help >/dev/null 2>&1; then
    echo -e "${SUCCESS}✓ SKTUI binary verified successfully!${RESET}"
else
    echo -e "${AMBER}⚠ Note: sktui command check returned an error. Ensure ~/.local/bin is on your PATH.${RESET}"
fi

echo
echo -e "${BOLD}${SUCCESS}==============================================================================${RESET}"
echo -e "${BOLD}${SUCCESS}✓ SKTUI Workstation installed successfully!${RESET}"
echo -e "${BOLD}${SUCCESS}==============================================================================${RESET}"
echo
echo "Launch SKTUI:"
echo "  sktui --paper        # Launch Paper Trading / Dry-Run Workstation"
echo "  sktui                # Launch Live Trading Workstation"
echo "  sktui --profile live # Launch with specific environment profile"
echo
if [ "$INSTALL_DEV" = true ]; then
    echo "Run Test Suite:"
    echo "  $VENV/bin/pytest"
    echo
fi

case ":$PATH:" in
    *":$BIN:"*)
        ;;
    *)
        echo -e "${AMBER}⚠ Notice: '$BIN' is not in your current shell PATH.${RESET}"
        echo "  Add it to your ~/.bashrc or ~/.zshrc:"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo
        ;;
esac
