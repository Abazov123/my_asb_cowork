#!/bin/bash

# =============================================================================
# Agent Second Brain - Bootstrap Script
# =============================================================================
# Downloads setup.sh and runs it properly (not via pipe)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/agent-second-brain/main/bootstrap.sh | bash
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}Agent Second Brain - Bootstrap${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}[X] Do not run as root!${NC}"
    echo "    Create a user first: adduser myuser && usermod -aG sudo myuser"
    echo "    Then: su - myuser"
    exit 1
fi

# Detect which fork to download from
# If this script is run via pipe, ask for GitHub username
# If run from a cloned repo, use the repo's remote URL
if [ -f "setup.sh" ]; then
    # Already in repo, just run setup.sh directly
    exec bash setup.sh
fi

echo -e "${CYAN}Enter your GitHub username (where you forked the repo):${NC}"
read -r GITHUB_USER < /dev/tty

if [ -z "$GITHUB_USER" ]; then
    echo -e "${RED}[X] GitHub username cannot be empty${NC}"
    exit 1
fi

SETUP_URL="https://raw.githubusercontent.com/$GITHUB_USER/agent-second-brain/main/setup.sh"

echo "Downloading setup script..."

# Create temp file
TEMP_SCRIPT=$(mktemp /tmp/setup-XXXXXX.sh)

# Download setup script
if command -v curl &> /dev/null; then
    curl -fsSL "$SETUP_URL" -o "$TEMP_SCRIPT"
elif command -v wget &> /dev/null; then
    wget -q "$SETUP_URL" -O "$TEMP_SCRIPT"
else
    echo -e "${RED}[X] Neither curl nor wget found${NC}"
    echo "    Install: sudo apt install curl"
    exit 1
fi

if [ ! -s "$TEMP_SCRIPT" ]; then
    echo -e "${RED}[X] Failed to download setup script${NC}"
    rm -f "$TEMP_SCRIPT"
    exit 1
fi

echo -e "${GREEN}[OK] Downloaded${NC}"
echo ""

# Make executable and run PROPERLY (not via pipe!)
# exec replaces current process, so stdin works normally
chmod +x "$TEMP_SCRIPT"
exec bash "$TEMP_SCRIPT"
