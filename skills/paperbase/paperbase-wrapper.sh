#!/bin/bash
# PaperBase CLI Wrapper - Auto-detect library and execute commands
# Version: 0.2.0 - Added workspace configuration persistence

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect skill installation directory
get_skill_dir() {
    local script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    local script_dir="$(dirname "$script_path")"
    echo "$script_dir"
}

# Get configuration file path
get_config_path() {
    local skill_dir="$(get_skill_dir)"
    echo "$skill_dir/workspaces.json"
}

# Find project root (向上查找 .git 或 pyproject.toml)
find_project_root() {
    local current_dir="$(pwd)"

    while [ "$current_dir" != "/" ]; do
        if [ -d "$current_dir/.git" ] || [ -f "$current_dir/pyproject.toml" ]; then
            echo "$current_dir"
            return 0
        fi
        current_dir="$(dirname "$current_dir")"
    done

    return 1
}

# Load library path from configuration
load_config() {
    local project_root="$1"
    local config_path="$(get_config_path)"

    if [ ! -f "$config_path" ]; then
        return 1
    fi

    # 使用 python 读取 JSON（兼容性更好）
    local library_path=$(python3 -c "
import json
import sys
try:
    with open('$config_path', 'r') as f:
        config = json.load(f)
        workspaces = config.get('workspaces', {})
        workspace = workspaces.get('$project_root', {})
        library_path = workspace.get('library_path', '')
        if library_path:
            print(library_path)
            sys.exit(0)
except:
    pass
sys.exit(1)
" 2>/dev/null)

    if [ -n "$library_path" ] && [ -d "$library_path" ]; then
        echo "$library_path"
        return 0
    fi

    return 1
}

# Save library path to configuration
save_config() {
    local project_root="$1"
    local library_path="$2"
    local config_path="$(get_config_path)"

    # 使用 python 写入 JSON
    python3 -c "
import json
import os
from datetime import datetime, timezone

config_path = '$config_path'
project_root = '$project_root'
library_path = '$library_path'

# 读取现有配置
if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        config = json.load(f)
else:
    config = {'workspaces': {}}

# 更新配置
if 'workspaces' not in config:
    config['workspaces'] = {}

config['workspaces'][project_root] = {
    'library_path': library_path,
    'last_used': datetime.now(timezone.utc).isoformat()
}

# 写入配置
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
" 2>/dev/null
}

# Auto-detect PaperBase library
detect_library() {
    # Step 1: Check environment variable first
    if [ -n "$PAPERBASE_LIBRARY" ] && [ -d "$PAPERBASE_LIBRARY" ]; then
        echo "$PAPERBASE_LIBRARY"
        return 0
    fi

    # Step 2: Find project root
    local project_root=$(find_project_root)

    if [ -n "$project_root" ]; then
        # Step 3: Try loading from configuration
        local cached_library=$(load_config "$project_root")
        if [ -n "$cached_library" ]; then
            echo "$cached_library"
            return 0
        fi

        # Step 4: Auto-detect in project root
        if [ -d "$project_root/library/papers" ]; then
            local library_path="$project_root/library"
            save_config "$project_root" "$library_path"
            echo "$library_path"
            return 0
        fi
    fi

    # Step 5: Fallback - Check current directory
    if [ -d "./library/papers" ]; then
        echo "$(pwd)/library"
        return 0
    fi

    # Step 6: Fallback - Check parent directory
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
