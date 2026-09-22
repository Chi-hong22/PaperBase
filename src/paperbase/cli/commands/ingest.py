"""ingest 命令实现"""

import os
import shutil
import stat
from pathlib import Path

import click
import yaml
from rich.console import Console

from paperbase.adapters.paper_fetch_adapter import PaperFetchAdapter, PaperFetchUnavailable
from paperbase.adapters.pdf_extractor import extract_pdf_metadata
from paperbase.config.loader import load_config
from paperbase.config.models import PdfConversionConfig
from paperbase.core.canonical_adoption_gate import (
    CanonicalAdoptionGateError,
    validateCanonicalAdoption,
)
from paperbase.core.chunker import generate_chunks, write_chunks_jsonl
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import create_manifest, load_manifest, save_manifest
from paperbase.core.normalizer import normalize_paper
from paperbase.core.online_ingest import ingest_fetched_paper
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
    PdfConversionOutcome,
    ReadyConversionOutcome,
    progressPdfConversion,
)
from paperbase.core.registry import PaperRegistry
from paperbase.core.visual_adoption import cleanupReadyVisualRuns
from paperbase.core.visual_repair_run import isPathReparsePoint
from paperbase.schemas.manifest import CanonicalMD, PaperState, PipelineInfo, SourcePDF
from paperbase.schemas.paper import PaperIdentifiers
from paperbase.utils.hash import sha256_file, sha256_string
from paperbase.utils.markdown import generate_canonical_markdown
from paperbase.utils.timestamp import now_iso8601


def _reReviewKwargs(re_review: bool) -> dict[str, bool]:  # noqa: N802
    """Only forward the new seam keyword when explicitly requested."""
    return {"re_review": True} if re_review else {}


def _target_is_local_file(target: str | None) -> bool:
    if not target:
        return False
    return Path(target).expanduser().exists()


def _print_agent_graph_handoff(console: Console) -> None:
    """输出 Agent-first 语义建图的后续步骤。"""
    console.print("[cyan]下一步（Agent 语义图谱流程）:[/cyan]")
    console.print("   paperbase graph preflight")
    console.print("   在本机 library/papers 目录下运行：/graphify . --update --no-viz")
    console.print("   语义 Agent 必须调用 subagents 并行处理 Canonical Markdown")
    console.print("   paperbase graph adopt")


def _save_incomplete_local_pdf_manifest(
    paths: PaperPaths,
    paper_id: str,
    storage_id: str,
    pdf_sha256: str,
    state: PaperState,
) -> None:
    """保存未采用 PDF 转换的可恢复状态。"""
    if paths.manifest_json.exists():
        manifest = load_manifest(paths.manifest_json)
    else:
        manifest = create_manifest(paper_id, storage_id)

    acquired_at = now_iso8601()
    if manifest.source_pdf and manifest.source_pdf.sha256 == pdf_sha256:
        acquired_at = manifest.source_pdf.acquired_at

    manifest.state = state
    manifest.source_pdf = SourcePDF(
        path="./source/source.pdf",
        sha256=pdf_sha256,
        acquired_at=acquired_at,
    )
    manifest.canonical_md = None
    manifest.pipeline = PipelineInfo(
        converter="markitdown",
        converter_version="0.0.1",
        normalizer_version="1.0.0",
    )
    save_manifest(manifest, paths.manifest_json)


def _passesCanonicalAdoptionGate(  # noqa: N802
    console: Console,
    paths: PaperPaths,
    paper_id: str,
    storage_id: str,
    pdf_sha256: str,
    canonical_md: str,
    minimum_body_chars: int,
) -> bool:
    """Validate a Canonical candidate before any final adoption writes."""
    try:
        validateCanonicalAdoption(
            canonical_md,
            expected_paper_id=paper_id,
            expected_storage_id=storage_id,
            minimum_body_chars=minimum_body_chars,
        )
    except CanonicalAdoptionGateError as exc:
        _save_incomplete_local_pdf_manifest(
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            PaperState.NEEDS_REVIEW,
        )
        console.print("[red]❌ Canonical 采用前门禁失败[/red]")
        console.print(f"   error: {exc.code}")
        console.print(f"   reason: {exc.reason}")
        console.print(f"   message: {exc.message}")
        return False
    return True


def _validateReadyAssets(  # noqa: N802
    paths: PaperPaths, assets: tuple[str, ...]
) -> None:
    """Require every conversion asset to be a local, non-link regular file."""
    if not assets:
        return

    assets_root = paths.paper_dir / "assets"
    if isPathReparsePoint(assets_root) or not assets_root.is_dir():
        raise ValueError("conversion assets directory is missing or unsafe")

    for asset_path in assets:
        if not isinstance(asset_path, str) or not asset_path.startswith("./assets/"):
            raise ValueError("conversion asset path is invalid")
        relative_path = asset_path.removeprefix("./assets/")
        path_parts = relative_path.split("/")
        if (
            not relative_path
            or "\\" in asset_path
            or any(
                part in {"", ".", ".."} or ":" in part
                for part in path_parts
            )
        ):
            raise ValueError("conversion asset path is invalid")

        parent_dir = assets_root
        for part in path_parts[:-1]:
            parent_dir = parent_dir / part
            if isPathReparsePoint(parent_dir) or not parent_dir.is_dir():
                raise ValueError("conversion asset parent is missing or unsafe")
        target_path = assets_root.joinpath(*path_parts)
        if isPathReparsePoint(target_path):
            raise ValueError("conversion asset target is unsafe")
        try:
            target_mode = os.stat(target_path, follow_symlinks=False).st_mode
        except FileNotFoundError as exc:
            raise ValueError("conversion asset target is missing") from exc
        if not stat.S_ISREG(target_mode):
            raise ValueError("conversion asset target must be a regular file")


