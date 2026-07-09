"""status 命令实现"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.registry import PaperRegistry


@click.command()
@click.argument("paper_id", required=False)
@click.option("--year", type=int, help="按年份过滤")
@click.option("--state", type=str, help="按状态过滤（raw/normalized/ready）")
@click.pass_context
def status(ctx, paper_id: str | None, year: int | None, state: str | None):
    """查询论文状态"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    registry_path = base_dir / "registry" / "papers.db"

    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    registry = PaperRegistry(registry_path)

    if paper_id:
        # 查询单篇
        paper = registry.get_paper(paper_id)
        if paper:
            console.print(f"[bold]Paper ID:[/bold] {paper['paper_id']}")
            console.print(f"[bold]Storage ID:[/bold] {paper['storage_id']}")
            console.print(f"[bold]State:[/bold] {paper['state']}")
            console.print(f"[bold]Title:[/bold] {paper['title']}")
            console.print(f"[bold]Year:[/bold] {paper['year']}")
        else:
            console.print(f"[red]未找到论文: {paper_id}[/red]")
    else:
        # 列出所有
        papers = registry.list_papers()
        if not papers:
            console.print("[yellow]知识库为空[/yellow]")
            return

        # 应用过滤条件
        if year is not None:
            papers = [p for p in papers if p.get("year") == year]
        if state is not None:
            papers = [p for p in papers if p.get("state") == state]

        if not papers:
            console.print("[yellow]未找到符合条件的论文[/yellow]")
            return

        table = Table(title="PaperBase 论文列表")
        table.add_column("Paper ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Year", style="magenta")
        table.add_column("State", style="green")

        for paper in papers[:20]:  # 限制 20 条
            table.add_row(
                paper["paper_id"],
                paper["title"] or "N/A",
                str(paper["year"]) if paper["year"] else "N/A",
                paper["state"]
            )

        console.print(table)
        if len(papers) > 20:
            console.print(f"\n[dim]... 还有 {len(papers) - 20} 篇论文[/dim]")

    registry.close()
