"""update 命令实现"""

import click
import json
from rich.console import Console
from paperbase.core.entity_manager import EntityManager
from paperbase.core.registry import PaperRegistry


@click.command()
@click.argument("paper_id")
@click.option(
    "--json",
    "json_input",
    required=True,
    help="关键信息 JSON 字符串"
)
@click.option(
    "--merge",
    is_flag=True,
    help="合并模式（追加到现有信息）"
)
@click.option(
    "--output-json",
    is_flag=True,
    help="以 JSON 格式输出结果"
)
@click.pass_context
def update(ctx, paper_id: str, json_input: str, merge: bool, output_json: bool):
    """更新论文的关键信息"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    registry_path = base_dir / "registry" / "papers.db"

    # 检查知识库
    if not registry_path.exists():
        if output_json:
            result = {
                "success": False,
                "error": "Knowledge base not found"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print("[red]知识库为空，请先添加论文[/red]")
        ctx.exit(1)

    # 解析 JSON
    try:
        entities_dict = json.loads(json_input)
    except json.JSONDecodeError as e:
        if output_json:
            result = {
                "success": False,
                "error": f"Invalid JSON: {str(e)}"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]JSON 格式错误: {e}[/red]")
        ctx.exit(1)

    # 查找论文
    registry = PaperRegistry(registry_path)
    paper = registry.get_paper(paper_id)
    registry.close()

    if not paper:
        if output_json:
            result = {
                "success": False,
                "error": f"Paper not found: {paper_id}"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]未找到论文: {paper_id}[/red]")
        ctx.exit(1)

    storage_id = paper["storage_id"]

    # 更新信息
    entity_manager = EntityManager(base_dir, registry_path=registry_path)

    try:
        entity_manager.update_entities(
            paper_id=paper_id,
            storage_id=storage_id,
            entities_dict=entities_dict,
            merge=merge
        )

        if output_json:
            result = {
                "success": True,
                "paper_id": paper_id,
                "storage_id": storage_id,
                "mode": "merge" if merge else "replace"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            mode_str = "合并" if merge else "替换"
            console.print(f"[green]✓ 已更新论文信息 ({mode_str}模式)[/green]")

    except FileNotFoundError as e:
        if output_json:
            result = {
                "success": False,
                "error": f"File not found: {str(e)}"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]文件未找到: {e}[/red]")
        ctx.exit(1)

    except ValueError as e:
        if output_json:
            result = {
                "success": False,
                "error": f"Validation failed: {str(e)}"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]数据验证失败: {e}[/red]")
        ctx.exit(1)

    except Exception as e:
        if output_json:
            result = {
                "success": False,
                "error": str(e)
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]更新失败: {e}[/red]")
        ctx.exit(1)
