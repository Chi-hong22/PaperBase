"""构建全文检索索引命令"""

import click
from pathlib import Path
from rich.console import Console
from paperbase.core.search_engine import SearchEngine

console = Console()


@click.command()
@click.option(
    "--base-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    help="PaperBase 项目根目录（默认: 当前目录）",
)
def index_cmd(base_dir: Path):
    """构建全文检索索引

    扫描 library/papers/ 下的所有 chunks.jsonl 文件，
    构建基于 SQLite FTS5 的全文检索索引。

    示例：
        paperbase index
        paperbase index --base-dir /path/to/paperbase
    """
    index_path = base_dir / "index" / "fts.db"
    library_path = base_dir / "library" / "papers"

    # 检查 library 目录
    if not library_path.exists():
        console.print("[red]错误: library/papers 目录不存在[/red]")
        console.print(f"路径: {library_path}")
        return

    # 检查是否有论文
    chunks_files = list(library_path.glob("*/chunks.jsonl"))
    if not chunks_files:
        console.print("[yellow]警告: 未找到任何 chunks.jsonl 文件[/yellow]")
        console.print("请先摄入论文: paperbase ingest <source>")
        return

    console.print(f"[cyan]构建全文检索索引...[/cyan]")
    console.print(f"  论文数: {len(chunks_files)}")
    console.print(f"  索引位置: {index_path}")

    try:
        with SearchEngine(index_path, library_path) as engine:
            engine.build_index()

        console.print("[green]✓ 索引构建完成[/green]")
        console.print(f"\n使用方法: paperbase search \"<query>\"")

    except Exception as e:
        console.print(f"[red]✗ 索引构建失败: {e}[/red]")
        raise
