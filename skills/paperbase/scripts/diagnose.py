#!/usr/bin/env python3
"""
PaperBase Diagnostic Script

Deep diagnostic analysis for troubleshooting issues.
"""

import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter


def diagnose_library(base_dir: Path) -> Dict:
    """Diagnose library directory"""
    library_dir = base_dir / "library" / "papers"

    if not library_dir.exists():
        return {"status": "error", "message": "library/papers/ 不存在"}

    paper_dirs = [d for d in library_dir.iterdir() if d.is_dir() and d.name.startswith("p_")]

    issues = []
    states = Counter()
    missing_files = []

    for paper_dir in paper_dirs:
        # Check required files
        paper_md = paper_dir / "paper.md"
        manifest_json = paper_dir / "manifest.json"

        if not paper_md.exists():
            missing_files.append(f"{paper_dir.name}/paper.md")

        if not manifest_json.exists():
            missing_files.append(f"{paper_dir.name}/manifest.json")
            continue

        # Parse manifest
        try:
            with open(manifest_json) as f:
                manifest = json.load(f)
            states[manifest.get("state", "unknown")] += 1
        except Exception as e:
            issues.append(f"{paper_dir.name}/manifest.json 解析失败: {e}")

    return {
        "status": "ok",
        "paper_count": len(paper_dirs),
        "states": dict(states),
        "missing_files": missing_files,
        "issues": issues
    }


def diagnose_registry(base_dir: Path) -> Dict:
    """Diagnose registry database"""
    registry_path = base_dir / "registry" / "papers.db"

    if not registry_path.exists():
        return {"status": "warning", "message": "registry/papers.db 不存在"}

    try:
        conn = sqlite3.connect(registry_path)
        cursor = conn.cursor()

        # Count papers
        cursor.execute("SELECT COUNT(*) FROM papers")
        total = cursor.fetchone()[0]

        # Count by state
        cursor.execute("SELECT state, COUNT(*) FROM papers GROUP BY state")
        states = dict(cursor.fetchall())

        # Check for NULL values
        cursor.execute("SELECT COUNT(*) FROM papers WHERE title IS NULL")
        null_titles = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM papers WHERE authors IS NULL OR authors = '[]'")
        null_authors = cursor.fetchone()[0]

        conn.close()

        issues = []
        if null_titles > 0:
            issues.append(f"{null_titles} 篇论文缺少标题")
        if null_authors > 0:
            issues.append(f"{null_authors} 篇论文缺少作者")

        return {
            "status": "ok",
            "total": total,
            "states": states,
            "issues": issues
        }
    except Exception as e:
        return {"status": "error", "message": f"Registry 损坏: {e}"}


def diagnose_consistency(base_dir: Path, library_info: Dict, registry_info: Dict) -> Dict:
    """Check consistency between library and registry"""
    if library_info["status"] != "ok" or registry_info["status"] != "ok":
        return {"status": "skipped", "message": "前置检查失败"}

    library_count = library_info["paper_count"]
    registry_count = registry_info["total"]

    issues = []

    if library_count != registry_count:
        issues.append(
            f"论文数量不一致: library 有 {library_count} 篇，registry 有 {registry_count} 篇"
        )

    # Compare states
    library_states = library_info["states"]
    registry_states = registry_info["states"]

    for state in set(library_states.keys()) | set(registry_states.keys()):
        lib_count = library_states.get(state, 0)
        reg_count = registry_states.get(state, 0)

        if lib_count != reg_count:
            issues.append(
                f"状态 '{state}' 不一致: library 有 {lib_count} 篇，registry 有 {reg_count} 篇"
            )

    if issues:
        return {"status": "error", "issues": issues}
    else:
        return {"status": "ok", "message": "library 与 registry 一致"}


def diagnose_graph(base_dir: Path) -> Dict:
    """Diagnose graph directory"""
    graph_dir = base_dir / "graph"

    if not graph_dir.exists():
        return {"status": "warning", "message": "graph/ 不存在"}

    graph_json = graph_dir / "graph.json"
    if not graph_json.exists():
        return {"status": "warning", "message": "graph/graph.json 不存在"}

    try:
        with open(graph_json) as f:
            graph = json.load(f)

        nodes = len(graph.get("nodes", []))
        edges = len(graph.get("edges", []))

        # Count paper nodes
        paper_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "paper"]

        return {
            "status": "ok",
            "nodes": nodes,
            "edges": edges,
            "paper_nodes": len(paper_nodes)
        }
    except Exception as e:
        return {"status": "error", "message": f"graph.json 损坏: {e}"}


def main():
    """Run diagnostic analysis"""
    print("🔬 PaperBase Diagnostic Tool\n" + "=" * 60)

    # Determine base directory
    base_dir = Path.cwd()
    if not (base_dir / "library").exists():
        base_dir = base_dir.parent
        if not (base_dir / "library").exists():
            print("❌ 未找到 PaperBase 库")
            sys.exit(1)

    print(f"📁 Base Directory: {base_dir}\n")

    # Run diagnostics
    print("1️⃣  检查 library/")
    library_info = diagnose_library(base_dir)
    print(f"   Status: {library_info['status']}")
    if library_info["status"] == "ok":
        print(f"   Papers: {library_info['paper_count']}")
        print(f"   States: {library_info['states']}")
        if library_info["missing_files"]:
            print(f"   ⚠️  缺少 {len(library_info['missing_files'])} 个文件")
        if library_info["issues"]:
            print(f"   ⚠️  {len(library_info['issues'])} 个问题")

    print("\n2️⃣  检查 registry/")
    registry_info = diagnose_registry(base_dir)
    print(f"   Status: {registry_info['status']}")
    if registry_info["status"] == "ok":
        print(f"   Total: {registry_info['total']}")
        print(f"   States: {registry_info['states']}")
        if registry_info["issues"]:
            for issue in registry_info["issues"]:
                print(f"   ⚠️  {issue}")

    print("\n3️⃣  检查一致性")
    consistency_info = diagnose_consistency(base_dir, library_info, registry_info)
    print(f"   Status: {consistency_info['status']}")
    if consistency_info["status"] == "error":
        for issue in consistency_info["issues"]:
            print(f"   ❌ {issue}")
    elif consistency_info["status"] == "ok":
        print(f"   ✅ {consistency_info['message']}")

    print("\n4️⃣  检查 graph/")
    graph_info = diagnose_graph(base_dir)
    print(f"   Status: {graph_info['status']}")
    if graph_info["status"] == "ok":
        print(f"   Nodes: {graph_info['nodes']}")
        print(f"   Edges: {graph_info['edges']}")
        print(f"   Papers: {graph_info['paper_nodes']}")

    # Summary
    print("\n" + "=" * 60)

    all_ok = all(
        info["status"] in ["ok", "warning"]
        for info in [library_info, registry_info, consistency_info, graph_info]
    )

    if all_ok:
        print("✅ 诊断完成，未发现严重问题")
    else:
        print("❌ 发现问题，建议:")

        if consistency_info["status"] == "error":
            print("   1. 重建 registry: rm registry/papers.db && paperbase status")

        if library_info.get("missing_files"):
            print("   2. 检查并修复缺失的文件")

        if graph_info["status"] == "error":
            print("   3. 重建 graph: paperbase graph update --force")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
