#!/usr/bin/env bash
# BricksInTheAir — package fetcher
#
# Run this ONCE on a Raspberry Pi (or any arm64 Debian machine) that has
# internet access.  It downloads all required packages into packages/ so
# the repo can be transferred to an offline Pi and installed with setup.sh.
#
# Usage:
#   chmod +x fetch_packages.sh && ./fetch_packages.sh
#   Then copy the whole repo (including packages/) to the offline Pi.

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

mkdir -p "$PKG_APT" "$PKG_PIP"

# ---------------------------------------------------------------------------
# 1. apt packages + all recursive dependencies
# ---------------------------------------------------------------------------

APT_PACKAGES="python3-tk python3-lgpio"

info "Updating package lists..."
sudo apt-get update -qq

info "Resolving and downloading apt packages (including all dependencies)..."

# Use a timestamp marker so we only copy what apt actually fetches
touch /tmp/bita_fetch_marker

# --download-only puts .deb files in /var/cache/apt/archives/
# --reinstall forces a re-download even if already installed on this machine
sudo apt-get install --download-only --reinstall -y $APT_PACKAGES

# Copy everything apt pulled since the marker
FETCHED=0
while IFS= read -r deb; do
    cp "$deb" "$PKG_APT/"
    info "  Fetched: $(basename "$deb")"
    (( FETCHED++ )) || true
done < <(find /var/cache/apt/archives -name "*.deb" -newer /tmp/bita_fetch_marker)

rm -f /tmp/bita_fetch_marker

if (( FETCHED == 0 )); then
    warn "No new .deb files were downloaded — packages may already be cached."
    warn "If packages/apt/ is empty, run: sudo apt-get clean  then re-run this script."
fi

# ---------------------------------------------------------------------------
# 2. pip packages (architecture-matched wheel)
# ---------------------------------------------------------------------------

info "Downloading pip packages..."
python3 -m pip download lgpio -d "$PKG_PIP" --quiet
info "  Fetched: $(ls "$PKG_PIP")"

# ---------------------------------------------------------------------------
# 3. Summary
# ---------------------------------------------------------------------------

APT_COUNT=$(ls "$PKG_APT"/*.deb 2>/dev/null | wc -l)
PIP_COUNT=$(ls "$PKG_PIP"/ 2>/dev/null | wc -l)

echo ""
info "Done. Package bundle ready:"
echo "  packages/apt/  — $APT_COUNT .deb file(s)"
echo "  packages/pip/  — $PIP_COUNT pip file(s)"
echo ""
info "Transfer the entire repo (including packages/) to the offline Pi, then run:"
echo "  ./setup.sh"
echo ""
