import json
import sys
from types import ModuleType

import pytest

from paperbase.adapters.zotero_adapter import ZoteroAdapter


@pytest.fixture
def zotero_runtime(monkeypatch):
    retrieval = ModuleType("zotero_mcp.tools.retrieval")
    tools = ModuleType("zotero_mcp.tools")
    tools.retrieval = retrieval

    cli_standalone = ModuleType("zotero_mcp.cli_standalone")

    class CLIContext:
        def __init__(self, verbose=False):
            self.verbose = verbose

    cli_standalone.CLIContext = CLIContext

    monkeypatch.setitem(sys.modules, "zotero_mcp.cli_standalone", cli_standalone)
    monkeypatch.setitem(sys.modules, "zotero_mcp.tools", tools)

    return retrieval


def test_fetch_item_parses_zotero_061_json(zotero_runtime):
    calls = []

    def get_item_metadata(item_key, include_abstract=True, format="markdown", *, ctx):
        calls.append((item_key, include_abstract, format))
        return json.dumps(
            {
                "key": "ABCD1234",
                "data": {
                    "key": "ABCD1234",
                    "itemType": "journalArticle",
                    "title": "Example Paper",
                    "creators": [
                        {"creatorType": "author", "name": "Lovelace, Ada"},
                        {
                            "creatorType": "author",
                            "firstName": "Grace",
                            "lastName": "Hopper",
                        },
                    ],
                    "date": "2026-07-10",
                    "DOI": "10.1234/example",
                    "abstractNote": "Example abstract.",
                    "url": "https://example.org/paper",
                },
            }
        )

    zotero_runtime.get_item_metadata = get_item_metadata

    item = ZoteroAdapter(local_mode=True).fetch_item("ABCD1234")

    assert item.key == "ABCD1234"
    assert item.title == "Example Paper"
    assert item.authors == ["Lovelace, Ada", "Hopper, Grace"]
    assert item.year == 2026
    assert item.doi == "10.1234/example"
    assert item.abstract == "Example abstract."
    assert item.url == "https://example.org/paper"
    assert item.item_type == "journalArticle"
    assert calls == [("ABCD1234", True, "json")]


def test_fetch_item_preserves_missing_authors_and_year_for_pdf_fallback(zotero_runtime):
    zotero_runtime.get_item_metadata = lambda item_key, include_abstract, format, *, ctx: json.dumps(
        {
            "key": item_key,
            "data": {
                "key": item_key,
                "itemType": "journalArticle",
                "title": "Metadata With Gaps",
                "creators": [],
                "date": "",
            },
        }
    )

    item = ZoteroAdapter(local_mode=True).fetch_item("GAPS1234")

    assert item.authors == []
    assert item.year is None


def test_list_recent_resolves_item_keys_from_zotero_061_output(zotero_runtime):
    zotero_runtime.get_recent = lambda limit, *, ctx: """# 1 Most Recently Added Items

## 1. Example Paper
**Type:** journalArticle
**Item Key:** ABCD1234
**Date:** 2026-07-10
**Authors:** Lovelace, Ada
"""
    zotero_runtime.get_item_metadata = lambda item_key, include_abstract, format, *, ctx: json.dumps(
        {
            "key": item_key,
            "data": {
                "key": item_key,
                "itemType": "journalArticle",
                "title": "Example Paper",
                "creators": [{"name": "Lovelace, Ada"}],
                "date": "2026-07-10",
                "abstractNote": "",
            },
        }
    )

    items = ZoteroAdapter(local_mode=True).list_recent(limit=1)

    assert [item.key for item in items] == ["ABCD1234"]
    assert [item.title for item in items] == ["Example Paper"]


def test_list_recent_accepts_title_containing_error(zotero_runtime):
    zotero_runtime.get_recent = lambda limit, *, ctx: """# 1 Most Recently Added Items

## 1. Error-State Kalman Filter
**Type:** journalArticle
**Item Key:** ERROR123
"""
    zotero_runtime.get_item_metadata = lambda item_key, include_abstract, format, *, ctx: json.dumps(
        {
            "key": item_key,
            "data": {
                "key": item_key,
                "itemType": "journalArticle",
                "title": "Error-State Kalman Filter",
                "creators": [{"name": "Lovelace, Ada"}],
                "date": "2026",
            },
        }
    )

    items = ZoteroAdapter(local_mode=True).list_recent(limit=1)

    assert [item.title for item in items] == ["Error-State Kalman Filter"]


def test_get_pdf_path_parses_zotero_061_local_path(zotero_runtime, tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    zotero_runtime.get_attachment_path = lambda item_key, *, ctx: (
        f"# Attachments for `{item_key}`\n\n"
        f"## `ATTACH01` (application/pdf)\n"
        f"- Local path: `{pdf_path}`\n"
    )

    result = ZoteroAdapter(local_mode=True).get_pdf_path("ABCD1234")

    assert result == str(pdf_path)


def test_get_pdf_path_accepts_directory_containing_error(zotero_runtime, tmp_path):
    pdf_path = tmp_path / "error_models" / "paper.pdf"
    pdf_path.parent.mkdir()
    pdf_path.write_bytes(b"%PDF-1.4\n")
    zotero_runtime.get_attachment_path = lambda item_key, *, ctx: (
        f"# Attachments for `{item_key}`\n\n"
        f"## `ATTACH01` (application/pdf)\n"
        f"- Local path: `{pdf_path}`\n"
    )

    assert ZoteroAdapter(local_mode=True).get_pdf_path("ABCD1234") == str(pdf_path)


def test_get_pdf_path_returns_none_when_zotero_has_no_local_pdf(zotero_runtime):
    zotero_runtime.get_attachment_path = lambda item_key, *, ctx: "# No attachments"

    assert ZoteroAdapter(local_mode=True).get_pdf_path("ABCD1234") is None


def test_get_pdf_path_returns_none_when_zotero_lookup_fails(zotero_runtime):
    def fail_lookup(item_key, *, ctx):
        raise RuntimeError("Zotero unavailable")

    zotero_runtime.get_attachment_path = fail_lookup

    assert ZoteroAdapter(local_mode=True).get_pdf_path("ABCD1234") is None
