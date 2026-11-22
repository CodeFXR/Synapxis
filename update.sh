#!/usr/bin/env bash
#
# Synapxis update script.
#
# Re-runs the installer against the current SYNAPXIS_PACKAGE_SOURCE so an
# existing install picks up the latest version. Re-uses the install root
# (SYNAPXIS_HOME or ~/.synapxis) and respects the same opt-in shell-config
# behaviour as install.sh.
#
# Usage:
#   bash update.sh                       # upgrade from default source (PyPI)
#   SYNAPXIS_PACKAGE_SOURCE=./local bash update.sh
#   SYNAPXIS_HOME=/opt/snxa bash update.sh
#
# This script is intentionally not a curl-piped-into-bash story. It is
# safe to inspect; the same hardening as install.sh applies
# (`set -euo pipefail`, root refusal, Python >= 3.10 check, terminal
# fallback, opt-in shell alias).

set -euo pipefail

if ! infocmp "${TERM:-}" >/dev/null 2>&1; then
    export TERM=xterm-256color
fi

ORANGE='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

log_info() {
    echo -e "${BOLD}::${NC} $*"
}

# --- 0. Refuse to run as root ---
if [ "$(id -u)" -eq 0 ]; then
    echo -e "${ORANGE}${BOLD}Error:${NC} Refusing to run as root. Run update.sh as the user who owns the install." >&2
    exit 1
fi

# --- 1. Locate Python 3.10+ ---
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${ORANGE}${BOLD}Error:${NC} python3 is required." >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3)"
PY_MAJOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[0])')"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])')"
PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
if [ "$PY_MAJOR" -lt 3 ] \
    || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo -e "${ORANGE}${BOLD}Error:${NC} Python 3.10 or later is required (found $PY_VERSION)." >&2
    exit 1
fi

SYNAPXIS_HOME="${SYNAPXIS_HOME:-$HOME/.synapxis}"
SYNAPXIS_PACKAGE_SOURCE="${SYNAPXIS_PACKAGE_SOURCE:-synapxis==1.0.0}"

if [ ! -d "$SYNAPXIS_HOME/.venv" ]; then
    echo -e "${ORANGE}${BOLD}Error:${NC} No Synapxis installation found at $SYNAPXIS_HOME"
    echo "Run the installer first:"
    echo "  curl -fsSL https://snx.codefxr.com/install | bash"
    exit 1
fi

log_info "Updating Synapxis at $SYNAPXIS_HOME from $SYNAPXIS_PACKAGE_SOURCE ..."

# shellcheck disable=SC1091
source "$SYNAPXIS_HOME/.venv/bin/activate"
python -m pip install --upgrade "$SYNAPXIS_PACKAGE_SOURCE"

log_info "Update complete."
echo "Run 'synapxis --version' to confirm."
