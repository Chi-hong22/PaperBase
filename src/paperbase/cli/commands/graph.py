"""graph 命令实现"""

import click
from rich.console import Console
from pathlib import Path
from datetime import datetime, UTC
from paperbase.adapters.graphify_adapter import (
    check_graphify_installed,
    run_graphify,
    get_graph_stats,
)
from paperbase.core.registry import PaperRegistry
from paperbase.core.manifest import load_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.schemas.manifest import PaperState, GraphInfo
from paperbase.core.graph_updater import detect_changed_papers
from paperbase.core.entity_graph_builder import EntityGraphBuilder


@click.group()
def graph():
    """知识图谱管理"""
    pass


@graph.command()
@click.option(
    "--force",
    is_flag=True,
    help="强制重建图谱（删除现有数据）"
)
@click.option(
    "--incremental",
    is_flag=True,
    help="仅更新内容发生变化的论文"
)
@click.pass_context
def update(ctx, force: bool, incremental: bool):
    """更新知识图谱"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]开始更新知识图谱...[/cyan]")

    # 互斥检查
    if force and incremental:
        console.print("[red]❌ --force 和 --incremental 不能同时使用[/red]")
        raise click.Abort()

    # Step 1: 检查 graphify 是否安装
    console.print("[yellow]1. 检查 graphify 安装...[/yellow]")
    if not check_graphify_installed():
        console.print("[red]❌ graphify 未安装[/red]")
        console.print("   请运行: [cyan]uv tool install graphify[/cyan]")
        raise click.Abort()

    console.print("   ✓ graphify 已安装")

    # Step 2: 增量模式检测
    library_dir = base_dir / "library"
    if incremental:
        console.print("[yellow]2. 检测内容变化的论文（增量模式）...[/yellow]")
        changed_papers = detect_changed_papers(library_dir)

        if not changed_papers:
            console.print("   ✓ 没有论文需要更新")
            console.print("\n[green]✅ 图谱已是最新状态[/green]")
            return

        console.print(f"   找到 {len(changed_papers)} 篇需要更新的论文：")
        for paper in changed_papers[:5]:  # 最多显示 5 篇
            console.print(f"     - {paper['paper_id']}: {paper['reason']}")
        if len(changed_papers) > 5:
            console.print(f"     ... 还有 {len(changed_papers) - 5} 篇")

        # 增量模式下，只更新变化的论文
        normalized_papers = changed_papers
    else:
        # Step 2: 检查是否有 NORMALIZED 论文（全量模式）
        console.print("[yellow]2. 检查待图谱化的论文...[/yellow]")
        registry_path = base_dir / "registry" / "papers.db"
        if not registry_path.exists():
            console.print("[red]❌ Registry 不存在，请先摄入论文[/red]")
            raise click.Abort()

        registry = PaperRegistry(registry_path)
        normalized_papers = registry.list_papers(state=PaperState.NORMALIZED)
        all_papers = registry.list_papers()
        registry.close()

        console.print(f"   找到 {len(normalized_papers)} 篇待图谱化论文")
        console.print(f"   总计 {len(all_papers)} 篇论文")

    # Step 3: 运行 graphify
    console.print("[yellow]3. 运行 graphify...[/yellow]")
    library_dir = base_dir / "library"
    graph_dir = base_dir / "graph"

    result = run_graphify(
        library_dir=library_dir,
        graph_dir=graph_dir,
        force_rebuild=force
    )

    if not result["success"]:
        console.print(f"[red]❌ graphify 执行失败:[/red]")
        console.print(f"   {result['error']}")
        raise click.Abort()

    console.print("   ✓ graphify 执行成功")
    if result["output"]:
        console.print(f"   输出: {result['output'][:200]}...")

    # Step 4: 获取图谱统计
    console.print("[yellow]4. 统计图谱信息...[/yellow]")
    stats = get_graph_stats(graph_dir)
    console.print(f"   生成文件: {len(stats['files'])} 个")
    if stats['files']:
        console.print(f"   文件列表: {', '.join(stats['files'][:5])}")

    # Step 5: 更新 manifest 和 registry
    console.print("[yellow]5. 更新论文状态...[/yellow]")
    if not incremental:
        registry = PaperRegistry(registry_path)
    updated_count = 0
    now = datetime.now(UTC).isoformat() + "Z"

    for paper in normalized_papers:
        storage_id = paper["storage_id"]
        paper_id = paper["paper_id"]

        # 更新 manifest
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        if paths.manifest_json.exists():
            manifest = load_manifest(paths.manifest_json)
            manifest.state = PaperState.GRAPHED

            # 记录图谱化时的内容 SHA256
            content_sha256 = manifest.canonical_md.sha256 if manifest.canonical_md else None

            manifest.graph = GraphInfo(
                indexed=True,
                updated_at=now,
                content_sha256_at_index=content_sha256
            )
            save_manifest(manifest, paths.manifest_json)

        # 更新 registry
        if not incremental:
            registry.update_state(paper_id, PaperState.GRAPHED)
        updated_count += 1

    if not incremental:
        registry.close()
    console.print(f"   ✓ 更新了 {updated_count} 篇论文")

    console.print(f"\n[green]✅ 知识图谱更新完成![/green]")
    console.print(f"   图谱目录: {graph_dir}")
    console.print(f"   已图谱化论文: {updated_count} 篇")


@graph.command()
@click.pass_context
def status(ctx):
    """查看图谱状态"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"

    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在[/yellow]")
        return

    stats = get_graph_stats(graph_dir)
    console.print(f"[cyan]图谱状态:[/cyan]")
    console.print(f"  目录: {graph_dir}")
    console.print(f"  文件数: {len(stats['files'])}")
    if stats['files']:
        console.print(f"  文件列表:")
        for f in stats['files']:
            console.print(f"    - {f}")


