#!/bin/bash
# PaperBase Skill Installer for Unix/Linux/macOS
# Installs the PaperBase skill to user's global AI agent directory

set -e

echo "🚀 PaperBase Skill Installer"
echo "=============================="
echo ""

# Detect AI agent configuration directory
CLAUDE_DIR="$HOME/.claude/skills"
CODEX_DIR="$HOME/.codex/skills"
INSTALL_DIR=""

if [ -d "$CLAUDE_DIR" ]; then
    INSTALL_DIR="$CLAUDE_DIR"
    echo "✓ Detected Claude Code configuration: $CLAUDE_DIR"
elif [ -d "$CODEX_DIR" ]; then
    INSTALL_DIR="$CODEX_DIR"
    echo "✓ Detected Codex configuration: $CODEX_DIR"
else
    echo "⚠️  No AI agent configuration directory found."
    echo "   Creating Claude Code skills directory..."
    mkdir -p "$CLAUDE_DIR"
    INSTALL_DIR="$CLAUDE_DIR"
    echo "✓ Created: $CLAUDE_DIR"
fi

echo ""

# Get script directory (where install.sh is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"

# Target directory
TARGET_DIR="$INSTALL_DIR/paperbase-skill"

# Check if skill already exists
if [ -d "$TARGET_DIR" ]; then
    echo "⚠️  Skill already exists at: $TARGET_DIR"
    read -p "   Overwrite? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Installation cancelled."
        exit 1
    fi
    echo "   Removing old version..."
    rm -rf "$TARGET_DIR"
fi

# Copy skill to global directory
echo "📦 Installing skill to: $TARGET_DIR"
cp -r "$SOURCE_DIR" "$TARGET_DIR"

# Make wrapper executable
chmod +x "$TARGET_DIR/paperbase-wrapper.sh"

# Verify installation
if [ -f "$TARGET_DIR/SKILL.md" ] && [ -f "$TARGET_DIR/README.md" ] && [ -f "$TARGET_DIR/paperbase-wrapper.sh" ]; then
    echo "✅ Installation successful!"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Restart your AI agent (if currently running)"
    echo "   2. In any conversation, type: /paperbase --help"
    echo "   3. Try: /paperbase status"
    echo ""
    echo "📖 Documentation: $TARGET_DIR/README.md"
else
    echo "❌ Installation failed. Please check file permissions."
    exit 1
fi

echo ""
echo "🎉 Done! The /paperbase skill is now available globally."
echo ""
echo "🔍 Verifying dependencies..."

# Check uv
if ! command -v uv &> /dev/null; then
    echo "⚠️  'uv' not found. Install: https://github.com/astral-sh/uv"
else
    echo "✓ uv: $(uv --version)"
fi

# Check paperbase CLI (optional, only if in a PaperBase repo)
if [ -f "$(pwd)/../../pyproject.toml" ]; then
    cd ../..
    if uv run paperbase --version &> /dev/null; then
        echo "✓ PaperBase CLI: Available"
    else
        echo "⚠️  PaperBase CLI not available. Run 'uv sync' in project root."
    fi
fi
