#!/usr/bin/env bash
# BricksInTheAir — system install script
#
# 1. Makes all Python scripts executable
# 2. Installs a 'bita' command to /usr/local/bin so you can launch
#    the program from anywhere in the terminal
#
# Usage:
#   chmod +x install.sh && ./install.sh
#
# After install:
#   bita          # terminal REPL with live GPIO
#   bita --gui    # tkinter GUI with live GPIO

set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$REPO_DIR/BitA_Simulation"

# ---------------------------------------------------------------------------
# 1. Make all Python scripts executable
# ---------------------------------------------------------------------------

info "Setting +x on Python scripts..."
chmod +x "$SIM_DIR"/*.py
for f in "$SIM_DIR"/*.py; do
    info "  $(basename "$f")"
done

# ---------------------------------------------------------------------------
# 2. Install the 'bita' launcher to /usr/local/bin
# ---------------------------------------------------------------------------

info "Installing 'bita' command to /usr/local/bin ..."

sudo tee /usr/local/bin/bita > /dev/null << EOF
#!/usr/bin/env bash
exec python3 "$SIM_DIR/opi_main.py" "\$@"
EOF

sudo chmod +x /usr/local/bin/bita

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
info "Done. Commands available from any terminal:"
echo ""
echo "  bita          — terminal REPL with live GPIO"
echo "  bita --gui    — tkinter GUI with live GPIO"
echo ""
