"""ingest 命令实现"""

import click
from rich.console import Console
from pathlib import Path
from paperbase.core.identity import normalize_paper_id, generate_storage_id
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.core.manifest import create_manifest, save_manifest
from paperbase.adapters.pdf_extractor import extract_pdf_metadata, extract_pdf_text
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
from paperbase.core.normalizer import normalize_paper
from paperbase.schemas.manifest import PaperState, SourcePDF, CanonicalMD, PipelineInfo
from paperbase.utils.hash import sha256_file, sha256_string
import shutil
import yaml


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("--no-graph", is_flag=True, help="跳过图谱更新")
@click.option("--batch", type=click.Path(exists=True, path_type=Path), help="批量摄入文件列表（每行一个路径）")
@click.pass_context
def ingest(ctx, pdf_path: Path | None, no_graph: bool, batch: Path | None):
    """摄入论文 PDF"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    # 互斥检查
    if pdf_path and batch:
        console.print("[red]❌ 不能同时使用 PDF_PATH 和 --batch[/red]")
        raise click.Abort()

    if not pdf_path and not batch:
        console.print("[red]❌ 必须提供 PDF_PATH 或 --batch[/red]")
        raise click.Abort()

    # 批量模式
    if batch:
        _ingest_batch(ctx, batch, no_graph)
        return

    # 单文件模式
    console.print(f"[cyan]开始摄入论文:[/cyan] {pdf_path.name}")

    try:
        # Step 1: 提取元数据
        console.print("[yellow]1. 提取 PDF 元数据...[/yellow]")
        metadata = extract_pdf_metadata(pdf_path)
        console.print(f"   标题: {metadata.get('title', 'N/A')}")
        console.print(f"   作者: {', '.join(metadata.get('authors', [])) or 'N/A'}")
        console.print(f"   年份: {metadata.get('year', 'N/A')}")

        # Step 2: 生成 paper_id
        console.print("[yellow]2. 生成 paper_id...[/yellow]")
        if metadata.get("doi"):
            paper_id = normalize_paper_id(metadata["doi"])
        else:
            # Fallback: 使用文件名
            paper_id = f"fallback:{pdf_path.stem}"
            paper_id = normalize_paper_id(paper_id)

        storage_id = generate_storage_id(paper_id)
        console.print(f"   paper_id: {paper_id}")
        console.print(f"   storage_id: {storage_id}")

        # Step 3: 创建目录结构
        console.print("[yellow]3. 创建存储目录...[/yellow]")
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        paths.create_directories()

        # Step 4: 复制 PDF 到 source
        console.print("[yellow]4. 保存源 PDF...[/yellow]")
        shutil.copy2(pdf_path, paths.source_pdf)
        pdf_sha256 = sha256_file(paths.source_pdf)
        console.print(f"   SHA256: {pdf_sha256[:16]}...")

        # Step 5: 转换为 Markdown
        console.print("[yellow]5. 转换为 Markdown...[/yellow]")
        candidate_md = convert_pdf_to_markdown(pdf_path)
        console.print(f"   长度: {len(candidate_md)} 字符")

        # Step 6: 规范化
        console.print("[yellow]6. 规范化论文数据...[/yellow]")
        paper_metadata = normalize_paper(
            candidate_md=candidate_md,
            metadata=metadata,
            paper_id=paper_id,
            storage_id=storage_id,
            source_provider="markitdown"
        )

        # Step 7: 生成 Canonical Markdown
        console.print("[yellow]7. 生成 Canonical Markdown...[/yellow]")
        canonical_md = generate_canonical_markdown(paper_metadata, candidate_md)
        paths.paper_md.write_text(canonical_md, encoding="utf-8")
        canonical_sha256 = sha256_string(canonical_md)

        # Step 8: 创建 manifest
        console.print("[yellow]8. 创建 manifest...[/yellow]")
        manifest = create_manifest(paper_id, storage_id)
        manifest.state = PaperState.NORMALIZED
        manifest.source_pdf = SourcePDF(
            path="./source/source.pdf",
            sha256=pdf_sha256,
            acquired_at=paper_metadata.provenance.ingested_at
        )
        manifest.canonical_md = CanonicalMD(
            path="./paper.md",
            sha256=canonical_sha256,
            schema_version="1.0"
        )
        manifest.pipeline = PipelineInfo(
            converter="markitdown",
            converter_version="0.0.1",
            normalizer_version="1.0.0"
        )
        save_manifest(manifest, paths.manifest_json)

        # Step 9: 注册到 registry
        console.print("[yellow]9. 注册到 registry...[/yellow]")
        registry_path = base_dir / "registry" / "papers.db"
        registry_path.parent.mkdir(exist_ok=True)
        registry = PaperRegistry(registry_path)
        registry.register_paper(
            paper_id=paper_id,
            storage_id=storage_id,
            state=PaperState.NORMALIZED,
            title=paper_metadata.title,
            authors=[a.name for a in paper_metadata.authors],
            year=paper_metadata.year,
            doi=metadata.get("doi")
        )
        registry.close()

        console.print(f"\n[green]✅ 论文已注册到知识库[/green]")
        console.print(f"   路径: {paths.paper_dir}")
        console.print(f"   状态: {PaperState.NORMALIZED.value}")

        # Step 9.5: 自动提取实体（如果 LLM 已配置）
        console.print("\n[cyan]检查实体提取...[/cyan]")
        try:
            from paperbase.core.entity_manager import EntityManager

            entity_manager = EntityManager(base_dir=base_dir)

            if entity_manager.llm_client.enabled:
                console.print("  [yellow]内部 LLM 已启用，正在提取实体...[/yellow]")

                try:
                    entities = entity_manager.auto_extract_entities(paper_id, storage_id)

                    if entities:
                        console.print("[green]✅ 实体已自动提取（内部 LLM）[/green]")
                        for category, items in entities.items():
                            if items:
                                names = [e.get("name", "") for e in items]
                                console.print(f"   {category}: {', '.join(names[:3])}")
                                if len(names) > 3:
                                    console.print(f"      ... 及其他 {len(names) - 3} 项")
                    else:
                        console.print("[yellow]⚠️  实体提取失败或返回空[/yellow]")
                        console.print("   论文已摄入，可稍后手动填充实体")

                except Exception as e:
                    console.print(f"[yellow]⚠️  实体提取异常: {e}[/yellow]")
                    console.print("   论文已摄入，可稍后手动填充实体")
            else:
                console.print("[yellow]ℹ️  内部 LLM 未配置，跳过自动提取[/yellow]")
                console.print("   提示：")
                console.print("   1. 配置内部 LLM: 编辑 config/paperbase.yaml")
                console.print("   2. 使用外部 Agent: 让 Claude Code/Codex 调用 'paperbase update'")
                console.print("   3. 手动填充: paperbase update <paper_id> --json '{{...}}'")

        except ImportError as e:
            console.print(f"[yellow]⚠️  无法导入 EntityManager: {e}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️  实体提取检查失败: {e}[/yellow]")

        # Step 10: 更新图谱（可选）
        if not no_graph:
            console.print("\n[yellow]10. 更新知识图谱...[/yellow]")
            try:
                from paperbase.cli.commands.graph import update as graph_update
                # 调用 graph update 命令
                ctx.invoke(graph_update, force=False)
            except Exception as e:
                console.print(f"[yellow]⚠️  图谱更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
        else:
            console.print("\n[yellow]ℹ️  跳过图谱更新（--no-graph）[/yellow]")
            console.print("   稍后可运行: [cyan]paperbase graph update[/cyan]")

        # 摄入流程完成
        console.print(f"\n[green]✅ 摄入完成![/green]")
        console.print(f"   论文已成功添加到知识库")

    except Exception as e:
        console.print(f"\n[red]❌ 摄入失败: {e}[/red]")
        raise


def generate_canonical_markdown(metadata: "PaperMetadata", body: str) -> str:
    """生成 Canonical Markdown"""
    import yaml

    # 生成 frontmatter
    frontmatter_dict = metadata.model_dump(mode="json", exclude_none=True)
    frontmatter_yaml = yaml.dump(frontmatter_dict, allow_unicode=True, sort_keys=False)

    # 组合
    canonical = f"---\n{frontmatter_yaml}---\n\n{body}"

    return canonical


def _ingest_batch(ctx, batch_file: Path, no_graph: bool):
    """批量摄入论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print(f"[cyan]批量摄入模式:[/cyan] {batch_file.name}")

    # 读取文件列表
    try:
        pdf_paths = []
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    pdf_path = Path(line)
                    if not pdf_path.exists():
                        console.print(f"[yellow]⚠️  跳过不存在的文件: {line}[/yellow]")
                        continue
                    pdf_paths.append(pdf_path)

        console.print(f"[cyan]找到 {len(pdf_paths)} 个有效 PDF 文件[/cyan]\n")

        # 逐个摄入（跳过图谱）
        success_count = 0
        failed_count = 0

        for i, pdf_path in enumerate(pdf_paths, 1):
            console.print(f"[cyan]--- [{i}/{len(pdf_paths)}] {pdf_path.name} ---[/cyan]")
            try:
                # 调用单文件摄入逻辑，强制跳过图谱
                ctx.invoke(ingest, pdf_path=pdf_path, no_graph=True, batch=None)
                success_count += 1
            except Exception as e:
                console.print(f"[red]❌ 摄入失败: {e}[/red]")
                failed_count += 1

            console.print()  # 空行分隔

        # 统计
        console.print(f"[cyan]批量摄入完成:[/cyan]")
        console.print(f"  成功: {success_count} 篇")
        console.print(f"  失败: {failed_count} 篇")

        # 统一更新图谱
        if not no_graph and success_count > 0:
            console.print("\n[yellow]开始统一更新知识图谱...[/yellow]")
            try:
                from paperbase.cli.commands.graph import update as graph_update
                ctx.invoke(graph_update, force=False)
            except Exception as e:
                console.print(f"[yellow]⚠️  图谱更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
        elif no_graph:
            console.print("\n[yellow]ℹ️  跳过图谱更新（--no-graph）[/yellow]")
            console.print("   稍后可运行: [cyan]paperbase graph update[/cyan]")

    except Exception as e:
        console.print(f"[red]❌ 批量摄入失败: {e}[/red]")
        raise