def _stateForConversionFailure(error_code: str) -> PaperState:  # noqa: N802
    """Keep local-PDF and Zotero-PDF conversion failure states aligned."""
    blocked_codes = {
        "visual_model_required",
        "visual_model_invalid",
        "visual_model_unsupported",
        "visual_auto_routing_unavailable",
        "visual_host_capability_missing",
        "visual_subagent_capability_missing",
        "visual_agent_host_unavailable",
    }
    retryable_codes = {
        "visual_progress_failed",
        "visual_transient_failure_exhausted",
    }
    review_codes = {
        "visual_auto_audit_result_invalid",
        "visual_boundary_review_invalid",
        "visual_quality_blocked",
        "visual_re_review_invalid",
        "visual_worker_result_invalid",
    }
    is_visual_capability_error = (
        error_code.startswith("visual_") and "capability" in error_code
    )
    if error_code in blocked_codes or is_visual_capability_error:
        return PaperState.BLOCKED
    if error_code in retryable_codes:
        return PaperState.FAILED_RETRYABLE
    if error_code in review_codes:
        return PaperState.NEEDS_REVIEW
    return PaperState.FAILED_PERMANENT


def _progressPdfConversionForIngest(  # noqa: N802
    source_pdf: Path,
    conversion_config: PdfConversionConfig,
    accept_visual_warnings: bool,
    re_review: bool = False,
) -> PdfConversionOutcome:
    """Preserve the legacy progress seam unless acceptance or re-review is explicit."""
    if re_review:
        return progressPdfConversion(
            source_pdf,
            conversion_config,
            accept_visual_warnings=accept_visual_warnings,
            re_review=True,
        )
    if accept_visual_warnings:
        return progressPdfConversion(
            source_pdf,
            conversion_config,
            accept_visual_warnings=True,
        )
    return progressPdfConversion(source_pdf, conversion_config)


def _candidateFromConversionOutcome(  # noqa: N802
    console: Console,
    paths: PaperPaths,
    paper_id: str,
    storage_id: str,
    pdf_sha256: str,
    conversion_outcome: PdfConversionOutcome,
) -> str | None:
    """Apply the shared conversion quality gate and return only adoptable Markdown."""
    if isinstance(conversion_outcome, AgentActionRequiredOutcome):
        _save_incomplete_local_pdf_manifest(
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            PaperState.BLOCKED,
        )
        task_package = conversion_outcome.task_package.resolve()
        console.print("[yellow]⚠ PDF 视觉转换等待 Agent Host 继续[/yellow]")
        console.print(f"   task_package: {task_package}")
        console.print("   需 Agent Host 继续处理此视觉转换任务。")
        return None

    if isinstance(conversion_outcome, NeedsConfirmationOutcome):
        _save_incomplete_local_pdf_manifest(
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            PaperState.NEEDS_REVIEW,
        )
        console.print("[yellow]⚠ PDF 转换存在待确认警告，未自动采用[/yellow]")
        for warning in conversion_outcome.warnings:
            console.print(f"   - {warning}")
        return None

    if isinstance(conversion_outcome, FailedConversionOutcome):
        _save_incomplete_local_pdf_manifest(
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            _stateForConversionFailure(conversion_outcome.error.code),
        )
        console.print("[red]❌ PDF 转换未完成[/red]")
        console.print(
            f"   {conversion_outcome.error.code}: "
            f"{conversion_outcome.error.message}"
        )
        return None

    if not isinstance(conversion_outcome, ReadyConversionOutcome):
        raise RuntimeError("未知的 PDF 转换结果")

    try:
        _validateReadyAssets(paths, conversion_outcome.assets)
    except ValueError as exc:
        _save_incomplete_local_pdf_manifest(
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            PaperState.NEEDS_REVIEW,
        )
        console.print("[red]❌ PDF 转换资产未通过采用校验[/red]")
        console.print(f"   原因: {exc}")
        return None
    return conversion_outcome.markdown


def _cleanupVisualRunsAfterAdoption(  # noqa: N802
    console: Console,
    paths: PaperPaths,
    conversion_config: PdfConversionConfig,
    primary_adoption_succeeded: bool,
) -> None:
    """Best-effort cleanup only after the primary visual adoption succeeds."""
    if conversion_config.visual.mode == "off" or not primary_adoption_succeeded:
        return
    try:
        cleanupReadyVisualRuns(paths.paper_dir)
    except Exception as exc:
        console.print("[yellow]⚠ 视觉临时运行清理失败，已保留现场[/yellow]")
        console.print(f"   原因: {exc}")


def _create_zotero_adapter(ctx):
    """从配置和环境变量创建 ZoteroAdapter

    Returns:
        ZoteroAdapter 实例

    Raises:
        click.Abort: 如果 zotero_mcp 不可用或配置错误
    """
    from paperbase.adapters.zotero_adapter import (
        ZoteroAdapter,
        ZoteroUnavailable,
    )

    console = Console()
    base_dir = ctx.obj["base_dir"]

    # Read config
    config_path = base_dir / "config" / "paperbase.yaml"
    local_mode = True
    api_key = None
    library_id = None
    library_type = "user"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            zotero_config = config.get("adapters", {}).get("zotero", {})
            local_mode = zotero_config.get("local_mode", True)

    # Override with environment variables
    api_key = os.getenv("ZOTERO_API_KEY", api_key)
    library_id = os.getenv("ZOTERO_LIBRARY_ID", library_id)
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", library_type)

    try:
        return ZoteroAdapter(
            local_mode=local_mode,
            api_key=api_key,
            library_id=library_id,
            library_type=library_type,
        )
    except (ZoteroUnavailable, ValueError) as e:
        console.print(f"[red]❌ Zotero 初始化失败: {e}[/red]")
        raise click.Abort()


