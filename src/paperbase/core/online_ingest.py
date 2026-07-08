"""Persist online-fetched papers into the PaperBase library layout."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from paperbase.adapters.paper_fetch_adapter import FetchedPaper
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import create_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import CanonicalMD, ManifestSchema, PaperState, PipelineInfo, SourceArtifact
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
    return normalize_paper_id(f"fallback:{sha256_string(fetched.title)[:16]}")


def _write_references(path: Path, fetched: FetchedPaper) -> None:
    with path.open("w", encoding="utf-8") as f:
        for reference in fetched.references:
            f.write(json.dumps(reference.__dict__, ensure_ascii=False) + "\n")


def _copy_assets(paths: PaperPaths, fetched: FetchedPaper) -> list[SourceArtifact]:
    acquired_at = datetime.now(UTC).isoformat()
    artifacts: list[SourceArtifact] = []
    for index, asset in enumerate(fetched.assets, start=1):
        if asset.source_path is None or not asset.source_path.exists():
            continue
        suffix = asset.source_path.suffix or ".bin"
        target = paths.assets_dir / f"{asset.kind}-{index:03d}{suffix}"
        shutil.copy2(asset.source_path, target)
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
    storage_id = generate_storage_id(paper_id)
    paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
    paths.create_directories()

    asset_artifacts = _copy_assets(paths, fetched)
    _write_references(paths.references_jsonl, fetched)

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id=paper_id,
        storage_id=storage_id,
        title=fetched.title,
        authors=[PaperAuthor(name=name) for name in fetched.authors],
        year=fetched.year,
        abstract=fetched.abstract or "No abstract available",
        source=PaperSource(
            discovery="search",
            fulltext_provider=fetched.provider,
            original_url=fetched.original_url,
        ),
        provenance=PaperProvenance(
            ingested_at=now,
            converter={"name": "paper-fetch-skill", "version": "3.0.1"},
            normalizer={"name": "paperbase-online-ingest", "version": "1.0.0"},
            canonical_content_sha256=sha256_string(fetched.markdown),
        ),
        references=PaperReferences(
            path="./references.jsonl",
            count=len(fetched.references),
        ),
        quality=PaperQuality(
            fulltext=fetched.has_fulltext,
            metadata_complete=bool(fetched.title and fetched.authors),
            references_parsed=bool(fetched.references),
            needs_review=not fetched.has_fulltext,
        ),
    )

    canonical_md = generate_canonical_markdown(
        metadata.model_dump(mode="json", exclude_none=True),
        fetched.markdown,
    )
    paths.paper_md.write_text(canonical_md, encoding="utf-8")

    manifest = create_manifest(paper_id, storage_id)
    manifest.state = PaperState.NORMALIZED
    manifest.canonical_md = CanonicalMD(
        path="./paper.md",
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
