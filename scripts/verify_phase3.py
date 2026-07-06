#!/usr/bin/env python
"""Phase 3 功能验证脚本"""

from pathlib import Path
import sys

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from paperbase.adapters.graphify_adapter import (
    check_graphify_installed,
    get_graph_stats,
)
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState

print("=" * 60)
print("Phase 3 功能验证")
print("=" * 60)

base_dir = Path(".")

# 1. 检查 graphify 安装
print("\n1. 检查 graphify 安装...")
if check_graphify_installed():
    print("   ✓ graphify 已安装")
else:
    print("   ✗ graphify 未安装")
    print("   请运行: uv tool install graphify")
    sys.exit(1)

# 2. 检查图谱目录
print("\n2. 检查图谱目录...")
graph_dir = base_dir / "graph"
if graph_dir.exists():
    stats = get_graph_stats(graph_dir)
    print(f"   ✓ 图谱目录存在")
    print(f"   文件数: {len(stats['files'])}")
    if stats['files']:
        print(f"   文件列表: {stats['files']}")
else:
    print("   ✗ 图谱目录不存在")
    print("   请运行: paperbase graph update")

# 3. 检查 GRAPHED 状态的论文
print("\n3. 检查 GRAPHED 状态的论文...")
registry_path = base_dir / "registry" / "papers.db"
if registry_path.exists():
    registry = PaperRegistry(registry_path)
    graphed_papers = registry.list_papers(state=PaperState.GRAPHED)
    registry.close()

    print(f"   已图谱化论文: {len(graphed_papers)} 篇")
    for paper in graphed_papers[:5]:
        print(f"     - {paper['title']} ({paper['paper_id']})")
else:
    print("   ✗ Registry 不存在")

# 4. 检查 manifest 的 graph 字段
print("\n4. 检查 manifest 的 graph 字段...")
papers_dir = base_dir / "library" / "papers"
if papers_dir.exists():
    manifests_with_graph = 0
    for manifest_path in papers_dir.glob("*/manifest.json"):
        import json
        with open(manifest_path) as f:
            manifest = json.load(f)
        if manifest.get("graph", {}).get("indexed"):
            manifests_with_graph += 1

    print(f"   包含 graph 信息的 manifest: {manifests_with_graph} 个")
else:
    print("   ✗ papers 目录不存在")

print("\n" + "=" * 60)
print("✅ Phase 3 验证完成")
print("=" * 60)
