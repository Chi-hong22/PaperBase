"""Canonical 写入前纯本地采用门测试。"""

import pytest

from paperbase.core.canonical_adoption_gate import (
    CanonicalAdoptionGateError,
    inspectCanonicalTextForGraph,
    validateCanonicalAdoption,
    validateMarkdownHealth,
)
from paperbase.schemas.paper import PaperMetadata
from paperbase.utils.markdown import generate_canonical_markdown

PAPER_ID = "doi:10.1234/canonical-gate"
STORAGE_ID = "p_canonical_gate"


def _canonical(body: str, **metadata_changes: object) -> str:
    metadata: dict[str, object] = {
        "schema_version": "1.0",
        "paper_id": PAPER_ID,
        "storage_id": STORAGE_ID,
        "title": "Canonical gate fixture",
        "authors": [{"name": "Ada Lovelace"}],
        "year": 2026,
        "abstract": "A local validation fixture.",
    }
    metadata.update(metadata_changes)
    return generate_canonical_markdown(metadata, body)


def test_valid_canonical_returns_schema_and_structured_references():
    canonical = _canonical(
        "# Paper\n\n" + ("Full text evidence. " * 40) + "\n\n## References\n\n"
        "[1] A. Author. (2024). A parsed reference. DOI: 10.1000/example.\n"
    )

    result = validateCanonicalAdoption(
        canonical,
        expected_paper_id=PAPER_ID,
        expected_storage_id=STORAGE_ID,
        minimum_body_chars=500,
    )

    assert isinstance(result.metadata, PaperMetadata)
    assert result.metadata.paper_id == PAPER_ID
    assert len(result.references) == 1
    assert result.references[0]["doi"] == "10.1000/example"


@pytest.mark.parametrize(
    ("canonical", "expected_reason"),
    [
        ("not frontmatter", "frontmatter"),
        (_canonical("body", authors=[]), "schema"),
        (_canonical("body", paper_id="doi:wrong"), "paper_id"),
        (_canonical("body", storage_id="p_wrong"), "storage_id"),
        (_canonical("![local](C:/temp/figure.png)\n\n" + ("body " * 120)), "asset"),
        (_canonical("![relative](figures/figure.png)\n\n" + ("body " * 120)), "asset"),
        (_canonical("short body"), "500"),
        (
            _canonical(("body " * 120) + "\n\n## References\n\nUnnumbered broken entry."),
            "References",
        ),
    ],
    ids=[
        "invalid-frontmatter",
        "invalid-schema",
        "paper-id-mismatch",
        "storage-id-mismatch",
        "absolute-asset",
        "non-assets-relative-path",
        "short-body",
        "unparseable-reference-section",
    ],
)
def test_invalid_canonical_is_rejected(canonical, expected_reason):
    with pytest.raises(CanonicalAdoptionGateError, match=expected_reason):
        validateCanonicalAdoption(
            canonical,
            expected_paper_id=PAPER_ID,
            expected_storage_id=STORAGE_ID,
            minimum_body_chars=500,
        )


@pytest.mark.parametrize(
    "fragment",
    ["\x01", "\ufffd", r"\n", r"\r", r"\t", "<!-- paperbase:visual-page-start page=1 -->"],
)
def test_markdown_health_rejects_extraction_debris(fragment):
    with pytest.raises(CanonicalAdoptionGateError):
        validateMarkdownHealth(f"safe text\n\n{fragment}\n")


def test_graph_text_inspection_is_pure_and_matches_existing_quality_rules():
    assert inspectCanonicalTextForGraph(_canonical("short"), 500) == "Canonical 正文不足 500 字符"
    assert (
        inspectCanonicalTextForGraph(
            _canonical("---\ncontent_kind: abstract_only\n---\n\n" + ("body " * 120)),
            500,
        )
        == "content_kind=abstract_only"
    )
    assert inspectCanonicalTextForGraph(_canonical("body " * 120), 500) is None
