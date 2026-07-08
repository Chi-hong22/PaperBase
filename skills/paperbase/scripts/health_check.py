#!/usr/bin/env python3
"""
PaperBase Health Check Script

Comprehensive health check for PaperBase installation and data.
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Tuple


def check_python_version() -> Tuple[bool, str]:
    """Check if Python version >= 3.11"""
    version = sys.version_info
    if version >= (3, 11):
        return True, f"✅ Python {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"❌ Python {version.major}.{version.minor}.{version.micro} (需要 >= 3.11)"


def check_command(cmd: str, name: str, required: bool = True) -> Tuple[bool, str]:
    """Check if a command is available"""
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.split("\n")[0]
            return True, f"✅ {name}: {version}"
        else:
            status = "❌" if required else "⚠️"
            return not required, f"{status} {name}: 未找到"
    except FileNotFoundError:
        status = "❌" if required else "⚠️"
        suffix = "" if required else " (可选)"
        return not required, f"{status} {name}: 未找到{suffix}"
    except Exception as e:
        return False, f"❌ {name}: 检查失败 ({e})"


def check_library_structure(base_dir: Path) -> Tuple[bool, str]:
    """Check if library directory structure is valid"""
    library_dir = base_dir / "library"

    if not library_dir.exists():
        return False, "❌ library/ 目录不存在"

    papers_dir = library_dir / "papers"
    if not papers_dir.exists():
        return False, "❌ library/papers/ 目录不存在"

    # Count papers
    paper_dirs = [d for d in papers_dir.iterdir() if d.is_dir() and d.name.startswith("p_")]
    paper_count = len(paper_dirs)

    if paper_count == 0:
        return True, "⚠️  library/ 存在但为空（0 篇论文）"

    return True, f"✅ library/ 结构正常（{paper_count} 篇论文）"


def check_registry(base_dir: Path) -> Tuple[bool, str]:
    """Check registry database"""
    registry_path = base_dir / "registry" / "papers.db"

    if not registry_path.exists():
        return True, "⚠️  registry/papers.db 不存在（将在首次使用时自动创建）"

    # Check file size
    size_bytes = registry_path.stat().st_size
    size_kb = size_bytes / 1024

    if size_bytes == 0:
        return False, "❌ registry/papers.db 为空文件"

    # Try to query
    try:
        import sqlite3
        conn = sqlite3.connect(registry_path)
        cursor = conn.execute("SELECT COUNT(*) FROM papers")
        count = cursor.fetchone()[0]
        conn.close()
        return True, f"✅ registry/papers.db 正常（{count} 篇论文，{size_kb:.1f} KB）"
    except Exception as e:
        return False, f"❌ registry/papers.db 损坏: {e}"


def check_graph(base_dir: Path) -> Tuple[bool, str]:
    """Check graph directory"""
    graph_dir = base_dir / "graph"

    if not graph_dir.exists():
        return True, "⚠️  graph/ 不存在（运行 'paperbase graph update' 创建）"

    graph_json = graph_dir / "graph.json"
    if not graph_json.exists():
        return True, "⚠️  graph/graph.json 不存在（运行 'paperbase graph update'）"

    # Count files
    files = list(graph_dir.iterdir())
    file_count = len([f for f in files if f.is_file()])

    # Try to parse graph.json
    try:
        with open(graph_json) as f:
            graph_data = json.load(f)
        nodes = len(graph_data.get("nodes", []))
        edges = len(graph_data.get("edges", []))
        return True, f"✅ graph/ 正常（{file_count} 个文件，{nodes} 节点，{edges} 边）"
    except Exception as e:
        return False, f"❌ graph/graph.json 损坏: {e}"


def check_config(base_dir: Path) -> Tuple[bool, str]:
    """Check configuration file"""
    config_path = base_dir / "config" / "paperbase.yaml"

    if not config_path.exists():
        return False, "❌ config/paperbase.yaml 不存在"

    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check LLM config
        llm = config.get("llm", {})
        llm_enabled = bool(llm.get("base_url") and llm.get("model"))

        if llm_enabled:
            return True, f"✅ config/paperbase.yaml 正常（LLM 已配置）"
        else:
            return True, f"✅ config/paperbase.yaml 正常（LLM 未配置）"
    except Exception as e:
        return False, f"❌ config/paperbase.yaml 解析失败: {e}"


def check_disk_space(base_dir: Path) -> Tuple[bool, str]:
    """Check available disk space"""
    try:
        import shutil
        stat = shutil.disk_usage(base_dir)
        free_gb = stat.free / (1024 ** 3)

        if free_gb < 1:
            return False, f"❌ 磁盘空间不足: {free_gb:.1f} GB 可用"
        elif free_gb < 5:
            return True, f"⚠️  磁盘空间较低: {free_gb:.1f} GB 可用"
        else:
            return True, f"✅ 磁盘空间充足: {free_gb:.1f} GB 可用"
    except Exception as e:
        return True, f"⚠️  无法检查磁盘空间: {e}"


def main():
    """Run all health checks"""
    print("🔍 PaperBase Health Check\n" + "=" * 60)

    # Determine base directory
    base_dir = Path.cwd()
    if not (base_dir / "library").exists():
        # Try parent directory
        base_dir = base_dir.parent
        if not (base_dir / "library").exists():
            print("❌ 错误: 未找到 PaperBase 库")
            print("   请在 PaperBase 根目录运行此脚本")
            sys.exit(1)

    print(f"📁 Base Directory: {base_dir}\n")

    # Run checks
    checks = [
        ("Python 版本", check_python_version()),
        ("uv 包管理器", check_command("uv", "uv", required=True)),
        ("graphify", check_command("graphify", "graphify", required=False)),
        ("库结构", check_library_structure(base_dir)),
        ("Registry 数据库", check_registry(base_dir)),
        ("知识图谱", check_graph(base_dir)),
        ("配置文件", check_config(base_dir)),
        ("磁盘空间", check_disk_space(base_dir)),
    ]

    # Print results
    all_passed = True
    for name, (passed, message) in checks:
        print(f"{name:20} {message}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("✅ 所有检查通过！")
        sys.exit(0)
    else:
        print("❌ 部分检查失败，请查看上述错误信息")
        print("\n建议:")
        print("  1. 运行 'paperbase doctor' 查看详细诊断")
        print("  2. 查看 references/troubleshooting.md 获取帮助")
        sys.exit(1)


if __name__ == "__main__":
    main()
