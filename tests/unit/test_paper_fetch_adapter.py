from dataclasses import dataclass, field

from paperbase.adapters.paper_fetch_adapter import PaperFetchAdapter


@dataclass
class FakeMetadata:
    title: str = "Example Paper"
    authors: list[str] = field(default_factory=lambda: ["Ada Lovelace", "Grace Hopper"])
    abstract: str = "This paper studies example systems."
    journal: str = "Journal of Examples"
    published: str = "2026-07-08"
    keywords: list[str] = field(default_factory=lambda: ["examples", "systems"])
    landing_page_url: str = "https://doi.org/10.1234/example"


@dataclass
class FakeReference:
    raw: str
    doi: str | None = None
    title: str | None = None
    year: str | None = None


@dataclass
class FakeAsset:
    kind: str = "figure"
    heading: str = "Figure 1"
    caption: str = "Example figure."
    path: str = "downloaded/fig1.png"
    original_url: str = "https://example.org/fig1.png"


@dataclass
class FakeArticle:
    metadata: FakeMetadata = field(default_factory=FakeMetadata)
    references: list[FakeReference] = field(
        default_factory=lambda: [
            FakeReference(
                raw="Lovelace A. Example work.",
                doi="10.1234/ref",
                title="Example work",
                year="2025",
            )
        ]
    )
    assets: list[FakeAsset] = field(default_factory=lambda: [FakeAsset()])


@dataclass
class FakeEnvelope:
    doi: str = "10.1234/example"
    source: str = "springer_html"
    has_fulltext: bool = True
    content_kind: str = "fulltext"
    warnings: list[str] = field(default_factory=list)
    source_trail: list[str] = field(default_factory=lambda: ["crossref", "springer_html"])
    markdown: str = "# Example Paper\n\n## Abstract\n\nThis paper studies example systems."
    metadata: FakeMetadata = field(default_factory=FakeMetadata)
    article: FakeArticle = field(default_factory=FakeArticle)


def test_adapter_maps_fetch_envelope_to_fetched_paper():
    def fake_fetch_paper(query, *, modes, render):
        assert query == "10.1234/example"
        assert "markdown" in modes
        assert "metadata" in modes
        return FakeEnvelope()

    adapter = PaperFetchAdapter(fetch_paper_fn=fake_fetch_paper)
    fetched = adapter.fetch("10.1234/example")

    assert fetched.query == "10.1234/example"
    assert fetched.doi == "10.1234/example"
    assert fetched.title == "Example Paper"
    assert fetched.authors == ["Ada Lovelace", "Grace Hopper"]
    assert fetched.year == 2026
    assert fetched.provider == "springer_html"
    assert fetched.has_fulltext is True
    assert fetched.references[0].doi == "10.1234/ref"
    assert fetched.assets[0].kind == "figure"
