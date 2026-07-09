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
from paperbase.adapters.paper_fetch_adapter import PaperFetchAdapter, PaperFetchUnavailable
from paperbase.core.normalizer import normalize_paper
from paperbase.core.online_ingest import ingest_fetched_paper
from paperbase.schemas.manifest import PaperState, SourcePDF, CanonicalMD, PipelineInfo
from paperbase.core.chunker import generate_chunks, write_chunks_jsonl
from paperbase.utils.hash import sha256_file, sha256_string
from paperbase.utils.markdown import generate_canonical_markdown
import shutil


def _target_is_local_file(target: str | None) -> bool:
    if not target:
        return False
    return Path(target).expanduser().exists()


def _ingest_online(ctx, query: str, no_graph: bool):
    console = Console()
    base_dir = ctx.obj["base_dir"]
    try:
        fetched = PaperFetchAdapter().fetch(query)
    except PaperFetchUnavailable as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc

    result = ingest_fetched_paper(base_dir=base_dir, fetched=fetched)
    console.print("[green]✓ 论文已成功添加到知识库[/green]")
    console.print(f"论文标识: {result.paper_id}")
    if no_graph:
        console.print("[dim]跳过索引更新（--no-graph）[/dim]")
    return result


def _ingest_local_pdf(ctx, pdf_path: Path, no_graph: bool):
    """摄入本地 PDF 文件"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

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

        # Step 6: 整理论文信息
        console.print("[yellow]6. 整理论文信息...[/yellow]")
        paper_metadata = normalize_paper(
            candidate_md=candidate_md,
            metadata=metadata,
            paper_id=paper_id,
            storage_id=storage_id,
            source_provider="markitdown"
        )

        # Step 7: 生成标准格式文档
        console.print("[yellow]7. 生成标准格式文档...[/yellow]")
        # 转换 PaperMetadata 为字典
        metadata_dict = paper_metadata.model_dump(mode="json", exclude_none=True)
        canonical_md = generate_canonical_markdown(metadata_dict, candidate_md)
        paths.paper_md.write_text(canonical_md, encoding="utf-8")
        canonical_sha256 = sha256_string(canonical_md)

        # Step 7.5: 生成分块文件
        console.print("[yellow]7.5. 生成文本分块...[/yellow]")
        chunks = generate_chunks(canonical_md, paper_id)
        if chunks:
            write_chunks_jsonl(chunks, paths.chunks_jsonl)
            console.print(f"   ✓ 生成 {len(chunks)} 个文本块")

        # Step 8: 保存元数据
        console.print("[yellow]8. 保存元数据...[/yellow]")
        manifest = create_manifest(paper_id, storage_id)
        manifest.state = PaperState.NORMALIZED
        manifest.source_pdf = SourcePDF(
            path="./source/source.pdf",
            sha256=pdf_sha256,
            acquired_at=paper_metadata.provenance.ingested_at
        )
        manifest.canonical_md = CanonicalMD(
            path=f"../{storage_id}.md",
            sha256=canonical_sha256,
            schema_version="1.0"
        )
        manifest.pipeline = PipelineInfo(
            converter="markitdown",
            converter_version="0.0.1",
            normalizer_version="1.0.0"
        )
        save_manifest(manifest, paths.manifest_json)

        # Step 9: 记录到知识库
        console.print("[yellow]9. 记录到知识库...[/yellow]")
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

        console.print(f"\n[green]✓ 论文已保存到知识库[/green]")
        console.print(f"   路径: {paths.paper_dir}")

        # Step 9: 更新知识库索引（可选）
        if not no_graph:
            console.print("\n[yellow]9. 更新知识库索引...[/yellow]")
            try:
                from paperbase.cli.commands.graph import update as graph_update
                # 调用 graph update 命令
                ctx.invoke(graph_update, force=False)
            except Exception as e:
                console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
        else:
            console.print("\n[dim]跳过索引更新（--no-graph）[/dim]")
            console.print("   稍后可运行: [cyan]paperbase graph update[/cyan]")

        # 摄入流程完成
        console.print(f"\n[green]✓ 摄入完成[/green]")
        console.print(f"   论文已成功添加到知识库")

    except Exception as e:
        console.print(f"\n[red]❌ 摄入失败: {e}[/red]")
        raise


@click.command()
@click.argument("target", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, path_type=Path), help="本地 PDF 文件路径")
@click.option("--no-graph", is_flag=True, help="跳过图谱更新")
@click.option("--batch", type=click.Path(exists=True, path_type=Path), help="批量摄入文件列表（每行一个路径、DOI、URL 或标题）")
@click.pass_context
def ingest(ctx, target: str | None, file_path: Path | None, no_graph: bool, batch: Path | None):
    """摄入论文：本地 PDF 或 DOI/URL/title"""
    console = Console()

    # 互斥检查
    if sum([bool(target), bool(file_path), bool(batch)]) > 1:
        console.print("[red]❌ 只能指定一个输入源：TARGET、--file 或 --batch[/red]")
        raise click.Abort()

    if not target and not file_path and not batch:
        console.print("[red]❌ 必须提供输入源：TARGET、--file 或 --batch[/red]")
        raise click.Abort()

    # 批量模式
    if batch:
        _ingest_batch(ctx, batch, no_graph)
        return

    # 本地文件模式
    if file_path is not None:
        _ingest_local_pdf(ctx, file_path, no_graph)
        return

    if target and _target_is_local_file(target):
        _ingest_local_pdf(ctx, Path(target), no_graph)
        return

    # 在线查询模式
    if target:
        _ingest_online(ctx, target, no_graph)
        return


def _ingest_batch(ctx, batch_file: Path, no_graph: bool):
    """批量摄入论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print(f"[cyan]批量摄入:[/cyan] {batch_file.name}")

    # 读取文件列表
    try:
        targets = []
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    targets.append(line)

        console.print(f"[cyan]找到 {len(targets)} 篇论文[/cyan]\n")

        # 逐个摄入（跳过图谱）
        success_count = 0
        failed_count = 0

        for i, target in enumerate(targets, 1):
            # 判断是本地文件还是在线查询
            if _target_is_local_file(target):
                display_name = Path(target).name
            else:
                display_name = target[:50] + "..." if len(target) > 50 else target

            console.print(f"[cyan][{i}/{len(targets)}] {display_name}[/cyan]")
            try:
                # 调用主 ingest 命令，让它自动路由
                ctx.invoke(ingest, target=target, no_graph=True, batch=None)
                success_count += 1
            except Exception as e:
                console.print(f"[red]✗ 失败: {e}[/red]")
                failed_count += 1

            console.print()  # 空行分隔

        # 统计
        console.print(f"[cyan]批量摄入完成[/cyan]")
        console.print(f"  成功: {success_count} 篇")
        console.print(f"  失败: {failed_count} 篇")

        # 统一更新图谱
        if not no_graph and success_count > 0:
            console.print("\n[yellow]更新知识库索引...[/yellow]")
            try:
                from paperbase.cli.commands.graph import update as graph_update
                ctx.invoke(graph_update, force=False)
            except Exception as e:
                console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
        elif no_graph:
            console.print("\n[dim]跳过索引更新（--no-graph）[/dim]")
            console.print("   稍后可运行: [cyan]paperbase graph update[/cyan]")

    except Exception as e:
        console.print(f"[red]✗ 批量摄入失败: {e}[/red]")
        raise