def _create_paper_from_metadata(base_dir, metadata_dict, paper_id, storage_id, source_provider, no_graph):
    """从元数据创建论文（无 PDF 场景）

    Args:
        base_dir: 知识库根目录
        metadata_dict: 元数据字典（title, authors, year, doi, abstract, url）
        paper_id: 论文 ID
        storage_id: 存储 ID
        source_provider: 来源标识（如 "zotero"）
        no_graph: 是否跳过图谱更新

    Returns:
        PaperPaths 对象
    """
    console = Console()

    # Create markdown from metadata
    authors_str = ", ".join(metadata_dict.get("authors", ["Unknown"]))
    abstract = metadata_dict.get("abstract", "No abstract available.")

    candidate_md = f"""# {metadata_dict.get("title", "Untitled")}

## Abstract

{abstract}

## Metadata

- **Authors**: {authors_str}
- **Year**: {metadata_dict.get("year", "N/A")}
- **DOI**: {metadata_dict.get("doi", "N/A")}
- **URL**: {metadata_dict.get("url", "N/A")}
- **Source**: {source_provider}
"""

    # Normalize paper
    paper_metadata = normalize_paper(
        candidate_md=candidate_md,
        metadata=metadata_dict,
        paper_id=paper_id,
        storage_id=storage_id,
        source_provider=source_provider
    )
    if metadata_dict.get("abstract"):
        paper_metadata.abstract = metadata_dict["abstract"]
    if metadata_dict.get("doi") or metadata_dict.get("arxiv"):
        paper_metadata.identifiers = PaperIdentifiers(
            doi=metadata_dict.get("doi"),
            arxiv=metadata_dict.get("arxiv"),
        )

    # Create directory structure
    paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
    paths.create_directories()

    # Generate canonical markdown
    metadata_dict_full = paper_metadata.model_dump(mode="json", exclude_none=True)
    canonical_md = generate_canonical_markdown(metadata_dict_full, candidate_md)
    paths.paper_md.write_text(canonical_md, encoding="utf-8")
    canonical_sha256 = sha256_string(canonical_md)

    # Generate chunks
    chunks = generate_chunks(canonical_md, paper_id)
    if chunks:
        write_chunks_jsonl(chunks, paths.chunks_jsonl)

    # Save manifest
    manifest = create_manifest(paper_id, storage_id)
    manifest.state = PaperState.NORMALIZED
    manifest.canonical_md = CanonicalMD(
        path=f"../{storage_id}.md",
        sha256=canonical_sha256,
        schema_version="1.0"
    )
    manifest.pipeline = PipelineInfo(
        converter=source_provider,
        converter_version="0.6.0" if source_provider == "zotero" else "unknown",
        normalizer_version="1.0.0"
    )
    save_manifest(manifest, paths.manifest_json)

    # Register
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
        doi=metadata_dict.get("doi")
    )
    registry.close()

    # Update index if needed
    if not no_graph:
        console.print("\n[yellow]更新全文检索索引...[/yellow]")
        try:
            from paperbase.core.search_engine import SearchEngine
            index_path = base_dir / "index" / "fts.db"
            library_path = base_dir / "library" / "papers"
            with SearchEngine(index_path, library_path) as engine:
                engine.build_index()
            console.print("[green]✓ 索引更新完成[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")

    return paths


