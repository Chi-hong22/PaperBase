"""graph 命令实现"""

import click
from rich.console import Console
from pathlib import Path
from paperbase.utils.timestamp import now_iso8601
from paperbase.adapters.graphify_adapter import (
    check_graphify_installed,
    run_graphify,
    adopt_graphify_output,
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

    # Step 1.5: 手动 CLI 模式才读取 PaperBase 的本地 LLM 配置。
    llm_config, process_timeout, api_timeout = _load_headless_graphify_config()

    # Step 2: 检测需要更新的论文
    normalized_papers = _papers_to_index(base_dir, incremental=incremental)
    if incremental:
        if not normalized_papers:
            console.print("[green]✓ 索引已是最新[/green]")
            return
        console.print(f"检测到 {len(normalized_papers)} 篇论文有更新")
    else:
        console.print(f"待索引: {len(normalized_papers)} 篇")

    # Step 3: 构建索引
    console.print("[dim]正在构建论文关联...[/dim]")
    library_dir = base_dir / "library"
    graph_dir = base_dir / "graph"

    result = run_graphify(
        library_dir=library_dir,
        graph_dir=graph_dir,
        force_rebuild=force,
        llm_config=llm_config,
        process_timeout=process_timeout,
        api_timeout=api_timeout,
    )

    if not result["success"]:
        console.print(f"[red]graphify 失败: {result['error']}[/red]")
        console.print("提示: 检查网络配置和 LLM API 设置")
        raise click.Abort()

    # Step 4: 更新状态
    stats = get_graph_stats(graph_dir)
    updated_count = _project_index_state(base_dir, normalized_papers)

    console.print(f"[green]✓ 索引更新完成[/green]")
    console.print(f"   已索引: {updated_count} 篇论文")
    console.print(f"   索引文件: {len(stats['files'])} 个")


@graph.command()
@click.option(
    "--force",
    is_flag=True,
    help="将 Agent 生成的完整图谱投影到 PaperBase，并标记所有 NORMALIZED 论文",
)
@click.option(
    "--incremental",
    is_flag=True,
    help="只标记内容发生变化的论文（默认行为）",
)
@click.pass_context
def adopt(ctx, force: bool, incremental: bool):
    """接纳 Graphify Agent 已生成的 graphify-out，不调用本地 LLM。"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    if force and incremental:
        console.print("[red]--force 和 --incremental 不能同时使用[/red]")
        raise click.Abort()

    normalized_papers = _papers_to_index(
        base_dir,
        incremental=not force,
    )
    if not normalized_papers:
        console.print("[green]✓ 没有需要接纳的论文状态变化[/green]")
        return

    result = adopt_graphify_output(
        library_dir=base_dir / "library",
        graph_dir=base_dir / "graph",
    )
    if not result["success"]:
        console.print(f"[red]Graphify 输出接纳失败: {result['error']}[/red]")
        raise click.Abort()

    updated_count = _project_index_state(base_dir, normalized_papers)
    stats = get_graph_stats(base_dir / "graph")
    console.print("[green]✓ 已接纳 Graphify Agent 图谱[/green]")
    console.print(f"   已索引: {updated_count} 篇论文")
    console.print(f"   节点: {stats['nodes']}，边: {stats['edges']}")


def _load_headless_graphify_config() -> tuple[dict | None, float | None, float | None]:
    """读取手动 headless Graphify 所需的本地 LLM 和超时配置。"""
    from paperbase.config.loader import load_config

    try:
        config = load_config()
    except Exception:
        return None, None, None

    llm_config = {
        "api_key": config.llm.api_key,
        "base_url": config.llm.base_url,
        "model": config.llm.model,
    } if config.llm.is_enabled() else None
    return (
        llm_config,
        config.graph.get_process_timeout(),
        config.graph.get_api_timeout(),
    )


def _papers_to_index(base_dir: Path, *, incremental: bool) -> list[dict]:
    """返回需要在本次图谱状态投影中标记的论文。"""
    papers_path = base_dir / "library" / "papers"
    if incremental:
        return detect_changed_papers(papers_path)

    registry_path = base_dir / "registry" / "papers.db"
    if not registry_path.exists():
        raise click.ClickException("知识库为空，请先添加论文")

    with PaperRegistry(registry_path) as registry:
        return registry.list_papers(state=PaperState.NORMALIZED)


def _project_index_state(base_dir: Path, papers: list[dict]) -> int:
    """将已生成的图谱状态写回 manifest 和 Registry。"""
    now = now_iso8601()
    registry_path = base_dir / "registry" / "papers.db"
    updated_count = 0

    with PaperRegistry(registry_path) as registry:
        for paper in papers:
            paths = PaperPaths(storage_id=paper["storage_id"], base_dir=base_dir)
            if not paths.manifest_json.exists():
                continue

            manifest = load_manifest(paths.manifest_json)
            content_sha256 = manifest.canonical_md.sha256 if manifest.canonical_md else None
            manifest.graph = GraphInfo(
                indexed=True,
                updated_at=now,
                content_sha256_at_index=content_sha256,
            )
            manifest.state = PaperState.READY
            save_manifest(manifest, paths.manifest_json)
            registry.update_state(paper["paper_id"], PaperState.READY)
            updated_count += 1

    return updated_count


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

