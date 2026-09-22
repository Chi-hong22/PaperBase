"""项目内 PaperBase skill 查询路由对 graphify CLI 的调用契约。"""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_ROUTER_PATH = PROJECT_ROOT / "skills" / "paperbase" / "query_router.py"


def _loadQueryRouter():
    spec = importlib.util.spec_from_file_location("paperbase_skill_query_router", QUERY_ROUTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_query_graph_passes_adopted_graph_path_explicitly(monkeypatch, tmp_path):
    """graphify query 必须显式指向已接纳图谱，禁止依赖工作目录下的 graphify-out。"""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes": [], "links": []}', encoding="utf-8")

    captured: dict[str, list[str]] = {}

    class FakeCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeCompleted()

    router = _loadQueryRouter()
    monkeypatch.setattr(router.subprocess, "run", fake_run)

    result = router.query_graph("test query", tmp_path)

    assert result == "ok"
    cmd = captured["cmd"]
    assert "--graph" in cmd
    graph_arg = cmd[cmd.index("--graph") + 1]
    assert Path(graph_arg) == graph_dir / "graph.json"