def _ingest_online(
    ctx,
    query: str,
    no_graph: bool,
    headless_graph: bool,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
):
    console = Console()
    base_dir = ctx.obj["base_dir"]

    if re_review:
        # DOI/arXiv 等在线标识符的重审：用查询解析出的既有论文重入其视觉转换 run
        paper_id = normalize_paper_id(query)
        paths = PaperPaths(storage_id=generate_storage_id(paper_id), base_dir=base_dir)
        if not paths.source_pdf.exists():
            console.print(f"[red]❌ --re-review 未找到论文 {paper_id} 已保存的源 PDF[/red]")
            console.print("   重审仅适用于已摄入并保存过源 PDF 的论文；首次摄入请去掉 --re-review")
            raise click.Abort()
        # 预检身份一致：_ingest_local_pdf 会从 PDF 元数据重新推导 paper_id，
        # 若与查询解析的 paper_id 不同会落到新的论文目录，重审就找不到既有 run
        metadata = extract_pdf_metadata(paths.source_pdf)
        if metadata.get("doi"):
            derived_id = normalize_paper_id(metadata["doi"])
        else:
            derived_id = normalize_paper_id(f"fallback:{sha256_file(paths.source_pdf)[:16]}")
        if derived_id != paper_id:
            console.print(
                f"[red]❌ --re-review 身份不一致：源 PDF 元数据指向 {derived_id}，"
                f"与查询解析的 {paper_id} 不同[/red]"
            )
            console.print("   请改用与该论文摄入时相同的标识符（或 --file 指向同一 PDF）重审")
            raise click.Abort()
        console.print(f"[dim]--re-review: 重入 {paper_id} 的视觉转换 run[/dim]")
        return _ingest_local_pdf(
            ctx,
            paths.source_pdf,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            re_review=True,
        )

    try:
        fetched = PaperFetchAdapter().fetch(query)
    except PaperFetchUnavailable as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc

    result = ingest_fetched_paper(base_dir=base_dir, fetched=fetched)
    console.print("[green]✓ 论文已成功添加到知识库[/green]")
    console.print(f"论文标识: {result.paper_id}")

    if not no_graph:
        console.print("[yellow]更新全文检索索引...[/yellow]")
        try:
            from paperbase.core.search_engine import SearchEngine
            index_path = base_dir / "index" / "fts.db"
            library_path = base_dir / "library" / "papers"
            with SearchEngine(index_path, library_path) as engine:
                engine.build_index()
            console.print("[green]✓ 索引更新完成[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
            console.print("   可稍后手动运行: [cyan]paperbase index[/cyan]")

    if headless_graph:
        console.print("[yellow]更新知识图谱...[/yellow]")
        try:
            from paperbase.cli.commands.graph import update as graph_update
            ctx.invoke(graph_update, force=False)
        except Exception as e:
            console.print(f"[yellow]⚠ 知识图谱更新失败: {e}[/yellow]")
            console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
    elif no_graph:
        console.print("[dim]跳过语义图谱更新（--no-graph）[/dim]")
    else:
        _print_agent_graph_handoff(console)

    return result


def _ingest_local_pdf(
    ctx,
    pdf_path: Path,
    no_graph: bool,
    headless_graph: bool,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
):
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
            # Fallback: 使用 PDF 内容哈希（支持任意文件名）
            pdf_hash = sha256_file(pdf_path)
            paper_id = f"fallback:{pdf_hash[:16]}"
            paper_id = normalize_paper_id(paper_id)

        storage_id = generate_storage_id(paper_id)
        console.print(f"   paper_id: {paper_id}")
        console.print(f"   storage_id: {storage_id}")

        # 查重检查（--re-review 不短路：允许重入既有视觉转换 run）
        if re_review:
            console.print("[dim]--re-review: 跳过查重短路，重入既有视觉转换 run[/dim]")
        registry_path = base_dir / "registry" / "papers.db"
        if registry_path.exists() and not re_review:
            registry = PaperRegistry(registry_path)

            # 检查 DOI 重复
            if metadata.get("doi"):
                existing = registry.find_by_doi(metadata["doi"])
                if existing:
                    registry.close()
                    console.print(f"[yellow]⚠️  论文已存在（DOI 重复）[/yellow]")
                    console.print(f"   Paper ID: {existing['paper_id']}")
                    console.print(f"   标题: {existing.get('title', 'N/A')}")
                    console.print("[dim]提示：使用不同的 DOI 或删除已存在的论文[/dim]")
                    raise click.Abort()

            # 检查标题重复（Fallback）
            if metadata.get("title"):
                existing = registry.find_by_title(metadata["title"])
                if existing:
                    registry.close()
                    console.print(f"[yellow]⚠️  论文可能已存在（标题相同）[/yellow]")
                    console.print(f"   Paper ID: {existing['paper_id']}")
                    console.print(f"   标题: {existing.get('title', 'N/A')}")
                    console.print("[dim]提示：如果确实是不同论文，请确保标题不同[/dim]")
                    raise click.Abort()

            registry.close()

        # Step 3: 创建目录结构
        console.print("[yellow]3. 创建存储目录...[/yellow]")
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        paths.create_directories()

        # Step 4: 复制 PDF 到 source（--re-review 重入时源 PDF 已在位，跳过自拷贝）
        console.print("[yellow]4. 保存源 PDF...[/yellow]")
        if pdf_path.resolve() != paths.source_pdf.resolve():
            shutil.copy2(pdf_path, paths.source_pdf)
        pdf_sha256 = sha256_file(paths.source_pdf)
        console.print(f"   SHA256: {pdf_sha256[:16]}...")

        # Step 5: 推进 PDF 转换质量门
        console.print("[yellow]5. 转换为 Markdown...[/yellow]")
        try:
            paperbase_config = load_config(
                base_dir / "config" / "paperbase.yaml"
            )
            conversion_config = paperbase_config.conversion.pdf
            minimum_body_chars = (
                paperbase_config.graph.get_minimum_canonical_body_chars()
            )
            conversion_outcome = _progressPdfConversionForIngest(
                paths.source_pdf,
                conversion_config,
                accept_visual_warnings,
                re_review,
            )
        except Exception as exc:
            _save_incomplete_local_pdf_manifest(
                paths,
                paper_id,
                storage_id,
                pdf_sha256,
                PaperState.FAILED_PERMANENT,
            )
            console.print("[red]❌ PDF 转换质量门初始化失败[/red]")
            console.print(f"   原因: {exc}")
            return

        candidate_md = _candidateFromConversionOutcome(
            console,
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            conversion_outcome,
        )
        if candidate_md is None:
            return
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
        if not _passesCanonicalAdoptionGate(
            console,
            paths,
            paper_id,
            storage_id,
            pdf_sha256,
            canonical_md,
            minimum_body_chars,
        ):
            return
        paths.paper_md.write_text(canonical_md, encoding="utf-8")
        canonical_sha256 = sha256_string(canonical_md)

        # Step 8: 生成文本分块
        console.print("[yellow]8. 生成文本分块...[/yellow]")
        chunks = generate_chunks(canonical_md, paper_id)
        if chunks:
            write_chunks_jsonl(chunks, paths.chunks_jsonl)
            console.print(f"   ✓ 生成 {len(chunks)} 个文本块")

        # Step 9: 保存元数据
        console.print("[yellow]9. 保存元数据...[/yellow]")
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

        # Step 10: 记录到知识库
        console.print("[yellow]10. 记录到知识库...[/yellow]")
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

        # Step 11: 更新全文检索索引和知识图谱（可选）
        primary_adoption_succeeded = True
        if not no_graph:
            console.print("\n[yellow]11. 更新全文检索索引...[/yellow]")
            try:
                from paperbase.core.search_engine import SearchEngine
                index_path = base_dir / "index" / "fts.db"
                library_path = base_dir / "library" / "papers"
                with SearchEngine(index_path, library_path) as engine:
                    engine.build_index()
                console.print("[green]   ✓ 全文检索索引更新完成[/green]")
            except Exception as e:
                primary_adoption_succeeded = False
                console.print(f"[yellow]   ⚠ 索引更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase index[/cyan]")

            if headless_graph:
                console.print("\n[yellow]12. 更新知识图谱...[/yellow]")
                try:
                    from paperbase.cli.commands.graph import update as graph_update
                    ctx.invoke(graph_update, force=False)
                except Exception as e:
                    console.print(f"[yellow]   ⚠ 知识图谱更新失败: {e}[/yellow]")
                    console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
            else:
                _print_agent_graph_handoff(console)
        else:
            console.print("\n[dim]跳过索引更新（--no-graph）[/dim]")
            console.print("   稍后可运行: [cyan]paperbase index[/cyan] 和 [cyan]paperbase graph update[/cyan]")

        _cleanupVisualRunsAfterAdoption(
            console,
            paths,
            conversion_config,
            primary_adoption_succeeded,
        )

        # 摄入流程完成
        console.print(f"\n[green]✓ 摄入完成[/green]")
        console.print(f"   论文已成功添加到知识库")

    except Exception as e:
        console.print(f"\n[red]❌ 摄入失败: {e}[/red]")
        raise


def _ingest_from_zotero(
    ctx,
    item_key: str,
    no_graph: bool,
    headless_graph: bool,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
):
    """从 Zotero 导入单篇论文

    Args:
        ctx: Click 上下文
        item_key: Zotero item key
        no_graph: 是否跳过图谱更新

    Returns:
        str: "success" 表示成功导入，"skipped" 表示已存在跳过
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    # 解析 item_key（支持 URI 格式）
    # 格式: zotero://select/library/items/4KJIR58A → 4KJIR58A
    if item_key.startswith("zotero://"):
        if "/items/" in item_key:
            actual_key = item_key.split("/items/")[-1].strip()
            console.print(f"[dim]检测到 Zotero URI，提取 key: {actual_key}[/dim]")
            item_key = actual_key
        else:
            console.print(f"[red]❌ 无效的 Zotero URI 格式: {item_key}[/red]")
            console.print("[yellow]正确格式示例: zotero://select/library/items/ABCD1234[/yellow]")
            raise click.Abort()

    console.print(f"[cyan]从 Zotero 导入论文:[/cyan] {item_key}")

    # 初始化 ZoteroAdapter
    adapter = _create_zotero_adapter(ctx)

    try:
        # Step 1: 获取 Zotero 条目
        console.print("[yellow]1. 获取 Zotero 条目...[/yellow]")
        item = adapter.fetch_item(item_key)
        console.print(f"   标题: {item.title}")
        console.print(f"   作者: {', '.join(item.authors) if item.authors else 'N/A'}")
        console.print(f"   年份: {item.year or 'N/A'}")
        console.print(f"   类型: {item.item_type}")

        # Step 2: 探测本地 PDF，并在身份生成前提取可用标识符
        pdf_path = None
        pdf_metadata = {}
        console.print("[yellow]2. 探测本地 PDF 附件...[/yellow]")
        try:
            pdf_path_str = adapter.get_pdf_path(item_key)
            if pdf_path_str:
                pdf_path = Path(pdf_path_str)
                console.print(f"[green]   ✓ 找到 PDF: {pdf_path.name}[/green]")
                if pdf_path.exists():
                    pdf_metadata = extract_pdf_metadata(pdf_path)
            else:
                console.print("[yellow]   ⚠ 无法获取 PDF 路径（可能使用 Web API 模式）[/yellow]")
                console.print("[dim]   降级为元数据导入[/dim]")
        except Exception as e:
            console.print(f"[yellow]   ⚠ 获取或解析 PDF 失败: {e}[/yellow]")
            console.print("[dim]   降级为元数据导入[/dim]")
            pdf_path = None
            pdf_metadata = {}

        pdf_doi = pdf_metadata.get("doi")
        pdf_arxiv = pdf_metadata.get("arxiv_id") or pdf_metadata.get("arxiv")

        # Step 3: 生成 paper_id
        console.print("[yellow]3. 生成 paper_id...[/yellow]")
        if item.doi:
            paper_id = normalize_paper_id(item.doi)
        elif item.arxiv_id:
            paper_id = normalize_paper_id(f"arxiv:{item.arxiv_id}")
        elif pdf_doi:
            paper_id = normalize_paper_id(pdf_doi)
        elif pdf_arxiv:
            paper_id = normalize_paper_id(f"arxiv:{pdf_arxiv}")
        else:
            # Fallback: 使用 Zotero key
            paper_id = normalize_paper_id(f"zotero:{item_key}")

        storage_id = generate_storage_id(paper_id)
        console.print(f"   paper_id: {paper_id}")
        console.print(f"   storage_id: {storage_id}")

        merged_doi = item.doi or pdf_doi

        # Step 4: 查重检查（--re-review 且有本地 PDF 时不短路，允许重入视觉转换 run）
        console.print("[yellow]4. 查重检查...[/yellow]")
        registry_path = base_dir / "registry" / "papers.db"
        re_review_reentry = re_review and pdf_path is not None and pdf_path.exists()
        if re_review_reentry:
            console.print("[dim]--re-review: 论文已存在时重入其视觉转换 run[/dim]")
        if registry_path.exists() and not re_review_reentry:
            registry = PaperRegistry(registry_path)

            # 检查 DOI 重复
            if merged_doi:
                existing = registry.find_by_doi(merged_doi)
                if existing:
                    registry.close()
                    console.print(f"[yellow]⚠️  论文已存在（DOI 重复）[/yellow]")
                    console.print(f"   Paper ID: {existing['paper_id']}")
                    console.print(f"   标题: {existing.get('title', 'N/A')}")
                    console.print("[dim]跳过此论文[/dim]")
                    return "skipped"

            # 检查标题重复
            if item.title:
                existing = registry.find_by_title(item.title)
                if existing:
                    registry.close()
                    console.print(f"[yellow]⚠️  论文可能已存在（标题相同）[/yellow]")
                    console.print(f"   Paper ID: {existing['paper_id']}")
                    console.print(f"   标题: {existing.get('title', 'N/A')}")
                    console.print("[dim]跳过此论文[/dim]")
                    return "skipped"

            registry.close()
        # Step 5: 如果有 PDF，走完整 PDF 导入流程
        if pdf_path and pdf_path.exists():
            console.print("[yellow]5. 使用完整 PDF 导入流程...[/yellow]")

            # 直接调用 _ingest_local_pdf 的核心逻辑
            try:
                # 合并 Zotero 元数据和 PDF 元数据（Zotero 优先）
                merged_metadata = {
                    "title": item.title or pdf_metadata.get("title", "Untitled"),
                    "authors": item.authors if item.authors else pdf_metadata.get("authors", ["Unknown"]),
                    "year": item.year or pdf_metadata.get("year"),
                    "doi": item.doi or pdf_metadata.get("doi"),
                    "arxiv": item.arxiv_id or pdf_arxiv,
                    "abstract": item.abstract or pdf_metadata.get("abstract", ""),
                }

                console.print("[yellow]   5.2. 创建存储目录...[/yellow]")
                paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
                paths.create_directories()

                console.print("[yellow]   5.3. 保存源 PDF...[/yellow]")
                shutil.copy2(pdf_path, paths.source_pdf)
                pdf_sha256 = sha256_file(paths.source_pdf)

                console.print("[yellow]   5.4. 转换为 Markdown...[/yellow]")
                try:
                    paperbase_config = load_config(
                        base_dir / "config" / "paperbase.yaml"
                    )
                    conversion_config = paperbase_config.conversion.pdf
                    minimum_body_chars = (
                        paperbase_config.graph.get_minimum_canonical_body_chars()
                    )
                    conversion_outcome = _progressPdfConversionForIngest(
                        paths.source_pdf,
                        conversion_config,
                        accept_visual_warnings,
                        re_review,
                    )
                except Exception as exc:
                    _save_incomplete_local_pdf_manifest(
                        paths,
                        paper_id,
                        storage_id,
                        pdf_sha256,
                        PaperState.FAILED_PERMANENT,
                    )
                    console.print("[red]❌ PDF 转换质量门初始化失败[/red]")
                    console.print(f"   原因: {exc}")
                    return "incomplete"

                candidate_md = _candidateFromConversionOutcome(
                    console,
                    paths,
                    paper_id,
                    storage_id,
                    pdf_sha256,
                    conversion_outcome,
                )
                if candidate_md is None:
                    return "incomplete"
                console.print(f"      长度: {len(candidate_md)} 字符")

                console.print("[yellow]   5.5. 整理论文信息...[/yellow]")
                paper_metadata = normalize_paper(
                    candidate_md=candidate_md,
                    metadata=merged_metadata,
                    paper_id=paper_id,
                    storage_id=storage_id,
                    source_provider="zotero+markitdown"
                )
                if merged_metadata.get("abstract"):
                    paper_metadata.abstract = merged_metadata["abstract"]
                if merged_metadata.get("doi") or merged_metadata.get("arxiv"):
                    paper_metadata.identifiers = PaperIdentifiers(
                        doi=merged_metadata.get("doi"),
                        arxiv=merged_metadata.get("arxiv"),
                    )

                console.print("[yellow]   5.6. 生成标准格式文档...[/yellow]")
                metadata_dict = paper_metadata.model_dump(mode="json", exclude_none=True)
                canonical_md = generate_canonical_markdown(metadata_dict, candidate_md)
                if not _passesCanonicalAdoptionGate(
                    console,
                    paths,
                    paper_id,
                    storage_id,
                    pdf_sha256,
                    canonical_md,
                    minimum_body_chars,
                ):
                    return "incomplete"
                paths.paper_md.write_text(canonical_md, encoding="utf-8")
                canonical_sha256 = sha256_string(canonical_md)

                console.print("[yellow]   5.7. 生成文本分块...[/yellow]")
                chunks = generate_chunks(canonical_md, paper_id)
                if chunks:
                    write_chunks_jsonl(chunks, paths.chunks_jsonl)
                    console.print(f"      ✓ 生成 {len(chunks)} 个文本块")

                console.print("[yellow]   5.8. 保存元数据...[/yellow]")
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
                    converter="zotero+markitdown",
                    converter_version="0.6.0+markitdown-0.0.1",
                    normalizer_version="1.0.0"
                )
                save_manifest(manifest, paths.manifest_json)

                console.print("[yellow]   5.9. 记录到知识库...[/yellow]")
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
                    doi=merged_metadata.get("doi")
                )
                registry.close()

                console.print(f"\n[green]✓ 论文（含 PDF 全文）已保存到知识库[/green]")
                console.print(f"   路径: {paths.paper_dir}")

                # 更新索引
                primary_adoption_succeeded = True
                if not no_graph:
                    console.print("\n[yellow]更新全文检索索引...[/yellow]")
                    try:
                        from paperbase.core.search_engine import SearchEngine
                        index_path = base_dir / "index" / "fts.db"
                        library_path = base_dir / "library" / "papers"
                        with SearchEngine(index_path, library_path) as engine:
                            engine.build_index()
                        console.print("[green]✓ 索引更新完成[/green]")
                    except Exception as e:
                        primary_adoption_succeeded = False
                        console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")

                    if headless_graph:
                        console.print("[yellow]更新知识图谱...[/yellow]")
                        try:
                            from paperbase.cli.commands.graph import update as graph_update
                            ctx.invoke(graph_update, force=False)
                        except Exception as e:
                            console.print(f"[yellow]⚠ 知识图谱更新失败: {e}[/yellow]")
                    else:
                        _print_agent_graph_handoff(console)

                _cleanupVisualRunsAfterAdoption(
                    console,
                    paths,
                    conversion_config,
                    primary_adoption_succeeded,
                )

                console.print(f"\n[green]✓ 摄入完成（含 PDF 全文）[/green]")
                return "success"

            except Exception as e:
                console.print(f"[red]✗ PDF 处理失败: {e}[/red]")
                console.print("[yellow]降级为元数据导入...[/yellow]")
                # 继续执行元数据导入流程

        # Step 6: 仅元数据导入（无 PDF 或 PDF 处理失败）
        console.print("[yellow]5. 摄入元数据...[/yellow]")
        # 构造元数据字典
        metadata_dict = {
            "title": item.title or pdf_metadata.get("title", "Untitled"),
            "authors": item.authors if item.authors else pdf_metadata.get("authors", ["Unknown"]),
            "year": item.year or pdf_metadata.get("year"),
            "doi": item.doi or pdf_doi,
            "arxiv": item.arxiv_id or pdf_arxiv,
            "abstract": item.abstract or pdf_metadata.get("abstract", ""),
            "url": item.url,
        }

        # 使用公共函数创建论文
        paths = _create_paper_from_metadata(
            base_dir=base_dir,
            metadata_dict=metadata_dict,
            paper_id=paper_id,
            storage_id=storage_id,
            source_provider="zotero",
            no_graph=no_graph
        )

        console.print(f"\n[green]✓ 论文元数据已保存到知识库[/green]")
        console.print(f"   路径: {paths.paper_dir}")

        if headless_graph:
            console.print("[yellow]更新知识图谱...[/yellow]")
            try:
                from paperbase.cli.commands.graph import update as graph_update
                ctx.invoke(graph_update, force=False)
            except Exception as e:
                console.print(f"[yellow]⚠ 知识图谱更新失败: {e}[/yellow]")
        elif not no_graph:
            _print_agent_graph_handoff(console)

        console.print(f"\n[green]✓ 摄入完成[/green]")
        return "success"

    except Exception as e:
        console.print(f"\n[red]❌ 摄入失败: {e}[/red]")
        raise


def _ingest_zotero_recent(
    ctx,
    limit: int,
    no_graph: bool,
    headless_graph: bool,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
):
    """从 Zotero 批量导入最近论文

    Args:
        ctx: Click 上下文
        limit: 导入数量
        no_graph: 是否跳过图谱更新
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print(f"[cyan]从 Zotero 批量导入最近 {limit} 篇论文[/cyan]\n")

    # 初始化 ZoteroAdapter
    adapter = _create_zotero_adapter(ctx)

    try:
        # 获取最近论文列表
        console.print("[yellow]获取 Zotero 论文列表...[/yellow]")
        items = adapter.list_recent(limit)
        console.print(f"[cyan]找到 {len(items)} 篇论文[/cyan]\n")

        if not items:
            console.print("[yellow]没有找到论文[/yellow]")
            return

        # 逐个导入（每篇传入 no_graph=True）
        success_count = 0
        skip_count = 0
        failed_count = 0

        for i, item in enumerate(items, 1):
            # 显示标题（截断过长）
            display_title = item.title[:60] + "..." if len(item.title) > 60 else item.title
            console.print(f"[cyan][{i}/{len(items)}] {display_title}[/cyan]")

            try:
                # 调用单篇导入函数（强制 no_graph=True）
                result = _ingest_from_zotero(
                    ctx,
                    item.key,
                    no_graph=True,
                    headless_graph=False,
                    accept_visual_warnings=accept_visual_warnings,
                    **_reReviewKwargs(re_review),
                )
                if result == "success":
                    success_count += 1
                elif result == "skipped":
                    skip_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                # 单篇失败不影响其他论文
                console.print(f"[red]✗ 失败: {e}[/red]")
                failed_count += 1

            console.print()  # 空行分隔

        # 最终统计
        console.print(f"[cyan]批量导入完成[/cyan]")
        console.print(f"  成功: {success_count} 篇")
        console.print(f"  跳过: {skip_count} 篇（已存在）")
        console.print(f"  失败: {failed_count} 篇")

        # 统一更新索引（仅当有成功导入且未禁用时）
        if not no_graph and success_count > 0:
            console.print("\n[yellow]更新全文检索索引...[/yellow]")
            try:
                from paperbase.core.search_engine import SearchEngine
                index_path = base_dir / "index" / "fts.db"
                library_path = base_dir / "library" / "papers"
                with SearchEngine(index_path, library_path) as engine:
                    engine.build_index()
                console.print("[green]✓ 全文检索索引更新完成[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase index[/cyan]")

            if headless_graph:
                console.print("\n[yellow]更新知识图谱...[/yellow]")
                try:
                    from paperbase.cli.commands.graph import update as graph_update
                    ctx.invoke(graph_update, force=False)
                except Exception as e:
                    console.print(f"[yellow]⚠ 知识图谱更新失败: {e}[/yellow]")
                    console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
            else:
                _print_agent_graph_handoff(console)
        elif no_graph:
            console.print("\n[dim]跳过索引更新（--no-graph）[/dim]")
            console.print("   稍后可运行: [cyan]paperbase index[/cyan] 和 [cyan]paperbase graph update[/cyan]")

    except Exception as e:
        console.print(f"[red]✗ 批量导入失败: {e}[/red]")
        raise


@click.command()
@click.argument("target", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, path_type=Path), help="本地 PDF 文件路径")
@click.option(
    "--accept-visual-warnings",
    is_flag=True,
    help="显式采用已完成视觉转换中的低风险警告",
)
@click.option(
    "--re-review",
    is_flag=True,
    help="重置 ready_to_adopt 视觉转换的边界审校并重新生成审校任务包（保留已完成的分块结果）",
)
@click.option("--no-graph", is_flag=True, help="跳过本次索引和图谱后续处理")
@click.option(
    "--headless-graph",
    is_flag=True,
    help="显式使用本地 LLM 执行 headless 图谱更新（备用路径）",
)
@click.option("--batch", type=click.Path(exists=True, path_type=Path), help="批量摄入文件列表（每行一个路径、DOI、URL 或标题）")
@click.option("--zotero-key", type=str, help="从 Zotero 导入指定 item key 的论文")
@click.option("--zotero-recent", type=int, metavar="N", help="从 Zotero 批量导入最近 N 篇论文")
@click.pass_context
def ingest(
    ctx,
    target: str | None,
    file_path: Path | None,
    accept_visual_warnings: bool,
    re_review: bool,
    no_graph: bool,
    headless_graph: bool,
    batch: Path | None,
    zotero_key: str | None,
    zotero_recent: int | None,
):
    """摄入论文：本地 PDF 或 DOI/URL/title"""
    console = Console()
    if no_graph and headless_graph:
        raise click.UsageError("--no-graph 和 --headless-graph 不能同时使用")


    # 互斥检查
    if sum([bool(target), bool(file_path), bool(batch), bool(zotero_key), bool(zotero_recent)]) > 1:
        console.print("[red]❌ 只能指定一个输入源：TARGET、--file、--batch、--zotero-key 或 --zotero-recent[/red]")
        raise click.Abort()

    if not target and not file_path and not batch and not zotero_key and not zotero_recent:
        console.print("[red]❌ 必须提供输入源：TARGET、--file、--batch、--zotero-key 或 --zotero-recent[/red]")
        raise click.Abort()

    # Zotero 批量模式
    if zotero_recent:
        _ingest_zotero_recent(
            ctx,
            zotero_recent,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return

    # Zotero 单篇模式
    if zotero_key:
        _ingest_from_zotero(
            ctx,
            zotero_key,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return

    # 批量模式
    if batch:
        _ingest_batch(
            ctx,
            batch,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return

    # 本地文件模式
    if file_path is not None:
        _ingest_local_pdf(
            ctx,
            file_path,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return

    if target and _target_is_local_file(target):
        _ingest_local_pdf(
            ctx,
            Path(target),
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return

    # 在线查询模式
    if target:
        _ingest_online(
            ctx,
            target,
            no_graph,
            headless_graph,
            accept_visual_warnings=accept_visual_warnings,
            **_reReviewKwargs(re_review),
        )
        return


def _ingest_batch(
    ctx,
    batch_file: Path,
    no_graph: bool,
    headless_graph: bool,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
):
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
                ctx.invoke(
                    ingest,
                    target=target,
                    accept_visual_warnings=accept_visual_warnings,
                    re_review=re_review,
                    no_graph=True,
                    headless_graph=False,
                    batch=None,
                )
                success_count += 1
            except Exception as e:
                console.print(f"[red]✗ 失败: {e}[/red]")
                failed_count += 1

            console.print()  # 空行分隔

        # 统计
        console.print(f"[cyan]批量摄入完成[/cyan]")
        console.print(f"  成功: {success_count} 篇")
        console.print(f"  失败: {failed_count} 篇")

        # 统一更新索引
        if not no_graph and success_count > 0:
            console.print("\n[yellow]更新全文检索索引...[/yellow]")
            try:
                from paperbase.core.search_engine import SearchEngine
                index_path = base_dir / "index" / "fts.db"
                library_path = base_dir / "library" / "papers"
                with SearchEngine(index_path, library_path) as engine:
                    engine.build_index()
                console.print("[green]✓ 全文检索索引更新完成[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
                console.print("   可稍后手动运行: [cyan]paperbase index[/cyan]")

            if headless_graph:
                console.print("\n[yellow]更新知识图谱...[/yellow]")
                try:
                    from paperbase.cli.commands.graph import update as graph_update
                    ctx.invoke(graph_update, force=False)
                except Exception as e:
                    console.print(f"[yellow]⚠ 知识图谱更新失败: {e}[/yellow]")
                    console.print("   可稍后手动运行: [cyan]paperbase graph update[/cyan]")
            else:
                _print_agent_graph_handoff(console)
        elif no_graph:
            console.print("\n[dim]跳过索引更新（--no-graph）[/dim]")
            console.print("   稍后可运行: [cyan]paperbase index[/cyan] 和 [cyan]paperbase graph update[/cyan]")

    except Exception as e:
        console.print(f"[red]✗ 批量摄入失败: {e}[/red]")
        raise
