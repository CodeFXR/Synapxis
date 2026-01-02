#!/bin/bash
set -e

# --- Configuration ---
REPO_URL="https://github.com/CodeFXR/Synapxis.git"
INSTALL_DIR="$HOME/.synapxis"
ENTRY_POINT="main.py"

# --- Visual Styling ---
ORANGE='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_NAME=Linux;;
    Darwin*)    OS_NAME=Mac;;
    *)          OS_NAME="UNKNOWN:${OS}"
esac

# --- Header ---
clear
echo -e "${ORANGE}${BOLD}"
echo "███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ██╗  ██╗██╗███████╗"
echo "██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗╚██╗██╔╝██║██╔════╝"
echo "███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝ ╚███╔╝ ██║███████╗"
echo "╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝  ██╔██╗ ██║╚════██║"
echo "███████║   ██║   ██║ ╚████║██║  ██║██║     ██╔╝ ██╗██║███████║"
echo "╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝"
echo -e "${NC}"
echo -e ":: Detected System: $OS_NAME"

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while kill -0 "$pid" 2>/dev/null; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# --- 1. Check Prerequisites ---
echo -e "${BOLD}:: Checking System...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "   [!] Error: Git is not installed."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "   [!] Error: Python 3 is not installed."
    exit 1
fi

echo -e "   [OK] System tools ready."
echo ""

# --- 2. Download ---
echo -e "${BOLD}:: Downloading Synapxis...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi

echo -n "   [>] Cloning repository..."
git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1 &
spinner $!
echo -e " Done"

cd "$INSTALL_DIR"

# --- 3. Setup Virtual Env ---
echo ""
echo -e "${BOLD}:: Setting up Sandbox...${NC}"

echo -n "   [>] Creating virtual environment..."
python3 -m venv .venv &
spinner $!
echo -e " Done"

source .venv/bin/activate

echo -n "   [>] Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
# Install all required libraries
pip install textual networkx scipy numpy textual-image maturin aiosqlite > /dev/null 2>&1 &
spinner $!
echo -e " Done"
echo ""

# --- 4. Rust Compilation (Optional) ---
echo -e "${BOLD}:: Graphics Engine Setup...${NC}"
set +e

if command -v cargo &> /dev/null; then
    echo -n "   [>] Rust detected. Compiling HD Engine..."
    if [ -d "synapxis_rs" ]; then
        cd synapxis_rs
        if maturin develop --release > ../build.log 2>&1; then
            echo -e " Success"
            cargo clean > /dev/null 2>&1
        else
            echo -e " Failed (Using Standard Mode)"
        fi
        cd ..
    else
        echo -e " Skipped"
    fi
else
    echo -e "   [!] Rust not found. Using Standard Mode."
fi
set -e
echo ""

# --- 5. Shell Shortcuts ---
echo -e "${BOLD}:: Finalizing...${NC}"

SHELL_CONFIG=""
case "$SHELL" in
  */zsh)  SHELL_CONFIG="$HOME/.zshrc" ;;
  */bash)
    if [ -f "$HOME/.bash_profile" ]; then SHELL_CONFIG="$HOME/.bash_profile"; else SHELL_CONFIG="$HOME/.bashrc"; fi
    ;;
  */fish) SHELL_CONFIG="$HOME/.config/fish/config.fish" ;;
  *)      SHELL_CONFIG="$HOME/.profile" ;;
esac

if [ -f "$SHELL_CONFIG" ]; then
    # Clean old aliases
    if [[ "$SHELL" != *"fish"* ]]; then
        grep -v "alias synapxis=" "$SHELL_CONFIG" | grep -v "alias snx=" > "${SHELL_CONFIG}.tmp"
        mv "${SHELL_CONFIG}.tmp" "$SHELL_CONFIG"

        # Add new aliases
        echo "" >> "$SHELL_CONFIG"
        echo "# Synapxis App" >> "$SHELL_CONFIG"
        echo "alias synapxis=\"$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/$ENTRY_POINT\"" >> "$SHELL_CONFIG"
        echo "alias snx=\"$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/$ENTRY_POINT\"" >> "$SHELL_CONFIG"
        echo -e "   [OK] Aliases added to ${ORANGE}$SHELL_CONFIG${NC}"
    else
        echo -e "   [!] Fish shell detected. Please add alias manually."
    fi
else
    echo -e "   [!] Shell config not found. Add alias manually."
fi

# --- 6. Done ---
echo ""
echo -e "${ORANGE}===================================================${NC}"
echo -e "${BOLD}         INSTALLATION COMPLETE${NC}"
echo -e "${ORANGE}===================================================${NC}"
echo ""
echo -e "1. Restart terminal OR run: ${BOLD}source $SHELL_CONFIG${NC}"
echo -e "2. Launch with: ${BOLD}${ORANGE}snx${NC}"
echo ""
