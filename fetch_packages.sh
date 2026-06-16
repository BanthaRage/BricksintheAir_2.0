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

APT_PACKAGES="python3-tk python3-lgpio"

# ---------------------------------------------------------------------------
# 1. apt packages — download directly into packages/apt/
# ---------------------------------------------------------------------------

info "Updating package lists..."
sudo apt-get update -qq

info "Resolving full dependency list for: $APT_PACKAGES"

# Get the complete recursive dependency list (excluding virtual packages)
PKGLIST=$(apt-cache depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances \
    $APT_PACKAGES 2>/dev/null \
    | grep "^[a-zA-Z0-9]" \
    | sort -u)

info "Downloading .deb files to packages/apt/ ..."

# apt-get download fetches directly to the current directory — no apt cache involved
cd "$PKG_APT"
FETCHED=0
SKIPPED=0
for pkg in $PKGLIST; do
    if apt-get download "$pkg" 2>/dev/null; then
        info "  $pkg"
        (( FETCHED++ )) || true
    else
        # Virtual packages and already-downloaded duplicates land here — not an error
        (( SKIPPED++ )) || true
    fi
done
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 2. pip packages
# ---------------------------------------------------------------------------

info "Downloading pip packages to packages/pip/ ..."
python3 -m pip download lgpio -d "$PKG_PIP" --quiet
info "  lgpio"

# ---------------------------------------------------------------------------
# 3. Summary
# ---------------------------------------------------------------------------

APT_COUNT=$(ls "$PKG_APT"/*.deb 2>/dev/null | wc -l)
PIP_COUNT=$(ls "$PKG_PIP"/ 2>/dev/null | wc -l)

echo ""
info "Done. Package bundle ready:"
echo "  packages/apt/  — $APT_COUNT .deb file(s)  ($SKIPPED virtual/skipped)"
echo "  packages/pip/  — $PIP_COUNT pip file(s)"
echo ""
info "Transfer the entire repo (including packages/) to the offline Pi, then run:"
echo "  ./setup.sh"
echo ""
