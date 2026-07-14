from dataclasses import dataclass

import click
from click.testing import CliRunner

from paperbase.cli.main import main


@dataclass
class FakeOnlineResult:
    paper_id: str = "doi:10.1234/example"
    storage_id: str = "p_example"


def test_ingest_routes_non_file_identifier_to_online_adapter(monkeypatch, tmp_path):
    calls = {}
    graph_calls = []

    class FakeAdapter:
        def fetch(self, query):
            calls["query"] = query
            return object()

    def fake_ingest_fetched_paper(base_dir, fetched):
        calls["base_dir"] = base_dir
        calls["fetched"] = fetched
        return FakeOnlineResult()

    @click.command()
    @click.option("--force", is_flag=True)
    def fake_graph_update(force):
        graph_calls.append(force)

    monkeypatch.setattr("paperbase.cli.commands.ingest.PaperFetchAdapter", FakeAdapter)
    monkeypatch.setattr(
        "paperbase.cli.commands.ingest.ingest_fetched_paper",
        fake_ingest_fetched_paper,
    )
    monkeypatch.setattr("paperbase.cli.commands.graph.update", fake_graph_update)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "10.1234/example", "--no-graph"],
    )

    assert result.exit_code == 0
    assert calls["query"] == "10.1234/example"
    assert calls["base_dir"] == tmp_path
    assert graph_calls == []
    assert "doi:10.1234/example" in result.output
    # 新的用户友好输出不再显示 storage_id
    assert "论文标识" in result.output or "论文已成功添加" in result.output


def test_online_ingest_updates_fts_then_graph_by_default(monkeypatch, tmp_path):
    calls = []

    class FakeAdapter:
        def fetch(self, query):
            return object()

    class FakeSearchEngine:
        def __init__(self, index_path, library_path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def build_index(self):
            calls.append("fts")

    @click.command()
    @click.option("--force", is_flag=True)
    def fake_graph_update(force):
        calls.append("graph")

    monkeypatch.setattr("paperbase.cli.commands.ingest.PaperFetchAdapter", FakeAdapter)
    monkeypatch.setattr(
        "paperbase.cli.commands.ingest.ingest_fetched_paper",
        lambda base_dir, fetched: FakeOnlineResult(),
    )
    monkeypatch.setattr("paperbase.core.search_engine.SearchEngine", FakeSearchEngine)
    monkeypatch.setattr("paperbase.cli.commands.graph.update", fake_graph_update)

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "10.1234/example"],
    )

    assert result.exit_code == 0, result.output
    assert calls == ["fts", "graph"]
