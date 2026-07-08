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
        console.print(f"[yellow]graphify 失败: {result['error']}[/yellow]")
        console.print("[dim]尝试使用备用方案（EntityGraphBuilder）...[/dim]")

        # 降级到 EntityGraphBuilder
        builder = EntityGraphBuilder(base_dir=base_dir)
        entities_dict = builder.extract_all_entities(library_dir)

        if not entities_dict:
            console.print("[red]备用方案也失败：没有找到已提取的实体[/red]")
            console.print("提示: 先运行 [cyan]paperbase extract --all[/cyan] 提取实体")
            raise click.Abort()

        # 构建简化图谱
        nodes = builder.build_entity_nodes(entities_dict)
        edges = builder.build_entity_edges(entities_dict)
        output_path = graph_dir / "entities.jsonl"
        builder.export_to_jsonl(nodes, edges, output_path)

        console.print(f"[green]✓ 已使用备用方案构建关联图谱[/green]")
        console.print(f"   输出: {output_path}")
        console.print(f"   信息点: {len(nodes)} 个")
        console.print(f"   关联: {len(edges)} 条")
        console.print("[dim]提示: 修复网络配置后运行 'paperbase graph update --force' 获取完整语义图谱[/dim]")

        # 从 registry 获取所有论文（而不是只获取 normalized 状态的）
        registry_path = base_dir / "registry" / "papers.db"
        registry = PaperRegistry(registry_path)
        # 获取所有在 entities_dict 中的论文
        all_papers = registry.list_papers()
        normalized_papers = [p for p in all_papers if p["paper_id"] in entities_dict]
        registry.close()

    # Step 4: 更新状态
    stats = get_graph_stats(graph_dir)
    updated_count = 0
    now = datetime.now(UTC).isoformat() + "Z"

    if not incremental:
        registry = PaperRegistry(registry_path)

    try:
        for paper in normalized_papers:
            storage_id = paper["storage_id"]
            paper_id = paper["paper_id"]

            paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
            if paths.manifest_json.exists():
                manifest = load_manifest(paths.manifest_json)

                # 只处理 NORMALIZED 或 VALIDATED 状态的论文
                if manifest.state in [PaperState.NORMALIZED, PaperState.VALIDATED]:
                    content_sha256 = manifest.canonical_md.sha256 if manifest.canonical_md else None

                    manifest.graph = GraphInfo(
                        indexed=True,
                        updated_at=now,
                        content_sha256_at_index=content_sha256
                    )

                    # 推进到 READY
                    manifest.state = PaperState.READY
                    save_manifest(manifest, paths.manifest_json)

                    if not incremental:
                        registry.update_state(paper_id, PaperState.READY)
                    updated_count += 1
    finally:
        if not incremental:
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
    if stats['files']:
        console.print(f"  详细:")
        for f in stats['files']:
            console.print(f"    - {f}")


@graph.command()
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="输出文件路径（默认: graph/entities.jsonl）"
)
@click.option(
    "--no-state-update",
    is_flag=True,
    help="不更新论文状态"
)
@click.pass_context
def build_entities(ctx, output: str | None, no_state_update: bool):
    """构建关键信息关联图谱"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]构建关键信息关联...[/cyan]")

    # Step 1: 设置输出路径
    if output:
        output_path = Path(output)
    else:
        output_path = base_dir / "graph" / "entities.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 2: 收集信息
    library_dir = base_dir / "library"

    if not library_dir.exists():
        console.print("[red]知识库为空[/red]")
        raise click.Abort()

    builder = EntityGraphBuilder(base_dir=base_dir)
    entities_dict = builder.extract_all_entities(library_dir)

    if not entities_dict:
        console.print("[yellow]没有找到已分析的论文[/yellow]")
        console.print("提示: 先运行 [cyan]paperbase extract --all[/cyan] 分析论文内容")
        return

    console.print(f"收集了 {len(entities_dict)} 篇论文的信息")

    # Step 3: 构建关联
    nodes = builder.build_entity_nodes(entities_dict)
    edges = builder.build_entity_edges(entities_dict)

    # Step 4: 导出
    builder.export_to_jsonl(nodes, edges, output_path)

    # 统计信息
    console.print(f"[green]✓ 关联图谱已生成[/green]")
    console.print(f"   输出: {output_path}")
    console.print(f"   信息点: {len(nodes)} 个")
    console.print(f"   关联: {len(edges)} 条")

    # 显示类别分布
    category_stats = {}
    for node in nodes:
        category = node["category"]
        category_stats[category] = category_stats.get(category, 0) + 1

    if category_stats:
        console.print(f"\n   信息类别:")
        for category, count in sorted(category_stats.items()):
            console.print(f"     - {category}: {count}")

    # Step 5: 更新论文状态（如果启用）
    if not no_state_update:
        from datetime import datetime, UTC

        registry_path = base_dir / "registry" / "papers.db"
        if registry_path.exists():
            registry = PaperRegistry(registry_path)
            updated_count = 0
            now = datetime.now(UTC).isoformat() + "Z"

            try:
                # 更新所有参与图谱的论文状态
                for paper_id in entities_dict.keys():
                    paper = registry.get_paper(paper_id)
                    if paper:
                        storage_id = paper["storage_id"]
                        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)

                        if paths.manifest_json.exists():
                            manifest = load_manifest(paths.manifest_json)

                            # 只处理 NORMALIZED 或 VALIDATED 状态的论文
                            if manifest.state in [PaperState.NORMALIZED, PaperState.VALIDATED]:
                                manifest.graph = GraphInfo(
                                    indexed=True,
                                    updated_at=now,
                                    content_sha256_at_index=manifest.canonical_md.sha256 if manifest.canonical_md else None
                                )

                                # 推进到 READY
                                manifest.state = PaperState.READY
                                save_manifest(manifest, paths.manifest_json)

                                # 更新 registry
                                registry.update_state(paper_id, PaperState.READY)
                                updated_count += 1

                if updated_count > 0:
                    console.print(f"\n[green]✓ 已更新 {updated_count} 篇论文状态为 ready[/green]")
            finally:
                registry.close()
