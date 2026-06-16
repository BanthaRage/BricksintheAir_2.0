#!/usr/bin/env bash
# BricksInTheAir — setup script (Raspberry Pi 5)
#
# If lgpio and tkinter are already installed, this script skips package
# installation entirely.  The packages/ bundle (from fetch_packages.sh)
# is only required when packages are missing.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_APT="$SCRIPT_DIR/packages/apt"
PKG_PIP="$SCRIPT_DIR/packages/pip"

# ---------------------------------------------------------------------------
# 1. Python version check (3.10+ required)
# ---------------------------------------------------------------------------

info "Checking Python version..."

PYTHON=$(command -v python3 || true)
[[ -z "$PYTHON" ]] && error "python3 not found. It should be pre-installed on Raspberry Pi OS."

PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 10) )); then
    error "Python 3.10+ required, found $PY_VER"
fi

info "Python $PY_VER — OK"

# ---------------------------------------------------------------------------
# 2. Check which packages are already installed
# ---------------------------------------------------------------------------

HAS_TKINTER=false
HAS_LGPIO=false

"$PYTHON" -c "import tkinter" 2>/dev/null && HAS_TKINTER=true || true
"$PYTHON" -c "import lgpio"   2>/dev/null && HAS_LGPIO=true   || true

if $HAS_TKINTER && $HAS_LGPIO; then
    info "All packages already installed — skipping package installation."
else
    # -----------------------------------------------------------------------
    # 3a. Install missing packages from bundle (offline)
    # -----------------------------------------------------------------------

    NEED_APT=false
    NEED_PIP=false
    $HAS_TKINTER || NEED_APT=true
    $HAS_LGPIO   || { NEED_APT=true; NEED_PIP=true; }

    if $NEED_APT; then
        if [[ ! -d "$PKG_APT" ]] || [[ -z "$(ls "$PKG_APT"/*.deb 2>/dev/null)" ]]; then
            error "packages/apt/ is missing or empty and packages need installing.\nRun fetch_packages.sh on a Pi with internet first, then transfer the repo."
        fi

        info "Installing apt packages from packages/apt/ ..."
        sudo dpkg -i "$PKG_APT"/*.deb 2>&1 | grep -v "^(Reading\|Selecting\|Preparing\|Unpacking\|Setting)" || true

        if ! sudo apt-get install -f --no-download -y -qq 2>/dev/null; then
            warn "apt-get -f reported issues — trying dpkg with relaxed dependency checks..."
            sudo dpkg -i --force-depends "$PKG_APT"/*.deb
        fi
    fi

    if $NEED_PIP; then
        if [[ ! -d "$PKG_PIP" ]] || [[ -z "$(ls "$PKG_PIP"/ 2>/dev/null)" ]]; then
            error "packages/pip/ is missing or empty and lgpio needs installing.\nRun fetch_packages.sh on a Pi with internet first, then transfer the repo."
        fi

        info "Installing pip packages from packages/pip/ ..."
        "$PYTHON" -m pip install \
            --no-index \
            --find-links="$PKG_PIP" \
            --break-system-packages \
            --quiet \
            lgpio
    fi
fi

# ---------------------------------------------------------------------------
# 4. GPIO group permissions
# ---------------------------------------------------------------------------

CURRENT_USER="${SUDO_USER:-$USER}"

if groups "$CURRENT_USER" | grep -qw gpio; then
    info "User '$CURRENT_USER' is already in the gpio group."
else
    info "Adding '$CURRENT_USER' to the gpio group..."
    sudo usermod -aG gpio "$CURRENT_USER"
    warn "Log out and back in for the group change to take effect."
fi

# ---------------------------------------------------------------------------
# 5. Verify imports
# ---------------------------------------------------------------------------

info "Verifying Python imports..."

"$PYTHON" -c "import tkinter" 2>/dev/null \
    && info "  tkinter — OK" \
    || warn "  tkinter — NOT FOUND (GUI will not work)"

"$PYTHON" -c "import lgpio" 2>/dev/null \
    && info "  lgpio   — OK" \
    || warn "  lgpio   — NOT FOUND (GPIO will run in mock mode)"

# ---------------------------------------------------------------------------
# 6. Done
# ---------------------------------------------------------------------------

echo ""
info "Setup complete. To run BricksInTheAir:"
echo ""
echo "  Simulation only (no GPIO):"
echo "    python3 BitA_Simulation/main.py          # terminal REPL"
echo "    python3 BitA_Simulation/gui.py           # tkinter GUI"
echo ""
echo "  Raspberry Pi 5 with live GPIO:"
echo "    sudo python3 BitA_Simulation/opi_main.py          # terminal REPL"
echo "    sudo python3 BitA_Simulation/opi_main.py --gui    # tkinter GUI"
echo ""
echo "  GPIO pin map (BCM numbering):"
echo "    GPIO12 (Board 32) — Propeller speed"
echo "    GPIO13 (Board 33) — AFSS pump"
echo "    GPIO16 (Board 36) — Gear UP  (DRV8833 IN1)"
echo "    GPIO20 (Board 38) — Gear DOWN (DRV8833 IN2)"
echo "    GPIO21 (Board 40) — AFSS coil"
echo ""
