import json

from click.testing import CliRunner

from paperbase.cli.main import main


def test_graph_status_reports_node_link_counts(tmp_path):
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [{"id": "paper1"}, {"id": "paper2"}],
                "links": [{"source": "paper1", "target": "paper2"}],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["--base-dir", str(tmp_path), "graph", "status"])

    assert result.exit_code == 0, result.output
    assert "节点: 2" in result.output
    assert "边: 1" in result.output
