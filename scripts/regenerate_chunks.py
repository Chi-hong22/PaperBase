#!/usr/bin/env python3
"""为现有论文补生成 chunks.jsonl

用法：
    python scripts/regenerate_chunks.py
    python scripts/regenerate_chunks.py --paper-id <id>
"""

import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from rich.console import Console
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.core.chunker import generate_chunks, write_chunks_jsonl


@click.command()
@click.option("--paper-id", help="仅处理指定论文")
@click.option("--base-dir", type=click.Path(exists=True), default=".", help="PaperBase 根目录")
@click.option("--force", is_flag=True, help="强制覆盖已有 chunks")
def main(paper_id: str | None, base_dir: str, force: bool):
    """为现有论文补生成 chunks.jsonl"""
    console = Console()
    base_path = Path(base_dir).resolve()

    registry_path = base_path / "registry" / "papers.db"
    if not registry_path.exists():
        console.print("[red]Registry 不存在[/red]")
        return

    registry = PaperRegistry(registry_path)

    # 获取论文列表
    if paper_id:
        paper = registry.get_paper(paper_id)
        if not paper:
            console.print(f"[red]未找到论文: {paper_id}[/red]")
            registry.close()
            return
        papers = [paper]
    else:
        papers = registry.list_papers()

    console.print(f"[cyan]准备处理 {len(papers)} 篇论文...[/cyan]\n")

    success_count = 0
    skip_count = 0
    error_count = 0

    for paper in papers:
        pid = paper["paper_id"]
        sid = paper["storage_id"]
        title = paper.get("title", "N/A")

        paths = PaperPaths(storage_id=sid, base_dir=base_path)

        # 检查 chunks.jsonl 是否已存在
        if paths.chunks_jsonl.exists() and not force:
            console.print(f"[dim]跳过: {title[:50]} (已有 chunks)[/dim]")
            skip_count += 1
            continue

        # 检查 paper.md 是否存在
        if not paths.paper_md.exists():
            console.print(f"[yellow]跳过: {title[:50]} (paper.md 不存在)[/yellow]")
            skip_count += 1
            continue

        try:
            # 读取 canonical markdown
            canonical_md = paths.paper_md.read_text(encoding="utf-8")

            # 生成 chunks
            chunks = generate_chunks(canonical_md, pid)

            if not chunks:
                console.print(f"[yellow]警告: {title[:50]} (未生成 chunks)[/yellow]")
                error_count += 1
                continue

            # 写入 chunks.jsonl
            write_chunks_jsonl(chunks, paths.chunks_jsonl)

            console.print(f"[green]✓[/green] {title[:50]} ({len(chunks)} chunks)")
            success_count += 1

        except Exception as e:
            console.print(f"[red]✗[/red] {title[:50]} ({e})")
            error_count += 1

    registry.close()

    # 总结
    console.print(f"\n[cyan]处理完成:[/cyan]")
    console.print(f"  成功: {success_count}")
    console.print(f"  跳过: {skip_count}")
    console.print(f"  失败: {error_count}")

    if success_count > 0:
        console.print(f"\n[yellow]提示: 运行以下命令重建索引:[/yellow]")
        console.print(f"  [cyan]paperbase index[/cyan]")


if __name__ == "__main__":
    main()
