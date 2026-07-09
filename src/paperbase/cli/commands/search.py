"""search 命令实现"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.search_engine import SearchEngine
from paperbase.core.registry import PaperRegistry


@click.command()
@click.argument("query")
@click.option(
    "--limit",
    "-n",
    type=int,
    default=10,
    help="返回结果数量限制"
)
@click.pass_context
def search(ctx, query: str, limit: int):
    """全文检索论文内容"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    index_path = base_dir / "index" / "fts.db"
    library_path = base_dir / "library" / "papers"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查索引是否存在
    if not index_path.exists():
        console.print("[yellow]搜索索引不存在，需要构建索引[/yellow]")
        console.print("提示: 索引功能即将推出，当前可使用 'paperbase status' 查看所有论文")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 执行搜索
    engine = SearchEngine(index_path, library_path)
    results = engine.search(query, limit)
    engine.close()

    if not results:
        console.print(f"[yellow]未找到匹配结果: {query}[/yellow]")
        return

    # 获取论文元数据
    registry = PaperRegistry(registry_path)

    table = Table(title=f"搜索结果: {query}")
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=50)
    table.add_column("Snippet", style="dim", width=70)

    for result in results:
        paper = registry.get_paper(result["paper_id"])
        title = paper["title"] if paper and paper["title"] else "N/A"

        # 截断过长的 title 和 snippet
        if len(title) > 40:
            title = title[:37] + "..."

        snippet = result["snippet"]
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."

        table.add_row(
            f"{result['score']:.2f}",
            result["paper_id"],
            title,
            snippet
        )

    console.print(table)
    console.print(f"\n[dim]找到 {len(results)} 个结果[/dim]")

    registry.close()
