"""PaperBase CLI 入口"""

import click
from pathlib import Path
from paperbase.cli.commands.status import status
from paperbase.cli.commands.ingest import ingest
from paperbase.cli.commands.graph import graph
from paperbase.cli.commands.search import search
from paperbase.cli.commands.query import query


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--base-dir",
    type=click.Path(path_type=Path),
    default=Path.cwd(),
    help="PaperBase 根目录"
)
@click.pass_context
def main(ctx, base_dir: Path):
    """PaperBase - 学术论文知识库"""
    ctx.ensure_object(dict)
    ctx.obj["base_dir"] = base_dir


# 注册命令
main.add_command(status)
main.add_command(ingest)
main.add_command(graph)
main.add_command(search)
main.add_command(query)


if __name__ == "__main__":
    main()
