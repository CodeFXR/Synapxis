#!/bin/bash
#
# Synapxis installer.
#
# Usage:
#   bash install.sh                     # install into ~/.synapxis
#   SYNAPXIS_HOME=/opt/snxa bash install.sh
#   SYNAPXIS_INSTALL_NO_ALIASES=1 bash install.sh   # do not touch shell config
#
# This script is intentionally not a curl-piped-into-bash story. It is
# safe to inspect; it surfaces every destructive change before making
# it; every long-running command is `wait`-ed so failure propagates;
# every path is quoted; shell configuration is backed up and diffed
# before modification.
#
# Phase 5 hardening:
#   * Refuses to run as root.
#   * Validates Python >= 3.10.
#   * Quotes every expansion.
#   * Uses `wait` for background jobs and propagates exit codes.
#   * Backs up shell config, prints the proposed diff, and lets the
#     user skip or accept it.
#   * Aliases are opt-in via SYNAPXIS_INSTALL_NO_ALIASES=0.
#   * Does not self-update.

set -euo pipefail

ORANGE='\033[0;33m'
BOLD='\033[1m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BOLD}::${NC} $*"
}

log_warn() {
    echo -e "${ORANGE}${BOLD}::${NC} $*"
}

log_err() {
    echo -e "${RED}${BOLD}Error:${NC} $*" >&2
}

# `run` pipes a command through `& spinner $!` only when stdout is a
# TTY. In CI / non-interactive shells (our installer tests included),
# we just `wait` and capture exit codes. The optional spinner is a
# visual nicety that never affects the result.
run_with_progress() {
    local label="$1"
    shift
    if [ -t 1 ]; then
        printf '%s' "$label"
        "$@" >/dev/null 2>&1 &
        local pid=$!
        local spinstr='|/-\'
        while kill -0 "$pid" 2>/dev/null; do
            printf ' [%c]  ' "${spinstr}"
            spinstr="${spinstr#?}${spinstr%%${spinstr#?}}"
            sleep 0.1
            printf '\b\b\b\b\b\b'
        done
        if wait "$pid"; then
            printf '    \b\b\b\b'
            printf '%s\n' " Done"
            return 0
        else
            printf '    \b\b\b\b'
            local rc=$?
            log_err "$label failed (exit $rc)"
            return $rc
        fi
    else
        if "$@"; then
            printf '%s Done\n' "$label"
            return 0
        else
            local rc=$?
            log_err "$label failed (exit $rc)"
            return $rc
        fi
    fi
}

SYNAPXIS_HOME="${SYNAPXIS_HOME:-$HOME/.synapxis}"
SYNAPXIS_PACKAGE_SOURCE="${SYNAPXIS_PACKAGE_SOURCE:-synapxis==1.0.0}"
SYNAPXIS_INSTALL_NO_ALIASES="${SYNAPXIS_INSTALL_NO_ALIASES:-1}"
SYNAPXIS_SKIP_BACKUP_PROMPT="${SYNAPXIS_SKIP_BACKUP_PROMPT:-0}"

# --- 0. Refuse to run as root ---
if [ "$(id -u)" -eq 0 ]; then
    log_err "Refusing to run as root. Run install.sh as the user who will own the install."
    exit 1
fi

# --- 1. Locate Python 3.10+ ---
if ! command -v python3 >/dev/null 2>&1; then
    log_err "python3 is required." >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3)"
PY_MAJOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[0])')"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])')"
PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
if [ "$PY_MAJOR" -lt 3 ] \
    || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    log_err "Python 3.10 or later is required (found $PY_VERSION)."
    exit 1
fi

OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_NAME=Linux;;
    Darwin*)    OS_NAME=Mac;;
    *)          OS_NAME="UNKNOWN:${OS}";;
esac

if ! infocmp "${TERM:-}" >/dev/null 2>&1; then
    export TERM=xterm-256color
fi

if [ -t 1 ]; then
    clear
fi
echo -e "${ORANGE}${BOLD}"
echo "███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ██╗  ██╗██╗███████╗"
echo "██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗╚██╗██╔╝██║██╔════╝"
echo "███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝ ╚███╔╝ ██║███████╗"
echo "╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝  ██╔██╗ ██║╚════██║"
echo "███████║   ██║   ██║ ╚████║██║  ██║██║     ██╔╝ ██╗██║███████║"
echo "╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝"
echo -e "${NC}"
echo -e ":: Detected System: $OS_NAME  :: Python $PY_VERSION"
echo ""

log_info "Install location: $SYNAPXIS_HOME"
log_info "Disable alias step with: SYNAPXIS_INSTALL_NO_ALIASES=1"
echo ""

# --- 2. Prepare the install directory ---
log_info "Creating install directory..."
mkdir -p "$SYNAPXIS_HOME"

# --- 3. Create the venv (if missing) ---
if [ ! -d "$SYNAPXIS_HOME/.venv" ]; then
    log_info "Setting up sandbox (.venv)..."
    if ! "$PYTHON_BIN" -m venv "$SYNAPXIS_HOME/.venv"; then
        log_err "venv creation failed."
        exit 1
    fi
