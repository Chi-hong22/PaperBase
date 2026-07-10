"""sync 命令实现 - 同步 Registry 与文件系统"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry


@click.command()
@click.option("--dry-run", is_flag=True, help="仅显示需要清理的记录，不执行删除")
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接删除")
@click.pass_context
def sync(ctx, dry_run: bool, yes: bool):
    """同步 Registry 与文件系统，清理孤立的索引记录

    检查 Registry 中的论文记录，如果对应的论文目录不存在，
    则标记为孤立记录并提供清理选项。
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    registry_path = base_dir / "registry" / "papers.db"
    if not registry_path.exists():
        console.print("[yellow]⚠️  Registry 不存在，无需同步[/yellow]")
        return

    console.print("[cyan]正在扫描 Registry...[/cyan]")

    registry = PaperRegistry(registry_path)
    all_papers = registry.list_papers()

    if not all_papers:
        console.print("[green]✓ Registry 为空，无需同步[/green]")
        registry.close()
        return

    # 检查孤立记录
    orphaned = []
    for paper in all_papers:
        storage_id = paper["storage_id"]
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)

        if not paths.paper_dir.exists():
            orphaned.append(paper)

    if not orphaned:
        console.print(f"[green]✓ Registry 与文件系统一致（{len(all_papers)} 篇论文）[/green]")
        registry.close()
        return

    # 显示孤立记录
    console.print(f"\n[yellow]⚠️  发现 {len(orphaned)} 条孤立记录（文件系统中不存在）：[/yellow]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Paper ID", style="dim", width=30)
    table.add_column("标题", width=40)
    table.add_column("状态", width=10)

    for paper in orphaned:
        table.add_row(
            paper["paper_id"][:30],
            (paper.get("title") or "N/A")[:40],
            paper["state"]
        )

    console.print(table)

    if dry_run:
        console.print("\n[dim]（dry-run 模式，未执行删除）[/dim]")
        registry.close()
        return

    # 确认删除
    if not yes:
        console.print("\n[yellow]是否从 Registry 中删除这些孤立记录？[/yellow]")
        console.print("[dim]提示：这不会删除任何文件，仅清理索引[/dim]")

        if not click.confirm("确认删除", default=False):
            console.print("[yellow]已取消[/yellow]")
            registry.close()
            return

    # 执行删除
    console.print("\n[yellow]正在清理孤立记录...[/yellow]")
    deleted_count = 0

    for paper in orphaned:
        try:
            registry.delete_paper(paper["paper_id"])
            deleted_count += 1
            console.print(f"   ✓ 已删除: {paper['paper_id']}")
        except Exception as e:
            console.print(f"   [red]✗ 删除失败: {paper['paper_id']} - {e}[/red]")

    registry.close()

    console.print(f"\n[green]✓ 同步完成，已删除 {deleted_count} 条孤立记录[/green]")
    console.print(f"   保留: {len(all_papers) - deleted_count} 篇论文")
