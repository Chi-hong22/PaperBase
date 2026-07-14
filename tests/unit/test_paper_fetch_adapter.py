import json
from unittest.mock import Mock, patch

from paperbase.adapters.paper_fetch_adapter import PaperFetchAdapter


@patch("paperbase.adapters.paper_fetch_adapter.shutil.which", return_value="paper-fetch")
@patch("paperbase.adapters.paper_fetch_adapter.subprocess.run")
def test_adapter_maps_cli_envelope_to_fetched_paper(mock_run, mock_which):
    envelope = {
        "doi": "10.1234/example",
        "source": "springer_html",
        "has_fulltext": True,
        "content_kind": "fulltext",
        "warnings": [],
        "source_trail": ["crossref", "springer_html"],
        "markdown": "# Example Paper\n\nThis paper studies example systems.",
        "metadata": {
            "title": "Example Paper",
            "authors": ["Ada Lovelace", "Grace Hopper"],
            "abstract": "This paper studies example systems.",
            "published": "2026-07-08",
            "landing_page_url": "https://doi.org/10.1234/example",
        },
        "article": {
            "references": [
                {
                    "raw": "Lovelace A. Example work.",
                    "doi": "10.1234/ref",
                    "title": "Example work",
                    "year": "2025",
                }
            ],
            "assets": [
                {
                    "kind": "figure",
                    "heading": "Figure 1",
                    "caption": "Example figure.",
                    "path": "downloaded/fig1.png",
                    "original_url": "https://example.org/fig1.png",
                }
            ],
        },
    }
    mock_run.return_value = Mock(stdout=json.dumps(envelope))

    fetched = PaperFetchAdapter().fetch("10.1234/example")

    mock_which.assert_called_once_with("paper-fetch")
    mock_run.assert_called_once_with(
        ["paper-fetch", "--query", "10.1234/example", "--format", "both"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    assert fetched.query == "10.1234/example"
    assert fetched.doi == "10.1234/example"
    assert fetched.title == "Example Paper"
    assert fetched.authors == ["Ada Lovelace", "Grace Hopper"]
    assert fetched.year == 2026
    assert fetched.provider == "springer_html"
    assert fetched.has_fulltext is True
    assert fetched.references[0].doi == "10.1234/ref"
    assert fetched.assets[0].kind == "figure"
