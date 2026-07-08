"""query 命令实现"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.graph_query import find_related_papers, find_papers_by_topic, find_papers_by_entity
from paperbase.core.registry import PaperRegistry


@click.group()
def query():
    """图谱查询论文"""
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

    # 执行查询
    try:
        related_papers = find_related_papers(graph_dir, paper_id, depth)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        return

    if not related_papers:
        console.print(f"[yellow]未找到与 {paper_id} 相关的论文[/yellow]")
        return

    # 获取论文元数据
    registry = PaperRegistry(registry_path)

    table = Table(title=f"相关论文: {paper_id} (depth={depth})")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    for pid in related_papers:
        paper = registry.get_paper(pid)

        if paper:
            title = paper["title"] if paper["title"] else "N/A"
            authors = paper["authors"] if paper["authors"] else "N/A"
            year = str(paper["year"]) if paper["year"] else "N/A"

            # 截断过长的 title
            if len(title) > 50:
                title = title[:47] + "..."

            # 截断过长的 authors
            if len(authors) > 25:
                authors = authors[:22] + "..."

            table.add_row(pid, title, authors, year)
        else:
            # 论文不在 registry 中
            table.add_row(pid, "[dim]N/A[/dim]", "[dim]N/A[/dim]", "[dim]N/A[/dim]")

    console.print(table)
    console.print(f"\n[dim]找到 {len(related_papers)} 个相关论文[/dim]")

    registry.close()


@query.command()
@click.argument("topic")
@click.pass_context
def topic(ctx, topic: str):
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

    # 执行查询
    try:
        matched_papers = find_papers_by_topic(graph_dir, topic)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        return

    if not matched_papers:
        console.print(f"[yellow]未找到主题为 '{topic}' 的论文[/yellow]")
        return

    # 获取论文元数据
    registry = PaperRegistry(registry_path)

    table = Table(title=f"主题查询: {topic}")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    for pid in matched_papers:
        paper = registry.get_paper(pid)

        if paper:
            title = paper["title"] if paper["title"] else "N/A"
            authors = paper["authors"] if paper["authors"] else "N/A"
            year = str(paper["year"]) if paper["year"] else "N/A"

            # 截断过长的 title
            if len(title) > 50:
                title = title[:47] + "..."

            # 截断过长的 authors
            if len(authors) > 25:
                authors = authors[:22] + "..."

            table.add_row(pid, title, authors, year)
        else:
            # 论文不在 registry 中
            table.add_row(pid, "[dim]N/A[/dim]", "[dim]N/A[/dim]", "[dim]N/A[/dim]")

    console.print(table)
    console.print(f"\n[dim]找到 {len(matched_papers)} 个论文[/dim]")

    registry.close()


@query.command()
@click.argument("entity_filter")
@click.pass_context
def entity(ctx, entity_filter: str):
    """按关键信息查找论文

    ENTITY_FILTER 格式: category:name

    示例:
      paperbase query entity "methods:SLAM"
      paperbase query entity "datasets:ImageNet"
      paperbase query entity "domains:AUV navigation"
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查 graph 目录是否存在
    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查图谱文件是否存在
    entities_file = graph_dir / "entities.jsonl"
    graph_file = graph_dir / "graph.json"

    if not entities_file.exists() and not graph_file.exists():
        console.print("[yellow]图谱文件不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 执行查询
    try:
        matched_papers = find_papers_by_entity(graph_dir, entity_filter)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        return

    if not matched_papers:
        console.print(f"[yellow]未找到包含 '{entity_filter}' 的论文[/yellow]")
        return

    # 获取论文元数据
    registry = PaperRegistry(registry_path)

    table = Table(title=f"关键信息查询: {entity_filter}")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    for pid in matched_papers:
        paper = registry.get_paper(pid)

        if paper:
            title = paper["title"] if paper["title"] else "N/A"
            authors = paper["authors"] if paper["authors"] else "N/A"
            year = str(paper["year"]) if paper["year"] else "N/A"

            # 截断过长的 title
            if len(title) > 50:
                title = title[:47] + "..."

            # 截断过长的 authors
            if len(authors) > 25:
                authors = authors[:22] + "..."

            table.add_row(pid, title, authors, year)
        else:
            # 论文不在 registry 中
            table.add_row(pid, "[dim]N/A[/dim]", "[dim]N/A[/dim]", "[dim]N/A[/dim]")

    console.print(table)
    console.print(f"\n[dim]找到 {len(matched_papers)} 个论文[/dim]")

    registry.close()
