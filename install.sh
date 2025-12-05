#!/bin/bash

# ==============================================================================
# SYNAPXIS INSTALLER
# ==============================================================================
# This script installs Synapxis into a hidden directory in the user's home folder.
# It creates an isolated Python virtual environment to avoid affecting the
# system-wide Python installation.
# ==============================================================================

# --- Configuration ---
# The GitHub repository to clone from
REPO_URL="https://github.com/CodeFXR/Synapxis.git"
# The hidden directory where the app will live (The "Sandbox")
INSTALL_DIR="$HOME/.synapxis"

# --- Visual Styling (Orange Theme) ---
ORANGE='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color (Reset)

# Header Display
clear
echo -e "${ORANGE}${BOLD}"
echo "███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ██╗  ██╗██╗███████╗"
echo "██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗╚██╗██╔╝██║██╔════╝"
echo "███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝ ╚███╔╝ ██║███████╗"
echo "╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝  ██╔██╗ ██║╚════██║"
echo "███████║   ██║   ██║ ╚████║██║  ██║██║     ██╔╝ ██╗██║███████║"
echo "╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝"
echo -e "${NC}"

# Simple spinner animation for long processes
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# ------------------------------------------------------------------------------
# STEP 1: Pre-flight Checks
# We check if the user has the basic tools required to build the engine.
# ------------------------------------------------------------------------------
echo -e "${BOLD}:: Checking Prerequisites...${NC}"

# Check for Git (to download the code)
if ! command -v git &> /dev/null; then
    echo -e "   [!] Error: Git is not installed."
    echo "       Please install git and try again."
    exit 1
fi

# Check for Python 3 (The main engine)
if ! command -v python3 &> /dev/null; then
    echo -e "   [!] Error: Python 3 is not installed."
    echo "       Please install python3 and try again."
    exit 1
fi

echo -e "   [OK] System tools ready."
echo ""

# ------------------------------------------------------------------------------
# STEP 2: Download
# We download the source code into a hidden folder (~/.synapxis).
# ------------------------------------------------------------------------------
echo -e "${BOLD}:: Downloading Synapxis...${NC}"

# If a previous installation exists, remove it to ensure a clean update
if [ -d "$INSTALL_DIR" ]; then
    echo -e "   [>] Removing previous installation..."
    rm -rf "$INSTALL_DIR"
fi

# Clone the repository (depth 1 means we only get the latest version, saves time)
echo -n "   [>] Cloning repository to $INSTALL_DIR..."
git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR" &
spinner $!
echo -e " Done"

# Move into the installation directory for the rest of the script
cd "$INSTALL_DIR" || exit

# ------------------------------------------------------------------------------
# STEP 3: Environment Setup (The Sandbox)
# We create a Python Virtual Environment (.venv).
# This allows us to install libraries without asking for 'sudo' or breaking OS tools.
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}:: Setting up Virtual Environment...${NC}"

echo -n "   [>] Creating isolated Python sandbox..."
python3 -m venv .venv &
spinner $!
echo -e " Done"

# Activate the sandbox so subsequent commands use the local pip
source .venv/bin/activate

echo -n "   [>] Installing Python dependencies..."
# We explicitly install the required libraries here.
# This ensures the app works immediately even if requirements.txt is missing.
if pip install --upgrade pip > /dev/null 2>&1 && \
   pip install textual networkx scipy numpy textual-image maturin > /dev/null 2>&1; then
    echo -e " Done"
else
    echo -e "\n   [!] Error: Failed to install Python dependencies."
    exit 1
fi

echo ""

# ------------------------------------------------------------------------------
# STEP 4: Graphics Engine Build (Rust)
# We check if the user has Rust installed. If yes, we compile the HD engine.
# If no, the app will automatically use the Python fallback we wrote earlier.
# ------------------------------------------------------------------------------
echo -e "${BOLD}:: Graphics Engine Setup...${NC}"

if command -v cargo &> /dev/null; then
    echo -n "   [>] Rust detected. Compiling HD Braille Engine..."
    cd synapxis_rs

    # maturin builds the Rust code and installs it into our .venv python
    if maturin develop --release > ../build.log 2>&1; then
        echo -e " Success (HD Mode Active)"

        # Cleanup: Rust builds create a massive 'target' folder (100MB+).
        # We delete it now because we only need the final compiled binary.
        echo -n "   [>] Cleaning up build artifacts..."
        cargo clean > /dev/null 2>&1
        echo -e " Done"
    else
        echo -e " Failed"
        echo -e "       (App will run in Standard Mode. See build.log for details)"
    fi
    cd ..
else
    echo -e "   [!] Rust/Cargo not found."
    echo -e "       Synapxis will run in ${ORANGE}Standard Mode${NC} (Python Fallback)."
    echo "       (To enable HD graphics, install Rust and run this installer again)"
fi

echo ""

# ------------------------------------------------------------------------------
# STEP 5: Shell Integration
# We add an 'alias' to the user's shell config file.
# This allows them to type 'synapxis' from anywhere to run the app.
# ------------------------------------------------------------------------------
echo -e "${BOLD}:: Finalizing...${NC}"

SHELL_CONFIG=""
# Detect which shell the user is using (ZSH vs BASH)
if [ "$SHELL" == "*/zsh" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
elif [ "$SHELL" == "*/bash" ] || [ -f "$HOME/.bashrc" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
fi

if [ ! -z "$SHELL_CONFIG" ]; then
    # Remove old aliases if they exist to prevent duplicates
    # We use a temp file strategy for compatibility
    grep -v "alias synapxis=" "$SHELL_CONFIG" > "${SHELL_CONFIG}.tmp" && mv "${SHELL_CONFIG}.tmp" "$SHELL_CONFIG"
    grep -v "alias snx=" "$SHELL_CONFIG" > "${SHELL_CONFIG}.tmp" && mv "${SHELL_CONFIG}.tmp" "$SHELL_CONFIG"

    echo "" >> "$SHELL_CONFIG"
    echo "# Synapxis App" >> "$SHELL_CONFIG"
    # This is the direct invocation command. It calls the python binary INSIDE the hidden folder.
    echo "alias synapxis=\"$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/synapxis.py\"" >> "$SHELL_CONFIG"
    echo "alias snx=\"$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/synapxis.py\"" >> "$SHELL_CONFIG"

    echo -e "   [OK] Aliases 'synapxis' and 'snx' added to ${ORANGE}$SHELL_CONFIG${NC}"
else
    echo -e "   [!] Could not automatically detect shell config."
    echo "       You can add the alias manually:"
    echo "       alias snx=\"$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/synapxis.py\""
fi

# ------------------------------------------------------------------------------
# STEP 6: Completion
# ------------------------------------------------------------------------------
echo ""
echo -e "${ORANGE}===================================================${NC}"
echo -e "${BOLD}         INSTALLATION COMPLETE${NC}"
echo -e "${ORANGE}===================================================${NC}"
echo ""
echo -e "1. Restart your terminal (or run: source $SHELL_CONFIG)"
echo -e "2. Type ${BOLD}${ORANGE}synapxis${NC} or ${BOLD}${ORANGE}snx${NC} to launch."
echo ""
