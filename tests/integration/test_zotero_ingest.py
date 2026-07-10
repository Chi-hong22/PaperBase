"""Integration tests for Zotero ingest functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from click.testing import CliRunner

from paperbase.cli.main import main


def test_ingest_zotero_key_option_exists():
    """Test that --zotero-key option is available."""
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--zotero-key" in result.output


@patch("paperbase.adapters.zotero_adapter.ZoteroAdapter")
@patch("paperbase.cli.commands.ingest._create_paper_from_metadata")
def test_ingest_from_zotero_metadata_only(mock_create_paper, mock_adapter_class):
    """Test ingesting a Zotero item (metadata only, no PDF)."""
    from paperbase.adapters.zotero_adapter import ZoteroItem

    # Mock ZoteroAdapter
    mock_adapter = Mock()
    mock_adapter_class.return_value = mock_adapter

    mock_item = ZoteroItem(
        key="ABCD1234",
        title="Test Paper",
        authors=["John Doe"],
        year=2024,
        item_type="journalArticle",
        doi="10.1234/test",
        abstract="Test abstract",
        has_pdf=False,
        url="https://example.com/paper",
    )
    mock_adapter.fetch_item.return_value = mock_item

    # Mock _create_paper_from_metadata to return a simple paths object
    mock_paths = Mock()
    mock_paths.paper_dir = Path("/tmp/test_dir")
    mock_create_paper.return_value = mock_paths

    # Run ingest command
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, [
            "ingest",
            "--zotero-key", "ABCD1234",
            "--no-graph",
        ], obj={"base_dir": Path.cwd()})

        # Should call fetch_item
        mock_adapter.fetch_item.assert_called_once_with("ABCD1234")

        # Should call _create_paper_from_metadata for metadata-only import
        assert mock_create_paper.called
