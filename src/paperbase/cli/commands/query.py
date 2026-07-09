"""query 命令实现

CLI 高级用户参数化查询接口。

与 /paperbase skill 的区别：
- query CLI: 显式子命令 + 参数控制（如 --depth），适合终端手动操作
- /paperbase skill: 自动路由 + 自然语言，适合 AI Agent 工作流
"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.graph_query import find_related_papers, find_papers_by_topic
from paperbase.core.registry import PaperRegistry


@click.group()
def query():
    """图谱查询论文（高级用户参数化控制）

    AI Agent 请使用 /paperbase skill 进行自然语言查询。
    """
    pass


@query.command()
@click.argument("paper_id")
@click.option(
    "--depth",
    "-d",
    type=int,
    default=1,
    help="遍历深度（1=直接相关，2=二度相关）"
)
@click.pass_context
def related(ctx, paper_id: str, depth: int):
    """查找相关论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查 graph 目录是否存在
    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 graph.json 是否存在
    graph_file = graph_dir / "graph.json"
    if not graph_file.exists():
        console.print("[yellow]图谱文件不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 将 paper_id 转换为 storage_id
    registry = PaperRegistry(registry_path)
    paper_info = registry.get_paper(paper_id)

    if not paper_info:
        console.print(f"[red]未找到论文: {paper_id}[/red]")
        registry.close()
        return

    storage_id = paper_info["storage_id"]

    # 执行查询（使用 storage_id）
    try:
        related_storage_ids = find_related_papers(graph_dir, storage_id, depth)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        registry.close()
        return

    if not related_storage_ids:
        console.print(f"[yellow]未找到与 {paper_id} 相关的论文[/yellow]")
        registry.close()
        return

    # 将 storage_id 转换回 paper_id 并获取元数据
    table = Table(title=f"相关论文: {paper_id} (depth={depth})")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    for sid in related_storage_ids:
        # 通过 storage_id 查找 paper
        papers = registry.list_papers()
        paper = next((p for p in papers if p["storage_id"] == sid), None)

        if paper:
            pid = paper["paper_id"]
            title = paper["title"] if paper["title"] else "N/A"
            authors = paper["authors"] if paper["authors"] else []
            year = str(paper["year"]) if paper["year"] else "N/A"

            # 截断过长的 title
            if len(title) > 50:
                title = title[:47] + "..."

            # 转换 authors list 为字符串并截断
            if isinstance(authors, list):
                authors = ", ".join(authors)
            if len(authors) > 25:
                authors = authors[:22] + "..."

            table.add_row(pid, title, authors, year)
        else:
            # storage_id 不在 registry 中
            table.add_row(sid, "[dim]N/A[/dim]", "[dim]N/A[/dim]", "[dim]N/A[/dim]")

    console.print(table)
    console.print(f"\n[dim]找到 {len(related_storage_ids)} 个相关论文[/dim]")

    registry.close()


@query.command()
@click.argument("topic")
@click.option("--include-refs", is_flag=True, help="包含引用文献")
@click.pass_context
def topic(ctx, topic: str, include_refs: bool):
    """按主题查找论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查 graph 目录是否存在
    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 graph.json 是否存在
    graph_file = graph_dir / "graph.json"
    if not graph_file.exists():
        console.print("[yellow]图谱文件不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 执行查询（返回 node_id 列表）
    try:
        matched_node_ids = find_papers_by_topic(graph_dir, topic, include_refs)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        return

    if not matched_node_ids:
        console.print(f"[yellow]未找到主题为 '{topic}' 的论文[/yellow]")
        return

    # 将 node_id 转换为 paper_id 并获取元数据
    registry = PaperRegistry(registry_path)
    papers = registry.list_papers()

    # 分离本地论文和引用文献
    local_papers = []
    ref_papers = []

    for nid in matched_node_ids:
        # 判断是否为标准节点（本地论文）
        import re
        is_local = re.match(r'^p_[0-9a-f]{12}$', nid)

        if is_local:
            # 本地论文：从 registry 查找
            paper = next((p for p in papers if p["storage_id"] == nid), None)
            if paper:
                local_papers.append({
                    "id": paper["paper_id"],
                    "title": paper["title"] or "N/A",
                    "authors": paper["authors"] or [],
                    "year": str(paper["year"]) if paper["year"] else "N/A",
                    "type": "本地"
                })
        else:
            # 引用文献：从 graph.json 提取标签作为标题
            # 提取 storage_id 前缀（用于显示来源）
            storage_prefix = nid.split('_')[0] + '_' + nid.split('_')[1] if '_' in nid else nid
            source_paper = next((p for p in papers if p["storage_id"] == storage_prefix), None)
            source_info = f"引用自: {source_paper['title'][:20]}..." if source_paper else "引用文献"

            # 从节点标签提取标题（需要重新加载图谱）
            import json
            graph_file = graph_dir / "graph.json"
            with open(graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            node = next((n for n in graph_data.get("nodes", []) if n.get("id") == nid), None)
            ref_title = node.get("label", "N/A") if node else "N/A"

            ref_papers.append({
                "id": nid,
                "title": ref_title,
                "authors": source_info,  # 复用 authors 列显示来源
                "year": "N/A",
                "type": "引用"
            })

    # 构建表格
    table = Table(title=f"主题查询: {topic}")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    # 先显示本地论文
    for paper in local_papers:
        pid = paper["id"]
        title = paper["title"]
        authors = paper["authors"]
        year = paper["year"]

        # 截断过长的 title
        if len(title) > 50:
            title = title[:47] + "..."

        # 转换 authors list 为字符串并截断
        if isinstance(authors, list):
            authors = ", ".join(authors)
        if len(authors) > 25:
            authors = authors[:22] + "..."

        table.add_row(pid, title, authors, year)

    # 再显示引用文献（如果有）
    if ref_papers:
        # 添加分隔行
        if local_papers:
            table.add_row("", "[dim]--- 引用文献 ---[/dim]", "", "")

        for ref in ref_papers:
            nid = ref["id"]
            title = ref["title"]
            source = ref["authors"]  # 来源信息

            # 截断
            if len(nid) > 25:
                nid = nid[:22] + "..."
            if len(title) > 50:
                title = title[:47] + "..."
            if len(source) > 25:
                source = source[:22] + "..."

            table.add_row(f"[dim]{nid}[/dim]", f"[dim]{title}[/dim]", f"[dim]{source}[/dim]", "[dim]N/A[/dim]")

    console.print(table)

    # 统计信息
    if include_refs:
        console.print(f"\n[dim]本地论文: {len(local_papers)} 篇, 引用文献: {len(ref_papers)} 篇[/dim]")
    else:
        console.print(f"\n[dim]找到 {len(local_papers)} 个论文[/dim]")

    registry.close()
