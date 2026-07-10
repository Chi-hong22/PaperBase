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
@click.option(
    "--paper-id",
    type=str,
    default=None,
    help="只在指定论文中搜索（可选）"
)
@click.option(
    "--year",
    type=str,
    default=None,
    help="年份过滤（如 '2023' 或 '2020-2024'）"
)
@click.option(
    "--author",
    type=str,
    default=None,
    help="作者模糊匹配（如 'Smith'）"
)
@click.pass_context
def search(ctx, query: str, limit: int, paper_id: str, year: str, author: str):
    """全文检索论文内容

    支持全局搜索或在单篇论文中搜索，可通过年份和作者过滤。

    示例：

      paperbase search "threshold"                           # 全局搜索
      paperbase search "threshold" --paper-id doi:xxx         # 在指定论文中搜索
      paperbase search "SLAM" --year 2020-2024               # 年份范围过滤
      paperbase search "SLAM" --year 2023                    # 单一年份
      paperbase search "neural" --author "Smith"             # 作者过滤
      paperbase search "SLAM" --year 2020-2024 --author "Li" # 组合过滤
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    index_path = base_dir / "index" / "fts.db"
    library_path = base_dir / "library" / "papers"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查索引是否存在
    if not index_path.exists():
        console.print("[yellow]搜索索引不存在，需要先构建索引[/yellow]")
        console.print("提示: 使用 'paperbase index' 命令构建索引")
        return

    # 检查 registry 是否存在（如果使用元数据过滤）
    if (year or author) and not registry_path.exists():
        console.print("[yellow]Registry 不存在，无法使用元数据过滤[/yellow]")
        console.print("提示: 请先摄入论文")
        return

    # 解析年份范围
    year_range = None
    if year:
        year_range = _parse_year_range(year)
        if not year_range:
            console.print(f"[red]无效的年份格式: {year}[/red]")
            console.print("支持格式：'2023' 或 '2020-2024'")
            return

    # 执行搜索
    engine = SearchEngine(index_path, library_path)
    results = engine.search(
        query,
        limit,
        paper_id_filter=paper_id,
        year_range=year_range,
        author_filter=author
    )
    engine.close()

    if not results:
        filters = []
        if paper_id:
            filters.append(f"论文: {paper_id}")
        if year:
            filters.append(f"年份: {year}")
        if author:
            filters.append(f"作者: {author}")

        filter_desc = f" ({', '.join(filters)})" if filters else ""
        console.print(f"[yellow]未找到匹配结果{filter_desc}: {query}[/yellow]")
        return

    # 获取论文元数据
    registry = PaperRegistry(registry_path)

    # 构建搜索范围描述
    filters = []
    if paper_id:
        filters.append(f"论文: {paper_id}")
    if year:
        filters.append(f"年份: {year}")
    if author:
        filters.append(f"作者: {author}")

    filter_desc = f" ({', '.join(filters)})" if filters else ""
    table = Table(title=f"搜索结果: {query}{filter_desc}")
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


def _parse_year_range(year_str: str) -> tuple:
    """
    解析年份范围

    Args:
        year_str: 年份字符串（如 '2023' 或 '2020-2024'）

    Returns:
        tuple: (start_year, end_year) 或 None（解析失败）
    """
    year_str = year_str.strip()

    # 单一年份
    if year_str.isdigit():
        year = int(year_str)
        return (year, year)

    # 年份范围
    if "-" in year_str:
        parts = year_str.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start_year = int(parts[0])
            end_year = int(parts[1])
            if start_year <= end_year:
                return (start_year, end_year)

    return None