@graph.command()
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="输出文件路径（默认: graph/entities.jsonl）"
)
@click.pass_context
def build_entities(ctx, output: str | None):
    """构建实体图谱（从 paper.md 的 entities 字段）"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]开始构建实体图谱...[/cyan]")

    # Step 1: 设置输出路径
    if output:
        output_path = Path(output)
    else:
        output_path = base_dir / "graph" / "entities.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 2: 提取实体
    console.print("[yellow]1. 提取论文实体...[/yellow]")
    library_dir = base_dir / "library"

    if not library_dir.exists():
        console.print("[red]❌ library 目录不存在[/red]")
        raise click.Abort()

    builder = EntityGraphBuilder(base_dir=base_dir)
    entities_dict = builder.extract_all_entities(library_dir)

    console.print(f"   ✓ 从 {len(entities_dict)} 篇论文提取实体")

    if not entities_dict:
        console.print("[yellow]⚠ 没有找到包含 entities 的论文[/yellow]")
        return

    # Step 3: 生成节点
    console.print("[yellow]2. 生成实体节点...[/yellow]")
    nodes = builder.build_entity_nodes(entities_dict)
    console.print(f"   ✓ 生成 {len(nodes)} 个唯一实体节点")

    # Step 4: 生成边
    console.print("[yellow]3. 生成关系边...[/yellow]")
    edges = builder.build_entity_edges(entities_dict)
    console.print(f"   ✓ 生成 {len(edges)} 条关系边")

    # Step 5: 导出 JSONL
    console.print("[yellow]4. 导出 JSONL...[/yellow]")
    builder.export_to_jsonl(nodes, edges, output_path)
    console.print(f"   ✓ 已导出到 {output_path}")

    # 统计信息
    console.print(f"\n[green]✅ 实体图谱构建完成![/green]")
    console.print(f"   输出文件: {output_path}")
    console.print(f"   节点数: {len(nodes)}")
    console.print(f"   边数: {len(edges)}")
    console.print(f"   总对象数: {len(nodes) + len(edges)}")

    # 显示实体类别分布
    category_stats = {}
    for node in nodes:
        category = node["category"]
        category_stats[category] = category_stats.get(category, 0) + 1

    console.print(f"\n   实体类别分布:")
    for category, count in sorted(category_stats.items()):
        console.print(f"     - {category}: {count}")
