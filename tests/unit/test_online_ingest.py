from pathlib import Path

from paperbase.adapters.paper_fetch_adapter import FetchedAsset, FetchedPaper, FetchedReference
from paperbase.core.online_ingest import ingest_fetched_paper
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

    paper_md = tmp_path / "library" / "papers" / result.storage_id / "paper.md"
    manifest_json = tmp_path / "library" / "papers" / result.storage_id / "manifest.json"
    references_jsonl = tmp_path / "library" / "papers" / result.storage_id / "references.jsonl"
    assets_dir = tmp_path / "library" / "papers" / result.storage_id / "assets"

    assert result.manifest.state == PaperState.NORMALIZED
    assert paper_md.exists()
    assert manifest_json.exists()
    assert references_jsonl.read_text(encoding="utf-8").count("\n") == 1
    assert (assets_dir / "figure-001.png").exists()
    assert "fulltext_provider: springer_html" in paper_md.read_text(encoding="utf-8")
