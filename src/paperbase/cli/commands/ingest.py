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
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def ingest(ctx, pdf_path: Path):
    """摄入论文 PDF"""
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

        console.print(f"\n[green]✅ 摄入完成![/green]")
        console.print(f"   路径: {paths.paper_dir}")
        console.print(f"   状态: {PaperState.NORMALIZED.value}")

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
