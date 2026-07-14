"""graph 命令实现"""

import click
from rich.console import Console
from pathlib import Path
from paperbase.utils.timestamp import now_iso8601
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


@click.group()
def graph():
    """知识库索引管理"""
    pass


@graph.command()
@click.option(
    "--force",
    is_flag=True,
    help="强制重建索引（删除现有数据）"
)
@click.option(
    "--incremental",
    is_flag=True,
    help="仅更新内容发生变化的论文"
)
@click.pass_context
def update(ctx, force: bool, incremental: bool):
    """更新知识库索引"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]更新知识库索引...[/cyan]")

    # 互斥检查
    if force and incremental:
        console.print("[red]--force 和 --incremental 不能同时使用[/red]")
        raise click.Abort()

    # Step 1: 检查依赖
    if not check_graphify_installed():
        console.print("[red]缺少必要组件 graphify[/red]")
        console.print("   安装方法: [cyan]uv tool install graphify[/cyan]")
        raise click.Abort()

    # Step 1.5: 加载 PaperBase LLM 配置（用于传递给 graphify）
    from paperbase.config.loader import load_config
    try:
        config = load_config()
        llm_config = {
            "api_key": config.llm.api_key,
            "base_url": config.llm.base_url,
            "model": config.llm.model
        } if config.llm.is_enabled() else None
    except Exception:
        llm_config = None

    # Step 2: 检测需要更新的论文
    library_dir = base_dir / "library"
    if incremental:
        changed_papers = detect_changed_papers(library_dir)

        if not changed_papers:
            console.print("[green]✓ 索引已是最新[/green]")
            return

        console.print(f"检测到 {len(changed_papers)} 篇论文有更新")
        normalized_papers = changed_papers
    else:
        registry_path = base_dir / "registry" / "papers.db"
        if not registry_path.exists():
            console.print("[red]知识库为空，请先添加论文[/red]")
            raise click.Abort()

        registry = PaperRegistry(registry_path)
        normalized_papers = registry.list_papers(state=PaperState.NORMALIZED)
        all_papers = registry.list_papers()
        registry.close()

        console.print(f"待索引: {len(normalized_papers)} 篇，总计: {len(all_papers)} 篇")

    # Step 3: 构建索引
    console.print("[dim]正在构建论文关联...[/dim]")
    library_dir = base_dir / "library"
    graph_dir = base_dir / "graph"

    result = run_graphify(
        library_dir=library_dir,
        graph_dir=graph_dir,
        force_rebuild=force,
        llm_config=llm_config  # 传递 PaperBase 的 LLM 配置
    )

    if not result["success"]:
        console.print(f"[red]graphify 失败: {result['error']}[/red]")
        console.print("提示: 检查网络配置和 LLM API 设置")
        raise click.Abort()

    # Step 4: 更新状态
    stats = get_graph_stats(graph_dir)
    updated_count = 0
    now = now_iso8601()  # 使用统一的时间戳生成函数

    # 打开 registry（所有模式都需要）
    registry_path = base_dir / "registry" / "papers.db"
    registry = PaperRegistry(registry_path)

    try:
        for paper in normalized_papers:
            storage_id = paper["storage_id"]
            paper_id = paper["paper_id"]

            paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
            if paths.manifest_json.exists():
                manifest = load_manifest(paths.manifest_json)

                # 只处理 NORMALIZED 状态的论文
                if manifest.state == PaperState.NORMALIZED:
                    content_sha256 = manifest.canonical_md.sha256 if manifest.canonical_md else None

                    manifest.graph = GraphInfo(
                        indexed=True,
                        updated_at=now,
                        content_sha256_at_index=content_sha256
                    )

                    # 推进到 READY
                    manifest.state = PaperState.READY
                    save_manifest(manifest, paths.manifest_json)

                    # 更新 registry 状态（所有模式）
                    registry.update_state(paper_id, PaperState.READY)
                    updated_count += 1
    finally:
        registry.close()

    console.print(f"[green]✓ 索引更新完成[/green]")
    console.print(f"   已索引: {updated_count} 篇论文")
    console.print(f"   索引文件: {len(stats['files'])} 个")


@graph.command()
@click.pass_context
def status(ctx):
    """查看索引状态"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"

    if not graph_dir.exists():
        console.print("[yellow]索引尚未创建[/yellow]")
        return

    stats = get_graph_stats(graph_dir)
    console.print(f"[cyan]索引状态[/cyan]")
    console.print(f"  位置: {graph_dir}")
    console.print(f"  索引文件: {len(stats['files'])} 个")
    console.print(f"  节点: {stats['nodes']}")
    console.print(f"  边: {stats['edges']}")
    if stats['files']:
        console.print(f"  详细:")
        for f in stats['files']:
            console.print(f"    - {f}")

