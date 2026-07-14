"""Persist online-fetched papers into the PaperBase library layout."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from paperbase.utils.timestamp import now_iso8601

from paperbase.adapters.paper_fetch_adapter import FetchedPaper
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import create_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import CanonicalMD, ManifestSchema, PaperState, PipelineInfo, SourceArtifact
from paperbase.core.chunker import generate_chunks, write_chunks_jsonl
from paperbase.schemas.paper import (
    PaperAuthor,
    PaperMetadata,
    PaperProvenance,
    PaperQuality,
    PaperReferences,
    PaperSource,
)
from paperbase.utils.hash import sha256_file, sha256_string
from paperbase.utils.markdown import generate_canonical_markdown


@dataclass(frozen=True)
class OnlineIngestResult:
    paper_id: str
    storage_id: str
    manifest: ManifestSchema


def _paper_id_for_fetched(fetched: FetchedPaper) -> str:
    if fetched.doi:
        return normalize_paper_id(fetched.doi)

    query_paper_id = normalize_paper_id(fetched.query)
    if not query_paper_id.startswith("fallback:"):
        return query_paper_id

    # Use full SHA256 hash to prevent collisions
    return normalize_paper_id(f"fallback:{sha256_string(fetched.title)}")


def _write_references(path: Path, fetched: FetchedPaper) -> None:
    with path.open("w", encoding="utf-8") as f:
        for reference in fetched.references:
            f.write(json.dumps(reference.__dict__, ensure_ascii=False) + "\n")


def _copy_assets(paths: PaperPaths, fetched: FetchedPaper, acquired_at: str) -> list[SourceArtifact]:
    """Copy assets with unified timestamp."""
    artifacts: list[SourceArtifact] = []
    for index, asset in enumerate(fetched.assets, start=1):
        if asset.source_path is None or not asset.source_path.exists():
            continue
        # Sanitize asset.kind to prevent directory traversal
        safe_kind = asset.kind.replace("/", "_").replace("\\", "_").replace("..", "_")
        suffix = asset.source_path.suffix or ".bin"
        target = paths.assets_dir / f"{safe_kind}-{index:03d}{suffix}"
        shutil.copy2(asset.source_path, target)

        # Verify write completed successfully by checking file size
        if target.exists() and target.stat().st_size != asset.source_path.stat().st_size:
            raise IOError(f"Asset copy incomplete: {target} size mismatch")

        artifacts.append(
            SourceArtifact(
                path=f"./assets/{target.name}",
                kind=asset.kind,
                provider=fetched.provider,
                original_url=asset.original_url,
                acquired_at=acquired_at,
                sha256=sha256_file(target),
            )
        )
    return artifacts


def ingest_fetched_paper(base_dir: Path, fetched: FetchedPaper) -> OnlineIngestResult:
    paper_id = _paper_id_for_fetched(fetched)

    # 查重检查
    registry_path = base_dir / "registry" / "papers.db"
    if registry_path.exists():
        registry = PaperRegistry(registry_path)

        # 检查 paper_id 是否已存在
        existing = registry.get_paper(paper_id)
        if existing:
            registry.close()
            raise ValueError(
                f"论文已存在: {paper_id}\n"
                f"标题: {existing.get('title', 'N/A')}\n"
                f"提示：论文已在知识库中，无需重复摄入"
            )

        # 检查 DOI 重复
        if fetched.doi:
            existing = registry.find_by_doi(fetched.doi)
            if existing and existing['paper_id'] != paper_id:
                registry.close()
                raise ValueError(
                    f"论文已存在（DOI 重复）: {existing['paper_id']}\n"
                    f"DOI: {fetched.doi}\n"
                    f"标题: {existing.get('title', 'N/A')}"
                )

        registry.close()

    storage_id = generate_storage_id(paper_id)
    paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
    paths.create_directories()

    # Use unified timestamp for all operations
    now = now_iso8601()

    asset_artifacts = _copy_assets(paths, fetched, now)
    _write_references(paths.references_jsonl, fetched)

    # Step 1: Generate preliminary canonical markdown without hash in metadata
    preliminary_metadata_dict = {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "storage_id": storage_id,
        "title": fetched.title,
        "authors": [{"name": name} for name in fetched.authors],
        "year": fetched.year,
        "abstract": fetched.abstract or "No abstract available",
        "source": {
            "discovery": "search",
            "fulltext_provider": fetched.provider,
            "original_url": fetched.original_url,
        },
        "provenance": {
            "ingested_at": now,
            "converter": {"name": "paper-fetch-skill", "version": "3.0.1"},
            "normalizer": {"name": "paperbase-online-ingest", "version": "1.0.0"},
            # canonical_content_sha256 will be added after computing hash
        },
        "references": {
            "path": "./references.jsonl",
            "count": len(fetched.references),
        },
        "quality": {
            "fulltext": fetched.has_fulltext,
            "metadata_complete": bool(fetched.title and fetched.authors),
            "references_parsed": bool(fetched.references),
            "needs_review": not fetched.has_fulltext,
        },
    }

    preliminary_canonical_md = generate_canonical_markdown(
        preliminary_metadata_dict,
        fetched.markdown,
    )

    # Step 2: Compute hash of the preliminary canonical markdown
    canonical_sha256 = sha256_string(preliminary_canonical_md)

    # Step 3: Create final metadata with the computed hash
    preliminary_metadata_dict["provenance"]["canonical_content_sha256"] = canonical_sha256

    # Step 4: Generate final canonical markdown and validate with PaperMetadata
    metadata = PaperMetadata(**preliminary_metadata_dict)
    canonical_md = generate_canonical_markdown(
        metadata.model_dump(mode="json", exclude_none=True),
        fetched.markdown,
    )
    paths.paper_md.write_text(canonical_md, encoding="utf-8")

    # Step 5: Generate chunks for full-text search
    chunks = generate_chunks(canonical_md, paper_id)
    if chunks:
        write_chunks_jsonl(chunks, paths.chunks_jsonl)

    manifest = create_manifest(paper_id, storage_id)
    manifest.state = PaperState.NORMALIZED
    manifest.canonical_md = CanonicalMD(
        path=f"../{storage_id}.md",
        sha256=sha256_string(canonical_md),
        schema_version="1.0",
    )
    manifest.pipeline = PipelineInfo(
        converter="paper-fetch-skill",
        converter_version="3.0.1",
        normalizer_version="1.0.0",
    )
    manifest.source_artifacts.extend(asset_artifacts)
    save_manifest(manifest, paths.manifest_json)

    registry_path = base_dir / "registry" / "papers.db"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=paper_id,
            storage_id=storage_id,
            state=manifest.state,
            title=fetched.title,
            authors=fetched.authors,
            year=fetched.year,
            doi=fetched.doi,
        )

    return OnlineIngestResult(
        paper_id=paper_id,
        storage_id=storage_id,
        manifest=manifest,
    )
