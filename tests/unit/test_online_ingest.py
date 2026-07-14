from pathlib import Path

import pytest

from paperbase.adapters.paper_fetch_adapter import FetchedAsset, FetchedPaper, FetchedReference
from paperbase.core.online_ingest import ingest_fetched_paper
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def test_ingest_fetched_paper_writes_canonical_outputs(tmp_path: Path):
    source_asset = tmp_path / "source-figure.png"
    source_asset.write_bytes(b"fake image")

    fetched = FetchedPaper(
        query="10.1234/example",
        doi="10.1234/example",
        title="Example Paper",
        authors=["Ada Lovelace"],
        year=2026,
        abstract="This paper studies example systems.",
        markdown="# Example Paper\n\n![Figure 1](source-figure.png)\n",
        provider="springer_html",
        original_url="https://doi.org/10.1234/example",
        has_fulltext=True,
        content_kind="fulltext",
        references=[
            FetchedReference(
                raw="Lovelace A. Example work.",
                doi="10.1234/ref",
                title="Example work",
                year="2025",
            )
        ],
        assets=[
            FetchedAsset(
                kind="figure",
                heading="Figure 1",
                caption="Example figure.",
                source_path=source_asset,
                original_url="https://example.org/source-figure.png",
            )
        ],
    )

    result = ingest_fetched_paper(base_dir=tmp_path, fetched=fetched)

    paper_md = tmp_path / "library" / "papers" / f"{result.storage_id}.md"
    manifest_json = tmp_path / "library" / "papers" / result.storage_id / "manifest.json"
    references_jsonl = tmp_path / "library" / "papers" / result.storage_id / "references.jsonl"
    assets_dir = tmp_path / "library" / "papers" / result.storage_id / "assets"

    assert result.manifest.state == PaperState.NORMALIZED
    assert paper_md.exists()
    assert manifest_json.exists()
    assert references_jsonl.read_text(encoding="utf-8").count("\n") == 1
    assert (assets_dir / "figure-001.png").exists()
    assert "fulltext_provider: springer_html" in paper_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("query", ["arxiv:2301.07041", "2301.07041"])
def test_ingest_fetched_paper_uses_stable_arxiv_query_when_doi_is_missing(
    tmp_path: Path,
    query: str,
):
    fetched = FetchedPaper(
        query=query,
        doi=None,
        title="Paper Without DOI",
        authors=["Ada Lovelace"],
        year=2023,
        abstract="Abstract.",
        markdown="# Paper Without DOI",
        provider="arxiv",
        original_url="https://arxiv.org/abs/2301.07041",
        has_fulltext=True,
        content_kind="fulltext",
        references=[],
        assets=[],
    )

    result = ingest_fetched_paper(base_dir=tmp_path, fetched=fetched)

    assert result.paper_id == "arxiv:2301.07041"
    assert result.manifest.paper_id == "arxiv:2301.07041"
    with PaperRegistry(tmp_path / "registry" / "papers.db") as registry:
        registered = registry.get_paper("arxiv:2301.07041")
    assert registered is not None
    assert registered["paper_id"] == "arxiv:2301.07041"


def test_ingest_fetched_paper_keeps_title_fallback_for_ordinary_queries(tmp_path: Path):
    paper_ids = []
    for index, query in enumerate(["find this paper", "another title query"]):
        fetched = FetchedPaper(
            query=query,
            doi=None,
            title="Same Canonical Title",
            authors=["Ada Lovelace"],
            year=2023,
            abstract="Abstract.",
            markdown="# Same Canonical Title",
            provider="search",
            original_url=None,
            has_fulltext=False,
            content_kind="metadata_only",
            references=[],
            assets=[],
        )
        result = ingest_fetched_paper(base_dir=tmp_path / str(index), fetched=fetched)
        paper_ids.append(result.paper_id)

    assert paper_ids[0].startswith("fallback:")
    assert paper_ids[0] == paper_ids[1]
