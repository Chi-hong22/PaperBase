"""
PaperBase Doctor - Environment Diagnostics Tool

Checks system dependencies, configuration, and library health.
"""

import json
import sys
import subprocess
import shutil
import click
from pathlib import Path
from typing import List, Tuple
from paperbase.utils.markdown import find_local_absolute_image_paths

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

def check_library(base_dir: Path) -> Tuple[bool, str]:
    """Check if PaperBase library exists"""
    # 优先使用 Registry 统计论文数量
    registry_path = base_dir / "registry" / "papers.db"
    if registry_path.exists():
        try:
            from paperbase.core.registry import PaperRegistry
            with PaperRegistry(registry_path) as registry:
                paper_count = len(registry.list_papers())
            return True, f"Library found ({paper_count} papers)"
        except Exception:
            pass  # fallback to directory scanning

    # Fallback: 统计 Canonical Markdown 文件
    library_path = base_dir / "library"
    if library_path.exists():
        papers_dir = library_path / "papers"
        if papers_dir.exists():
            paper_count = len(list(papers_dir.glob("p_*.md")))
            return True, f"Library found ({paper_count} papers, no registry)"
        else:
            return False, "Library exists but papers/ directory missing"
    return False, "Library not found (run from PaperBase root or set PAPERBASE_LIBRARY)"

def check_registry(base_dir: Path) -> Tuple[bool, str]:
    """Check registry database"""
    registry_path = base_dir / "registry" / "papers.db"
    if registry_path.exists():
        size = registry_path.stat().st_size / 1024  # KB
        return True, f"Registry database found ({size:.1f} KB)"
    return False, "Registry database not found (will auto-create on first use)"

def check_library_consistency(base_dir: Path) -> Tuple[bool, str]:
    """Check that Registry records and Canonical Markdown agree."""
    papers_dir = base_dir / "library" / "papers"
    registry_path = base_dir / "registry" / "papers.db"
    if not papers_dir.exists() or not registry_path.exists():
        return True, "Consistency check skipped (library or registry unavailable)"

    canonical_ids = {path.stem for path in papers_dir.glob("p_*.md")}
    try:
        from paperbase.core.registry import PaperRegistry
        with PaperRegistry(registry_path) as registry:
            registry_ids = {paper["storage_id"] for paper in registry.list_papers()}
    except Exception as e:
        return False, f"Consistency check failed: {e}"

    canonical_not_registered = canonical_ids - registry_ids
    registry_missing_canonical = registry_ids - canonical_ids
    if canonical_not_registered or registry_missing_canonical:
        return False, (
            f"Canonical not registered: {len(canonical_not_registered)}; "
            f"Registry missing canonical: {len(registry_missing_canonical)}"
        )

    return True, "Registry and Canonical Markdown are consistent"


def check_canonical_asset_paths(base_dir: Path) -> Tuple[bool, str]:
    """Reject machine-local absolute image paths in Canonical Markdown."""
    papers_dir = base_dir / "library" / "papers"
    if not papers_dir.is_dir():
        return True, "Canonical asset path check skipped (library unavailable)"

    violations: list[str] = []
    for paper_path in papers_dir.glob("p_*.md"):
        try:
            content = paper_path.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"Canonical asset path check failed: {e}"

        if find_local_absolute_image_paths(content):
            violations.append(paper_path.name)

    if violations:
        return False, f"Canonical Markdown contains local absolute asset paths: {len(violations)} files"
    return True, "Canonical Markdown asset paths are portable"

def check_graph(base_dir: Path) -> Tuple[bool, str]:
    """Check knowledge graph"""
    graph_path = base_dir / "graph"
    if not graph_path.is_dir():
        return False, "Knowledge graph not found (run 'graph update' to create)"

    graph_json = graph_path / "graph.json"
    if not graph_json.is_file():
        return False, "Knowledge graph missing graph.json (run 'graph update' to create)"

    try:
        graph_data = json.loads(graph_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Knowledge graph graph.json is invalid: {e}"

    edges = graph_data.get("links", graph_data.get("edges")) if isinstance(graph_data, dict) else None
    if not isinstance(graph_data, dict) or not isinstance(graph_data.get("nodes"), list) or not isinstance(edges, list):
        return False, "Knowledge graph graph.json has invalid node-link structure"

    return True, "Knowledge graph found (graph.json)"

def check_paper_fetch() -> Tuple[bool, str]:
    """Check if paper-fetch CLI is available"""
    if shutil.which("paper-fetch"):
        try:
            result = subprocess.run(
                ["paper-fetch", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return True, f"paper-fetch {version}"
            else:
                return True, "paper-fetch (version unknown)"
        except Exception:
            return True, "paper-fetch (version check failed)"
    return False, "not installed (optional); install with: uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git"

def check_llm_config(base_dir: Path | None = None) -> Tuple[bool, str]:
    """Check LLM configuration"""
    try:
        from paperbase.config.loader import load_config

        config_path = base_dir / "config" / "paperbase.yaml" if base_dir else None
        config = load_config(config_path)

        if not config.llm.is_enabled():
            return True, "disabled (optional)"

        # LLM 已启用，检查必需字段
        model = config.llm.model
        base_url = config.llm.base_url

        if not model or not base_url:
            missing = []
            if not base_url: missing.append("base_url")
            if not model: missing.append("model")
            return False, f"enabled but missing: {', '.join(missing)}"

        return True, f"enabled ({model})"

    except Exception as e:
        return False, f"check failed: {e}"


def main(base_dir: Path | None = None):
    base_dir = base_dir or Path.cwd()
    print("🔍 PaperBase Doctor - Environment Diagnostics\n")
    print("=" * 60)

    checks: List[Tuple[str, Tuple[bool, str]]] = [
        ("Python Version", check_python_version()),
        ("uv Package Manager", check_uv()),
        ("graphify (optional)", check_graphify()),
        ("paper-fetch (optional)", check_paper_fetch()),
        ("SQLite Version", check_sqlite_version()),
        ("LLM Configuration", check_llm_config(base_dir)),
        ("PaperBase Library", check_library(base_dir)),
        ("Registry Database", check_registry(base_dir)),
        ("Library Consistency", check_library_consistency(base_dir)),
        ("Canonical Asset Paths", check_canonical_asset_paths(base_dir)),
        ("Knowledge Graph", check_graph(base_dir)),
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
    main(ctx.obj["base_dir"])

if __name__ == "__main__":
    main()
