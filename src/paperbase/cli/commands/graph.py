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
from paperbase.utils.markdown import parse_frontmatter


@click.group()
def graph():
    """知识库索引管理"""
    pass


@graph.command()
@click.option(
    "--force",
    is_flag=True,
    help="检查全部论文，而不只检查内容发生变化的论文",
)
@click.pass_context
def preflight(ctx, force: bool):
    """预检 Canonical Markdown，报告可建图和需要审核的论文。"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    papers = _papers_to_index(
        base_dir,
        incremental=not force,
        include_all=force,
        include_review=not force,
    )
    graphable, blocked = _partition_graphable_papers(base_dir, papers)

    console.print("[cyan]图谱预检[/cyan]")
    console.print(f"  可建图: {len(graphable)}")
    console.print(f"  需审核: {len(blocked)}")
    for paper, reason in blocked:
        console.print(f"  [yellow]- {paper['storage_id']}: {reason}[/yellow]")


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
    llm_config, process_timeout, api_timeout = _load_headless_graphify_config(base_dir)

    # Step 2: 检测需要更新的论文
    normalized_papers = _papers_to_index(
        base_dir,
        incremental=incremental,
        include_all=force,
    )
    if incremental:
        if not normalized_papers:
            console.print("[green]✓ 索引已是最新[/green]")
            return
        console.print(f"检测到 {len(normalized_papers)} 篇论文有更新")
    else:
        console.print(f"待索引: {len(normalized_papers)} 篇")

    graphable_papers, blocked_papers = _partition_graphable_papers(
        base_dir,
        normalized_papers,
    )
    existing_review_papers = _list_review_papers(base_dir)
    blocked_ids = {paper["storage_id"] for paper, _reason in blocked_papers}
    blocked_papers.extend(
        (paper, "已有 NEEDS_REVIEW，Canonical 尚未修改")
        for paper in existing_review_papers
        if paper["storage_id"] not in blocked_ids
    )
    if blocked_papers:
        review_count = _project_review_state(base_dir, blocked_papers)
        console.print(
            f"[yellow]预检发现 {review_count} 篇论文需要审核，"
            "本轮已停止且未调用 Graphify；请先修复 Canonical Markdown 后重试[/yellow]"
        )
        raise click.Abort()

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
    review_count = _project_review_state(base_dir, blocked_papers)
    updated_count = _project_index_state(base_dir, graphable_papers)

    console.print(f"[green]✓ 索引更新完成[/green]")
    console.print(f"   已索引: {updated_count} 篇论文")
    console.print(f"   需审核: {review_count} 篇论文")
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
        include_all=force,
    )
    if not normalized_papers:
        console.print("[green]✓ 没有需要接纳的论文状态变化[/green]")
        return

    graphable_papers, blocked_papers = _partition_graphable_papers(
        base_dir,
        normalized_papers,
    )
    existing_review_papers = _list_review_papers(base_dir)
    blocked_ids = {paper["storage_id"] for paper, _reason in blocked_papers}
    blocked_papers.extend(
        (paper, "已有 NEEDS_REVIEW，Canonical 尚未修改")
        for paper in existing_review_papers
        if paper["storage_id"] not in blocked_ids
    )
    if blocked_papers:
        review_count = _project_review_state(base_dir, blocked_papers)
        console.print(
            f"[yellow]发现 {review_count} 篇论文需要审核，"
            "本次未接纳 Graphify 输出；请先修复 Canonical Markdown 后重试[/yellow]"
        )
        raise click.Abort()

    result = adopt_graphify_output(
        library_dir=base_dir / "library",
        graph_dir=base_dir / "graph",
    )
    if not result["success"]:
        console.print(f"[red]Graphify 输出接纳失败: {result['error']}[/red]")
        raise click.Abort()

    updated_count = _project_index_state(base_dir, graphable_papers)
    review_count = 0
    stats = get_graph_stats(base_dir / "graph")
    console.print("[green]✓ 已接纳 Graphify Agent 图谱[/green]")
    console.print(f"   已索引: {updated_count} 篇论文")
    console.print(f"   需审核: {review_count} 篇论文")
    console.print(f"   节点: {stats['nodes']}，边: {stats['edges']}")


def _load_headless_graphify_config(
    base_dir: Path,
) -> tuple[dict | None, float | None, float | None]:
    """读取手动 headless Graphify 所需的本地 LLM 和超时配置。"""
    from paperbase.config.loader import load_config

    try:
        config_path = base_dir / "config" / "paperbase.yaml"
        config = load_config(config_path)
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


def _papers_to_index(
    base_dir: Path,
    *,
    incremental: bool,
    include_all: bool = False,
    include_review: bool = False,
) -> list[dict]:
    """返回需要在本次图谱状态投影中标记的论文。"""
    papers_path = base_dir / "library" / "papers"
    if incremental and not include_all:
        changed = detect_changed_papers(papers_path)
        if not include_review:
            return changed
        by_storage_id = {paper["storage_id"]: paper for paper in changed}
        registry_path = base_dir / "registry" / "papers.db"
        if registry_path.exists():
            with PaperRegistry(registry_path) as registry:
                for paper in registry.list_papers(state=PaperState.NEEDS_REVIEW):
                    by_storage_id[paper["storage_id"]] = paper
        return list(by_storage_id.values())

    registry_path = base_dir / "registry" / "papers.db"
    if not registry_path.exists():
        raise click.ClickException("知识库为空，请先添加论文")

    with PaperRegistry(registry_path) as registry:
        if include_all:
            return registry.list_papers()
        return registry.list_papers(state=PaperState.NORMALIZED)


def _list_review_papers(base_dir: Path) -> list[dict]:
    """返回尚未修复的 NEEDS_REVIEW 论文，避免它们被再次送入 Graphify。"""
    registry_path = base_dir / "registry" / "papers.db"
    if not registry_path.exists():
        return []
    with PaperRegistry(registry_path) as registry:
        return registry.list_papers(state=PaperState.NEEDS_REVIEW)


def _partition_graphable_papers(
    base_dir: Path,
    papers: list[dict],
) -> tuple[list[dict], list[tuple[dict, str]]]:
    """按 Canonical 质量拆分可建图论文和需要人工修复的论文。"""
    try:
        from paperbase.config.loader import load_config

        config_path = base_dir / "config" / "paperbase.yaml"
        config = load_config(config_path)
        minimum_chars = config.graph.get_minimum_canonical_body_chars()
    except Exception:
        minimum_chars = 500

    graphable: list[dict] = []
    blocked: list[tuple[dict, str]] = []
    for paper in papers:
        paths = PaperPaths(storage_id=paper["storage_id"], base_dir=base_dir)
        reason = _inspect_canonical_for_graph(paths.paper_md, minimum_chars)
        if reason is None:
            graphable.append(paper)
        else:
            blocked.append((paper, reason))
    return graphable, blocked


def _inspect_canonical_for_graph(path: Path, minimum_chars: int) -> str | None:
    """返回阻塞原因；None 表示 Canonical Markdown 可进入图谱。"""
    if not path.exists():
        return "Canonical Markdown 不存在"

    try:
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"Canonical Markdown 无法解析: {exc}"

    body_metadata, body_text = _extract_embedded_metadata(body)
    if body_metadata.get("content_kind") in {"metadata_only", "abstract_only"}:
        return f"content_kind={body_metadata['content_kind']}"
    if body_metadata.get("has_fulltext") is False:
        return "has_fulltext=false"

    # 正文级 paper-fetch 标记比历史 frontmatter quality 更接近实际内容。
    embedded_fulltext = (
        body_metadata.get("content_kind") == "fulltext"
        or body_metadata.get("has_fulltext") is True
    )
    quality = metadata.get("quality") or {}
    if not embedded_fulltext:
        if quality.get("fulltext") is False:
            return "quality.fulltext=false"
        if quality.get("needs_review") is True:
            return "quality.needs_review=true"

    if len(body_text.strip()) < minimum_chars:
        return f"Canonical 正文不足 {minimum_chars} 字符"
    return None


def _extract_embedded_metadata(body: str) -> tuple[dict, str]:
    """解析 paper-fetch 写入的正文级质量块，不改变 Canonical 内容。"""
    stripped = body.lstrip()
    if not stripped.startswith("---\n"):
        return {}, body
    try:
        metadata, remainder = parse_frontmatter(stripped)
    except ValueError:
        return {}, body
    return metadata, remainder


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


def _project_review_state(
    base_dir: Path,
    blocked_papers: list[tuple[dict, str]],
) -> int:
    """将 Canonical 质量不足的论文明确置为 NEEDS_REVIEW。"""
    if not blocked_papers:
        return 0

    now = now_iso8601()
    registry_path = base_dir / "registry" / "papers.db"
    updated_count = 0
    with PaperRegistry(registry_path) as registry:
        for paper, _reason in blocked_papers:
            paths = PaperPaths(storage_id=paper["storage_id"], base_dir=base_dir)
            if not paths.manifest_json.exists():
                continue

            manifest = load_manifest(paths.manifest_json)
            content_sha256 = manifest.canonical_md.sha256 if manifest.canonical_md else None
            manifest.graph = GraphInfo(
                indexed=False,
                updated_at=now,
                content_sha256_at_index=content_sha256,
            )
            manifest.state = PaperState.NEEDS_REVIEW
            save_manifest(manifest, paths.manifest_json)
            registry.update_state(paper["paper_id"], PaperState.NEEDS_REVIEW)
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

