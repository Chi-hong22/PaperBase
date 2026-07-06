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
@click.pass_context
def update(ctx, force: bool):
    """更新知识图谱"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]开始更新知识图谱...[/cyan]")

    # Step 1: 检查 graphify 是否安装
    console.print("[yellow]1. 检查 graphify 安装...[/yellow]")
    if not check_graphify_installed():
        console.print("[red]❌ graphify 未安装[/red]")
        console.print("   请运行: [cyan]uv tool install graphify[/cyan]")
        raise click.Abort()

    console.print("   ✓ graphify 已安装")

    # Step 2: 检查是否有 NORMALIZED 论文
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
            manifest.graph = GraphInfo(
                indexed=True,
                updated_at=now
            )
            save_manifest(manifest, paths.manifest_json)

        # 更新 registry
        registry.update_state(paper_id, PaperState.GRAPHED)
        updated_count += 1

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
