#!/bin/bash
# PaperBase CLI Wrapper - Auto-detect library and execute commands
# Version: 0.1.0

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Auto-detect PaperBase library
detect_library() {
    # Check environment variable first
    if [ -n "$PAPERBASE_LIBRARY" ] && [ -d "$PAPERBASE_LIBRARY" ]; then
        echo "$PAPERBASE_LIBRARY"
        return 0
    fi

    # Check current directory
    if [ -d "./library/papers" ]; then
        echo "$(pwd)/library"
        return 0
    fi

    # Check parent directory
    if [ -d "../library/papers" ]; then
        echo "$(cd .. && pwd)/library"
        return 0
    fi

    # Not found
    return 1
}

# Main execution
LIBRARY_PATH=$(detect_library)

if [ -z "$LIBRARY_PATH" ]; then
    echo -e "${RED}Error: PaperBase library not found${NC}"
    echo ""
    echo "Solutions:"
    echo "  1. Run from PaperBase repository root"
    echo "  2. Set environment variable: export PAPERBASE_LIBRARY='/path/to/library'"
    echo "  3. Navigate to a PaperBase directory"
    exit 1
fi

# Navigate to repository root
REPO_ROOT="$(dirname "$LIBRARY_PATH")"
cd "$REPO_ROOT"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: 'uv' command not found${NC}"
    echo "Install: https://github.com/astral-sh/uv"
    exit 1
fi

# Execute paperbase CLI
echo -e "${GREEN}[PaperBase]${NC} Using library: $LIBRARY_PATH"
uv run paperbase "$@"
