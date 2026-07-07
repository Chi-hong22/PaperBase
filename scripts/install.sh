#!/bin/bash
# PaperBase One-Command Installer
# Supports: Ubuntu, Debian, macOS, Arch Linux, Fedora

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🚀 PaperBase Installer v1.0.0      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Check Python version
echo -e "${BLUE}[1/6]${NC} Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    REQUIRED_VERSION="3.11"

    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" = "$REQUIRED_VERSION" ]; then
        echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"
    else
        echo -e "${RED}✗${NC} Python 3.11+ required (found $PYTHON_VERSION)"
        echo ""
        echo "Install Python 3.11+:"
        echo "  - Ubuntu/Debian: sudo apt install python3.11"
        echo "  - macOS: brew install python@3.11"
        echo "  - Arch: sudo pacman -S python"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Python 3 not found"
    exit 1
fi

# Step 2: Check Git
echo -e "${BLUE}[2/6]${NC} Checking Git..."
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | awk '{print $3}')
    echo -e "${GREEN}✓${NC} Git $GIT_VERSION"
else
    echo -e "${RED}✗${NC} Git not found"
    echo ""
    echo "Install Git:"
    echo "  - Ubuntu/Debian: sudo apt install git"
    echo "  - macOS: brew install git"
    echo "  - Arch: sudo pacman -S git"
    exit 1
fi

# Step 3: Check disk space
echo -e "${BLUE}[3/6]${NC} Checking disk space..."
AVAILABLE_SPACE=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE" -ge 2 ]; then
    echo -e "${GREEN}✓${NC} ${AVAILABLE_SPACE}GB available"
else
    echo -e "${YELLOW}⚠${NC}  Only ${AVAILABLE_SPACE}GB available (2GB+ recommended)"
fi

# Step 4: Install uv
echo -e "${BLUE}[4/6]${NC} Installing uv package manager..."
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version | awk '{print $2}')
    echo -e "${GREEN}✓${NC} uv already installed ($UV_VERSION)"
else
    echo "   Downloading uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for this session
    export PATH="$HOME/.cargo/bin:$PATH"

    if command -v uv &> /dev/null; then
        echo -e "${GREEN}✓${NC} uv installed successfully"
    else
        echo -e "${RED}✗${NC} uv installation failed"
        exit 1
    fi
fi

# Step 5: Clone PaperBase
echo -e "${BLUE}[5/6]${NC} Cloning PaperBase repository..."
if [ -d "PaperBase" ]; then
    echo -e "${YELLOW}⚠${NC}  PaperBase directory already exists"
    read -p "   Remove and re-clone? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf PaperBase
        git clone https://github.com/Chi-hong22/PaperBase.git
    else
        cd PaperBase
    fi
else
    git clone https://github.com/Chi-hong22/PaperBase.git
    cd PaperBase
fi

echo -e "${GREEN}✓${NC} Repository cloned"

# Step 6: Install dependencies
echo -e "${BLUE}[6/6]${NC} Installing dependencies..."
uv sync

echo -e "${GREEN}✓${NC} Dependencies installed"

# Optional: Install graphify
echo ""
echo -e "${YELLOW}Optional:${NC} Install graphify for knowledge graph features?"
read -p "Install graphify? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    uv tool install graphify
    echo -e "${GREEN}✓${NC} graphify installed"
else
    echo -e "${YELLOW}⚠${NC}  Skipped graphify (can install later with: uv tool install graphify)"
fi

# Verify installation
echo ""
echo -e "${BLUE}Verifying installation...${NC}"
if uv run paperbase --version &> /dev/null; then
    echo -e "${GREEN}✓${NC} PaperBase CLI working"
else
    echo -e "${RED}✗${NC} PaperBase CLI verification failed"
    exit 1
fi

# Success message
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ Installation Complete!           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. cd PaperBase"
echo "  2. uv run paperbase ingest \"arxiv:1706.03762\""
echo "  3. uv run paperbase search \"attention mechanism\""
echo ""
echo "Documentation: https://github.com/Chi-hong22/PaperBase"
echo "Issues: https://github.com/Chi-hong22/PaperBase/issues"
