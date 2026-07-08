"""extract 命令实现 - 对已摄入论文提取关键信息"""

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from paperbase.core.entity_manager import EntityManager
from paperbase.core.registry import PaperRegistry


@click.command()
@click.argument("paper_id", required=False)
@click.option(
    "--all",
    is_flag=True,
    help="提取所有论文的关键信息"
)
@click.option(
    "--force",
    is_flag=True,
    help="强制重新提取（即使已提取过）"
)
@click.option(
    "--output-json",
    is_flag=True,
    help="以 JSON 格式输出结果"
)
@click.pass_context
def extract(ctx, paper_id: str | None, all: bool, force: bool, output_json: bool):
    """提取论文关键信息（方法、数据集、领域等）

    用法:
      paperbase extract <paper_id>           提取单篇论文
      paperbase extract --all                提取所有未处理的论文
      paperbase extract --all --force        强制重新提取所有论文
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]
    registry_path = base_dir / "registry" / "papers.db"

    # 参数检查
    if not paper_id and not all:
        console.print("[red]请指定要提取的论文，或使用 --all 提取所有论文[/red]")
        console.print("用法: paperbase extract <paper_id> 或 paperbase extract --all")
        ctx.exit(1)

    if paper_id and all:
        console.print("[red]不能同时指定论文 ID 和 --all 选项[/red]")
        ctx.exit(1)

    # 检查 registry
    if not registry_path.exists():
        if output_json:
            import json
            result = {"success": False, "error": "Registry not found"}
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print("[red]知识库为空，请先添加论文[/red]")
        ctx.exit(1)

    # 初始化
    entity_manager = EntityManager(base_dir=base_dir, registry_path=registry_path)

    # 检查 LLM 是否启用
    if not entity_manager.llm_client.enabled:
        if output_json:
            import json
            result = {
                "success": False,
                "error": "LLM not configured",
                "hint": "Configure LLM in config/paperbase.yaml"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print("[red]LLM 未配置[/red]")
            console.print("配置方法:")
            console.print("  1. 编辑 config/paperbase.yaml")
            console.print("  2. 设置 llm.enabled: true")
            console.print("  3. 配置环境变量 PAPERBASE_LLM_*")
        ctx.exit(1)

    registry = PaperRegistry(registry_path)

    try:
        if all:
            # 批量提取
            _extract_all(console, registry, entity_manager, force, output_json)
        else:
            # 单篇提取
            _extract_single(console, registry, entity_manager, paper_id, force, output_json)
    finally:
        registry.close()


def _extract_single(console, registry, entity_manager, paper_id, force, output_json):
    """提取单篇论文关键信息"""
    import json
    from pathlib import Path

    paper = registry.get_paper(paper_id)

    if not paper:
        if output_json:
            result = {"success": False, "error": f"Paper not found: {paper_id}"}
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]未找到论文: {paper_id}[/red]")
        return

    storage_id = paper["storage_id"]

    # 检查是否已提取过
    if not force:
        from paperbase.core.paths import PaperPaths
        paths = PaperPaths(storage_id=storage_id, base_dir=entity_manager.base_dir)

        if paths.paper_md.exists():
            with open(paths.paper_md, "r", encoding="utf-8") as f:
                content = f.read()

            # 简单检查是否有非空实体
            if 'entities:' in content and ('- name:' in content or '[]' not in content):
                if output_json:
                    result = {
                        "success": False,
                        "error": "Entities already extracted",
                        "hint": "Use --force to override"
                    }
                    click.echo(json.dumps(result, ensure_ascii=False))
                else:
                    console.print(f"[yellow]已提取过关键信息，使用 --force 强制重新提取[/yellow]")
                return

    if not output_json:
        console.print(f"[cyan]正在提取:[/cyan] {paper.get('title', 'Unknown')[:60]}...")

    try:
        entities = entity_manager.auto_extract_entities(paper_id, storage_id)

        if entities:
            if output_json:
                result = {
                    "success": True,
                    "paper_id": paper_id,
                    "storage_id": storage_id,
                    "entities": entities
                }
                click.echo(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                console.print("[green]✓ 提取完成[/green]")
                for category, items in entities.items():
                    if items:
                        names = [e.get("name", "") for e in items]
                        console.print(f"  {category}: {', '.join(names[:3])}")
                        if len(names) > 3:
                            console.print(f"    ... 及其他 {len(names) - 3} 项")
        else:
            if output_json:
                result = {
                    "success": False,
                    "error": "Extraction returned empty"
                }
                click.echo(json.dumps(result, ensure_ascii=False))
            else:
                console.print("[yellow]⚠ 提取未返回结果[/yellow]")

    except Exception as e:
        if output_json:
            result = {
                "success": False,
                "error": str(e)
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print(f"[red]提取失败: {e}[/red]")


def _extract_all(console, registry, entity_manager, force, output_json):
    """批量提取所有论文关键信息"""
    import json
    from paperbase.core.paths import PaperPaths

    papers = registry.list_papers()

    if not papers:
        if output_json:
            result = {"success": True, "message": "No papers found"}
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print("[yellow]知识库中没有论文[/yellow]")
        return

    # 过滤已提取过的论文（如果不是 force 模式）
    papers_to_extract = []

    if not force:
        for paper in papers:
            storage_id = paper["storage_id"]
            paths = PaperPaths(storage_id=storage_id, base_dir=entity_manager.base_dir)

            if paths.paper_md.exists():
                with open(paths.paper_md, "r", encoding="utf-8") as f:
                    content = f.read()

                # 简单检查是否有非空实体
                if 'entities:' in content and '- name:' in content:
                    continue  # 跳过已提取的论文

            papers_to_extract.append(paper)
    else:
        papers_to_extract = papers

    if not papers_to_extract:
        if output_json:
            result = {
                "success": True,
                "message": "All entities already extracted",
                "hint": "Use --force to re-extract"
            }
            click.echo(json.dumps(result, ensure_ascii=False))
        else:
            console.print("[green]所有论文已提取完成[/green]")
            console.print("提示: 使用 --force 强制重新提取")
        return

    if not output_json:
        console.print(f"[cyan]批量提取关键信息:[/cyan] {len(papers_to_extract)} 篇论文\n")

    results = []
    success_count = 0
    failed_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        disable=output_json
    ) as progress:
        task = progress.add_task("提取中...", total=len(papers_to_extract))

        for paper in papers_to_extract:
            paper_id = paper["paper_id"]
            storage_id = paper["storage_id"]
            title = paper.get("title", "Unknown")

            if not output_json:
                progress.update(task, description=f"提取: {title[:40]}...")

            try:
                entities = entity_manager.auto_extract_entities(paper_id, storage_id)

                if entities:
                    success_count += 1
                    results.append({
                        "paper_id": paper_id,
                        "success": True,
                        "entities": entities
                    })

                    if not output_json:
                        entity_count = sum(len(items) for items in entities.values())
                        console.print(f"  [green]✓[/green] {title[:50]}... ({entity_count} 项)")
                else:
                    failed_count += 1
                    results.append({
                        "paper_id": paper_id,
                        "success": False,
                        "error": "Extraction returned empty"
                    })

                    if not output_json:
                        console.print(f"  [yellow]⚠[/yellow] {title[:50]}... (提取失败)")

            except Exception as e:
                failed_count += 1
                results.append({
                    "paper_id": paper_id,
                    "success": False,
                    "error": str(e)
                })

                if not output_json:
                    console.print(f"  [red]✗[/red] {title[:50]}... ({e})")

            progress.advance(task)

    if output_json:
        result = {
            "success": True,
            "total": len(papers_to_extract),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print(f"\n[green]✓ 批量提取完成[/green]")
        console.print(f"  成功: {success_count} 篇")
        console.print(f"  失败: {failed_count} 篇")
