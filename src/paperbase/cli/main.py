"""PaperBase CLI 入口"""

import os
import click
from pathlib import Path
from dotenv import load_dotenv
from paperbase.cli.commands.status import status
from paperbase.cli.commands.ingest import ingest
from paperbase.cli.commands.graph import graph
from paperbase.cli.commands.search import search
from paperbase.cli.commands.index import index_cmd
from paperbase.cli.commands.query import query
from paperbase.cli.commands.doctor import doctor
from paperbase.cli.commands.remove import remove
from paperbase.cli.commands.config import config

# 加载 .env 文件（如果存在）
load_dotenv()


def get_default_base_dir() -> Path:
    """获取默认的 base_dir，优先使用环境变量"""
    if env_path := os.getenv("PAPERBASE_LIBRARY"):
        return Path(env_path)
    return Path.cwd()


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--base-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="PaperBase 根目录（默认：$PAPERBASE_LIBRARY 或当前目录）"
)
@click.pass_context
def main(ctx, base_dir: Path | None):
    """PaperBase - 学术论文知识库"""
    ctx.ensure_object(dict)
    ctx.obj["base_dir"] = base_dir if base_dir is not None else get_default_base_dir()


# 注册命令
main.add_command(status)
main.add_command(ingest)
main.add_command(graph)
main.add_command(search)
main.add_command(index_cmd, name="index")
main.add_command(query)
main.add_command(doctor)
main.add_command(remove)
main.add_command(config)


if __name__ == "__main__":
    main()
