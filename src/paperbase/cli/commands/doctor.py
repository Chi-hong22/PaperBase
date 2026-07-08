"""
PaperBase Doctor - Environment Diagnostics Tool

Checks system dependencies, configuration, and library health.
"""

import sys
import subprocess
import shutil
import click
from pathlib import Path
from typing import List, Tuple

def check_python_version() -> Tuple[bool, str]:
    """Check Python version >= 3.11"""
    version = sys.version_info
    if version >= (3, 11):
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"Python {version.major}.{version.minor}.{version.micro} (3.11+ required)"

def check_uv() -> Tuple[bool, str]:
    """Check if uv is available"""
    if shutil.which("uv"):
        try:
            result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return False, f"uv command failed: {result.stderr.strip()}"
            version = result.stdout.strip().replace("uv ", "")
            return True, f"uv {version}"
        except Exception:
            return False, "uv found but version check failed"
    return False, "uv not found"

def check_graphify() -> Tuple[bool, str]:
    """Check if graphify is available"""
    if shutil.which("graphify"):
        try:
            result = subprocess.run(["graphify", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return False, f"graphify command failed: {result.stderr.strip()}"
            version = result.stdout.strip()
            return True, f"graphify {version}"
        except Exception:
            return True, "graphify (version unknown)"
    return False, "graphify not found (optional)"

def check_sqlite_version() -> Tuple[bool, str]:
    """Check SQLite version for FTS5 support"""
    try:
        import sqlite3
        version = sqlite3.sqlite_version
        major, minor, patch = map(int, version.split("."))

        if (major, minor) >= (3, 41):
            return True, f"SQLite {version} (FTS5 supported)"
        else:
            return False, f"SQLite {version} (3.41+ required for FTS5)"
    except Exception as e:
        return False, f"SQLite check failed: {e}"

def check_library() -> Tuple[bool, str]:
    """Check if PaperBase library exists"""
    library_path = Path("library")
    if library_path.exists():
        papers_dir = library_path / "papers"
        if papers_dir.exists():
            paper_count = len(list(papers_dir.glob("p_*")))
            return True, f"Library found ({paper_count} papers)"
        else:
            return False, "Library exists but papers/ directory missing"
    return False, "Library not found (run from PaperBase root or set PAPERBASE_LIBRARY)"

def check_registry() -> Tuple[bool, str]:
    """Check registry database"""
    registry_path = Path("registry/papers.sqlite")
    if registry_path.exists():
        size = registry_path.stat().st_size / 1024  # KB
        return True, f"Registry database found ({size:.1f} KB)"
    return False, "Registry database not found (will auto-create on first use)"

def check_graph() -> Tuple[bool, str]:
    """Check knowledge graph"""
    graph_path = Path("graph")
    if graph_path.exists():
        files = list(graph_path.glob("*.json"))
        if files:
            return True, f"Knowledge graph found ({len(files)} files)"
        return True, "Knowledge graph directory exists (empty)"
    return False, "Knowledge graph not found (run 'graph update' to create)"

def check_paper_fetch() -> Tuple[bool, str]:
    """Check if paper-fetch-skill is available"""
    try:
        import paper_fetch  # noqa: F401
        return True, "installed"
    except ImportError:
        return False, "not installed; run `uv sync --extra online-fetch`"

def check_llm_config() -> Tuple[bool, str]:
    """Check LLM configuration"""
    try:
        import os
        import yaml
        from pathlib import Path

        config_path = Path("config/paperbase.yaml")
        if not config_path.exists():
            return False, "config/paperbase.yaml not found"

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        llm_config = config.get("llm", {})
        enabled = llm_config.get("enabled", False)

        if not enabled:
            return True, "disabled (optional)"

        # 检查环境变量
        base_url = os.getenv("PAPERBASE_LLM_BASE_URL")
        api_key = os.getenv("PAPERBASE_LLM_API_KEY")
        model = os.getenv("PAPERBASE_LLM_MODEL")

        if not all([base_url, api_key, model]):
            missing = []
            if not base_url: missing.append("BASE_URL")
            if not api_key: missing.append("API_KEY")
            if not model: missing.append("MODEL")
            return False, f"enabled but env vars missing: {', '.join(missing)}"

        return True, f"enabled ({model})"

    except Exception as e:
        return False, f"check failed: {e}"


def main():
    print("🔍 PaperBase Doctor - Environment Diagnostics\n")
    print("=" * 60)

    checks: List[Tuple[str, Tuple[bool, str]]] = [
        ("Python Version", check_python_version()),
        ("uv Package Manager", check_uv()),
        ("graphify (optional)", check_graphify()),
        ("paper-fetch (optional)", check_paper_fetch()),
        ("SQLite Version", check_sqlite_version()),
        ("LLM Configuration", check_llm_config()),
        ("PaperBase Library", check_library()),
        ("Registry Database", check_registry()),
        ("Knowledge Graph", check_graph()),
    ]

    all_pass = True
    optional_fail = []

    for name, (passed, message) in checks:
        status = "✅" if passed else ("⚠️" if "optional" in name.lower() else "❌")
        print(f"{status} {name:25} {message}")

        if not passed:
            if "optional" in name.lower():
                optional_fail.append((name, message))
            else:
                all_pass = False

    print("=" * 60)

    if all_pass:
        print("\n✅ All required checks passed!")
        if optional_fail:
            print("\n⚠️  Optional components not installed:")
            for name, msg in optional_fail:
                print(f"   - {name}: {msg}")
            print("\n   Install with: uv tool install graphify")
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        print("\nCommon solutions:")
        print("  - Python 3.11+: Download from https://www.python.org/downloads/")
        print("  - uv: Install with 'curl -LsSf https://astral.sh/uv/install.sh | sh'")
        print("  - Library not found: Run from PaperBase repository root")
        print("  - SQLite < 3.41: Upgrade Python or install system SQLite")
        sys.exit(1)

    print("\nDocumentation: https://github.com/Chi-hong22/PaperBase")
    print("Issues: https://github.com/Chi-hong22/PaperBase/issues")

@click.command()
@click.pass_context
def doctor(ctx):
    """Run environment diagnostics"""
    main()

if __name__ == "__main__":
    main()
