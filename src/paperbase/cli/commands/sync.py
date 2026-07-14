"""sync 命令实现 - 同步 Registry 与文件系统"""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.utils.markdown import parse_frontmatter


def _normalize_authors(raw_authors) -> list[str]:
    authors = []
    for author in raw_authors or []:
        if isinstance(author, str) and author.strip():
            authors.append(author.strip())
        elif isinstance(author, dict):
            name = author.get("name")
            if isinstance(name, str) and name.strip():
                authors.append(name.strip())
    return authors


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="仅显示待删除的孤立记录和待重建的 Canonical，不修改 Registry",
)
@click.option("--yes", "-y", is_flag=True, help="跳过确认，清理孤立记录并重建 Registry")
@click.pass_context
def sync(ctx, dry_run: bool, yes: bool):
    """同步 Registry 与 Canonical Markdown。

    删除缺少 Canonical Markdown 的孤立 Registry 记录，
    并从有效 Canonical 与 manifest 重建未注册索引。
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    registry_path = base_dir / "registry" / "papers.db"
    console.print("[cyan]正在扫描 Registry...[/cyan]")

    registry = PaperRegistry(registry_path) if registry_path.exists() else None
    all_papers = registry.list_papers() if registry is not None else []

    # 检查孤立记录
    orphaned = []
    for paper in all_papers:
        storage_id = paper["storage_id"]
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)

        if not paths.paper_md.exists():
            orphaned.append(paper)

    registry_storage_ids = {paper["storage_id"] for paper in all_papers}
    papers_dir = base_dir / "library" / "papers"
    canonical_paths = list(papers_dir.glob("p_*.md")) if papers_dir.exists() else []
    unregistered = [path for path in canonical_paths if path.stem not in registry_storage_ids]

    if not orphaned and not unregistered:
        console.print(f"[green]✓ Registry 与文件系统一致（{len(all_papers)} 篇论文）[/green]")
        if registry is not None:
            registry.close()
        return

    # 显示孤立记录
    if orphaned:
        console.print(f"\n[yellow]⚠️  发现 {len(orphaned)} 条孤立记录（Canonical 不存在）：[/yellow]\n")

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

    if unregistered:
        console.print(f"\n[yellow]⚠️  Canonical 未注册: {len(unregistered)} 篇[/yellow]")
        for canonical_path in unregistered:
            console.print(f"   - {canonical_path.stem}")

    if dry_run:
        console.print("\n[dim]（dry-run 模式，未执行更改）[/dim]")
        if registry is not None:
            registry.close()
        return

    # 确认同步
    if not yes:
        console.print("\n[yellow]是否执行 Registry 同步？[/yellow]")
        console.print(
            f"[dim]将删除 {len(orphaned)} 条孤立记录，"
            f"重建 {len(unregistered)} 条未注册 Canonical 记录；不会修改论文文件[/dim]"
        )

        if not click.confirm("确认同步", default=False):
            console.print("[yellow]已取消[/yellow]")
            if registry is not None:
                registry.close()
            return

    if registry is None:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry = PaperRegistry(registry_path)

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

    console.print("\n[yellow]正在重建未注册记录...[/yellow]")
    rebuilt_count = 0
    rebuild_failed_count = 0

    for canonical_path in unregistered:
        storage_id = canonical_path.stem
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        try:
            if not paths.manifest_json.exists():
                raise ValueError("manifest.json 不存在")

            manifest = load_manifest(paths.manifest_json)
            if manifest.storage_id != storage_id:
                raise ValueError("manifest storage_id 与 Canonical 路径不一致")

            metadata, _ = parse_frontmatter(canonical_path.read_text(encoding="utf-8"))
            frontmatter_storage_id = metadata.get("storage_id")
            if frontmatter_storage_id and frontmatter_storage_id != storage_id:
                raise ValueError("frontmatter storage_id 与 Canonical 路径不一致")

            identifiers = metadata.get("identifiers")
            doi = metadata.get("doi")
            if not doi and isinstance(identifiers, dict):
                doi = identifiers.get("doi")
            if not doi and manifest.paper_id.startswith("doi:"):
                doi = manifest.paper_id.removeprefix("doi:")

            year = metadata.get("year")
            if isinstance(year, str) and year.isdigit():
                year = int(year)

            registry.register_paper(
                paper_id=manifest.paper_id,
                storage_id=manifest.storage_id,
                state=manifest.state,
                title=metadata.get("title"),
                authors=_normalize_authors(metadata.get("authors")),
                year=year,
                doi=doi,
            )
            rebuilt_count += 1
            console.print(f"   ✓ 已重建: {manifest.paper_id}")
        except Exception as e:
            rebuild_failed_count += 1
            console.print(f"   [red]✗ 无法重建: {storage_id} - {e}[/red]")

    registry.close()

    console.print("\n[green]✓ 同步完成[/green]")
    console.print(f"   已删除孤立记录: {deleted_count}")
    console.print(f"   已重建 Registry: {rebuilt_count}")
    if rebuild_failed_count:
        console.print(f"   无法重建: {rebuild_failed_count}")
