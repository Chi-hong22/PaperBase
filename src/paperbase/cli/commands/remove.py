"""remove 命令实现 - 硬删除论文"""

import click
from rich.console import Console
from pathlib import Path
import shutil
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.core.manifest import load_manifest


@click.command()
@click.argument("paper_id", type=str)
@click.option("--confirm", is_flag=True, help="跳过交互式确认（危险）")
@click.pass_context
def remove(ctx, paper_id: str, confirm: bool):
    """硬删除论文（包括所有文件和索引）

    警告：此操作不可逆！
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    # Step 1: 检查论文是否存在
    console.print(f"[cyan]正在查找论文:[/cyan] {paper_id}")

    registry_path = base_dir / "registry" / "papers.db"
    if not registry_path.exists():
        console.print("[red]❌ Registry 不存在，无法删除[/red]")
        raise click.Abort()

    registry = PaperRegistry(registry_path)
    paper_info = registry.get_paper(paper_id)

    if not paper_info:
        console.print(f"[red]❌ 论文不存在: {paper_id}[/red]")
        registry.close()
        raise click.Abort()

    storage_id = paper_info["storage_id"]
    paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)

    if not paths.paper_dir.exists():
        console.print(f"[yellow]⚠️  论文目录不存在: {paths.paper_dir}[/yellow]")
        console.print("[yellow]仅删除 Registry 记录...[/yellow]")
        registry.delete_paper(paper_id)
        registry.close()
        console.print("[green]✅ 删除完成（仅 Registry）[/green]")
        return

    # Step 2: 显示论文信息
    console.print("\n[yellow]⚠️  即将删除以下论文：[/yellow]")
    console.print(f"  Paper ID: [cyan]{paper_id}[/cyan]")
    console.print(f"  标题: {paper_info.get('title', 'N/A')}")
    console.print(f"  作者: {', '.join(paper_info.get('authors', [])) or 'N/A'}")
    console.print(f"  年份: {paper_info.get('year', 'N/A')}")
    console.print(f"  状态: {paper_info.get('state', 'N/A')}")
    console.print(f"  路径: {paths.paper_dir}")

    # 检查文件大小
    total_size = sum(f.stat().st_size for f in paths.paper_dir.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)
    console.print(f"  占用空间: {size_mb:.2f} MB")

    # Step 3: 交互式确认
    if not confirm:
        console.print("\n[red bold]警告：此操作将永久删除所有文件，无法恢复！[/red bold]")
        user_input = click.prompt(
            "请输入论文 Paper ID 以确认删除",
            type=str
        )

        if user_input != paper_id:
            console.print("[yellow]❌ 确认失败，删除已取消[/yellow]")
            registry.close()
            raise click.Abort()

    # Step 4: 执行删除
    console.print("\n[yellow]开始删除...[/yellow]")

    # 4.1: 读取 manifest 获取 PDF SHA256
    pdf_sha256 = None
    try:
        if paths.manifest_json.exists():
            manifest = load_manifest(paths.manifest_json)
            if manifest.source_pdf:
                pdf_sha256 = manifest.source_pdf.sha256
    except Exception as e:
        console.print(f"[yellow]⚠️  读取 manifest 失败: {e}[/yellow]")

    # 4.2: 删除论文目录
    console.print("[yellow]1. 删除论文目录...[/yellow]")
    try:
        shutil.rmtree(paths.paper_dir)
        console.print(f"   ✅ 已删除: {paths.paper_dir}")
    except Exception as e:
        console.print(f"[red]❌ 删除目录失败: {e}[/red]")
        registry.close()
        raise

    # 4.3: 从 Registry 删除记录
    console.print("[yellow]2. 从 Registry 删除记录...[/yellow]")
    try:
        registry.delete_paper(paper_id)
        console.print(f"   ✅ 已删除记录: {paper_id}")
    except Exception as e:
        console.print(f"[red]❌ 删除 Registry 记录失败: {e}[/red]")
    finally:
        registry.close()

    # 4.4: 清理孤立的 PDF
    if pdf_sha256:
        console.print("[yellow]3. 检查孤立的 PDF...[/yellow]")
        pdf_path = base_dir / "library" / "sources" / "pdf" / f"{pdf_sha256}.pdf"

        if pdf_path.exists():
            # 检查是否有其他论文引用
            is_orphaned = _check_pdf_orphaned(base_dir, pdf_sha256)

            if is_orphaned:
                try:
                    pdf_path.unlink()
                    console.print(f"   ✅ 已删除孤立 PDF: {pdf_sha256[:16]}...")
                except Exception as e:
                    console.print(f"[yellow]⚠️  删除 PDF 失败: {e}[/yellow]")
            else:
                console.print(f"   ℹ️  PDF 仍被其他论文引用，保留: {pdf_sha256[:16]}...")

    # Step 5: 提示重建图谱
    console.print("\n[green]✅ 删除完成！[/green]")
    console.print("\n[yellow]⚠️  请运行以下命令更新知识图谱：[/yellow]")
    console.print("   [cyan]paperbase graph update --force[/cyan]")


def _check_pdf_orphaned(base_dir: Path, pdf_sha256: str) -> bool:
    """检查 PDF 是否被其他论文引用

    遍历所有 manifest.json，检查是否有其他论文使用相同的 PDF SHA256
    """
    papers_dir = base_dir / "library" / "papers"
    if not papers_dir.exists():
        return True

    for paper_dir in papers_dir.iterdir():
        if not paper_dir.is_dir():
            continue

        manifest_path = paper_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = load_manifest(manifest_path)
            if manifest.source_pdf and manifest.source_pdf.sha256 == pdf_sha256:
                return False  # 仍被引用
        except Exception:
            continue

    return True  # 孤立
