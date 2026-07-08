from dataclasses import dataclass

from click.testing import CliRunner

from paperbase.cli.main import main


@dataclass
class FakeOnlineResult:
    paper_id: str = "doi:10.1234/example"
    storage_id: str = "p_example"


def test_ingest_routes_non_file_identifier_to_online_adapter(monkeypatch, tmp_path):
    calls = {}

    class FakeAdapter:
        def fetch(self, query):
            calls["query"] = query
            return object()

    def fake_ingest_fetched_paper(base_dir, fetched):
        calls["base_dir"] = base_dir
        calls["fetched"] = fetched
        return FakeOnlineResult()

    monkeypatch.setattr("paperbase.cli.commands.ingest.PaperFetchAdapter", FakeAdapter)
    monkeypatch.setattr(
        "paperbase.cli.commands.ingest.ingest_fetched_paper",
        fake_ingest_fetched_paper,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "10.1234/example", "--no-graph"],
    )

    assert result.exit_code == 0
    assert calls["query"] == "10.1234/example"
    assert calls["base_dir"] == tmp_path
    assert "doi:10.1234/example" in result.output
    assert "p_example" in result.output