fi

# shellcheck disable=SC1091
source "$SYNAPXIS_HOME/.venv/bin/activate"

log_info "Upgrading pip and wheel..."
run_with_progress "    [>] " python -m pip install --upgrade pip wheel

# --- 4. Install Synapxis ---
log_info "Installing synapxis..."
run_with_progress "    [>] " python -m pip install "$SYNAPXIS_PACKAGE_SOURCE"

# --- 5. Verify the install ---
log_info "Verifying install..."
if ! run_with_progress "    [>] " python -c "import synapxis"; then
    log_err "synapxis did not import."
    exit 1
fi

log_info "Looking for the synapxis console script..."
SYNAPXIS_BIN="$SYNAPXIS_HOME/.venv/bin/synapxis"
if [ -x "$SYNAPXIS_BIN" ]; then
    echo -e "    [OK] ${SYNAPXIS_BIN#$HOME/}"
else
    echo -e "    ${ORANGE}!!${NC} synapxis binary not on PATH in $SYNAPXIS_HOME/.venv/bin."
fi

if ! "$SYNAPXIS_BIN" --version >/dev/null 2>&1; then
    log_err "synapxis --version exited non-zero."
    exit 1
fi

# --- 7. Optional shell alias (with backup + diff) ---
configure_shell_alias() {
    if [ "$SYNAPXIS_INSTALL_NO_ALIASES" = "1" ]; then
        echo -e "    ${ORANGE}Skipping alias step (SYNAPXIS_INSTALL_NO_ALIASES=1).${NC}"
        return 0
    fi

    case "$SHELL" in
      */zsh)  SHELL_CONFIG="$HOME/.zshrc" ;;
      */bash)
        if [ -f "$HOME/.bash_profile" ]; then SHELL_CONFIG="$HOME/.bash_profile"; else SHELL_CONFIG="$HOME/.bashrc"; fi
        ;;
      */fish) SHELL_CONFIG="$HOME/.config/fish/config.fish" ;;
      *)      SHELL_CONFIG="$HOME/.profile" ;;
    esac

    if [ -z "${SHELL_CONFIG:-}" ] || [ ! -f "$SHELL_CONFIG" ]; then
        echo -e "    ${ORANGE}Skipping alias step: no $SHELL shell config at ${SHELL_CONFIG:-unknown}.${NC}"
        return 0
    fi

    ALIAS_LINE="alias snx='$SYNAPXIS_HOME/.venv/bin/synapxis'"
    ALIAS_BLOCK="\\n# Synapxis (added $(date -u +%Y-%m-%dT%H:%M:%SZ))\\n$ALIAS_LINE"

    if grep -F "$ALIAS_LINE" "$SHELL_CONFIG" >/dev/null 2>&1; then
        echo -e "    [OK] snx alias already present in ${SHELL_CONFIG#$HOME/}."
        return 0
    fi

    echo ""
    log_warn "About to edit: $SHELL_CONFIG"
    BACKUP="${SHELL_CONFIG}.synapxis.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "$SHELL_CONFIG" "$BACKUP"
    echo -e "    [OK] Backed up to ${BACKUP#$HOME/}"

    TMP_NEW="$(mktemp)"
    {
        cat "$SHELL_CONFIG"
        printf '\\n# Synapxis (added %s)\\n%s\\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ALIAS_LINE"
    } > "$TMP_NEW"

    if command -v diff >/dev/null 2>&1; then
        echo -e "    Proposed diff:"
        diff -u "$SHELL_CONFIG" "$TMP_NEW" | sed 's/^/    /' || true
    fi

    if [ "$SYNAPXIS_SKIP_BACKUP_PROMPT" = "1" ] || [ ! -t 0 ]; then
        echo "    Applying change (non-interactive)."
    else
        printf '    Apply? [y/N] '
        read -r answer
        case "$answer" in
            y|Y|yes|YES) echo "    Applying change." ;;
            *) echo "    Skipped."; rm -f "$TMP_NEW"; return 0 ;;
        esac
    fi

    mv "$TMP_NEW" "$SHELL_CONFIG"
    echo -e "    [OK] Updated ${SHELL_CONFIG#$HOME/}"
}

configure_shell_alias

# --- 8. Done ---
echo ""
echo -e "${ORANGE}===================================================${NC}"
echo -e "${BOLD}         SYNAPXIS IS READY${NC}"
echo -e "${ORANGE}===================================================${NC}"
echo -e "1. Activate: ${BOLD}source \"$SYNAPXIS_HOME/.venv/bin/activate\"${NC}"
echo -e "   (or add $SYNAPXIS_HOME/.venv/bin to your PATH)"
echo -e "2. Launch:   ${BOLD}${ORANGE}synapxis${NC}    (or the 'snx' alias, if installed)"
echo -e ""
echo -e "Rust renderer: bundled in the installed wheel"
echo -e ""
echo "Update:   python -m pip install --upgrade synapxis"
echo "Rollback: python -m pip install --force-reinstall 'synapxis==<ver>'"
echo "Verify:   synapxis verify"
