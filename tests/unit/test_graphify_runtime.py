import json
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from click.testing import CliRunner

from paperbase.adapters import graphify_runtime
from paperbase.cli.main import main


def testExplicitLocalPythonIsValidatedAndUsed(tmp_path, monkeypatch):
    python_path = tmp_path / "独立环境" / "python.exe"
    python_path.parent.mkdir()
    python_path.touch()
    observed = []

    def runProbe(cmd, **kwargs):
        observed.append(cmd)
        return CompletedProcess(cmd, 0, json.dumps({
            "python": str(python_path), "prefix": str(python_path.parent), "version": "1.2.3",
        }), "")

    monkeypatch.setattr("subprocess.run", runProbe)
    runtime = graphify_runtime.resolveGraphifyRuntime("local", python=str(python_path))

    assert runtime.source == "local"
    assert runtime.version == "1.2.3"
    assert runtime.command == [str(python_path), "-m", "graphify"]
    assert observed[0][0] == str(python_path)


@pytest.fixture
def runtimeInventory(tmp_path, monkeypatch):
    local_python = tmp_path / "本地 环境" / "python.exe"
    uv_root = tmp_path / "uv-tools"
    uv_prefix = uv_root / "unexpected-distribution-name"
    uv_python = uv_prefix / "Scripts" / "python.exe"
    for path in (local_python, uv_python):
        path.parent.mkdir(parents=True)
        path.touch()
    (uv_prefix / "uv-receipt.toml").write_text(
        '[tool]\nentrypoints = [{name="graphify", from="unexpected-distribution-name"}]\n',
        encoding="utf-8",
    )
    launcher = tmp_path / "bin" / "graphify.exe"
    launcher.parent.mkdir()
    launcher.write_bytes(b"launcher-prefix\x00#!" + str(uv_python).encode("utf-8") + b"\nPK")
    inventory = {"local": True, "uv": True, "launcher": True, "calls": []}

    def whichCommand(name, path=None):
        if name == "uv" and inventory["uv"]:
            return "uv-test"
        if name == "graphify" and inventory["launcher"]:
            return str(launcher)
        if Path(name).is_file():
            return str(name)
        return None

    def runCommand(cmd, **kwargs):
        inventory["calls"].append(cmd)
        if cmd == ["uv-test", "tool", "dir"]:
            return CompletedProcess(cmd, 0, str(uv_root), "")
        if str(cmd[0]) == str(local_python) and inventory["local"]:
            prefix = local_python.parent
        elif str(cmd[0]) == str(uv_python) and inventory["uv"]:
            prefix = uv_prefix
        else:
            return CompletedProcess(cmd, 1, "", "ModuleNotFoundError")
        return CompletedProcess(cmd, 0, json.dumps({
            "python": cmd[0], "prefix": str(prefix), "version": "9.8.7",
        }), "")

    monkeypatch.setattr(graphify_runtime.sys, "executable", str(local_python))
    monkeypatch.setattr(graphify_runtime.os, "get_exec_path", lambda: [str(launcher.parent)])
    monkeypatch.setattr(graphify_runtime.shutil, "which", whichCommand)
    monkeypatch.setattr(graphify_runtime.subprocess, "run", runCommand)
    for variable in ("SOURCE", "PYTHON", "COMMAND"):
        monkeypatch.delenv(f"PAPERBASE_GRAPHIFY_{variable}", raising=False)
    inventory.update(local_python=local_python, uv_python=uv_python, launcher=launcher)
    return inventory


@pytest.mark.parametrize("source,local_available,expected", [
    ("auto", True, "local"), ("auto", False, "uv"),
    ("local", True, "local"), ("uv", True, "uv"),
])
def testSourceSelection(source, local_available, expected, runtimeInventory):
    runtimeInventory["local"] = local_available
    runtime = graphify_runtime.resolveGraphifyRuntime(source)
    assert runtime.source == expected
    assert runtime.python == runtimeInventory[f"{expected}_python"]


def testLocalDoesNotMisclassifyUvLauncherOrFallBack(runtimeInventory):
    runtimeInventory["local"] = False
    with pytest.raises(graphify_runtime.GraphifyUnavailable, match="local"):
        graphify_runtime.resolveGraphifyRuntime("local")
    assert ["uv-test", "tool", "dir"] not in runtimeInventory["calls"]


def testUvReceiptDiscoveryDoesNotAssumeDistributionNameOrInstall(runtimeInventory):
    runtimeInventory["launcher"] = False
    runtime = graphify_runtime.resolveGraphifyRuntime("uv")
    assert runtime.python == runtimeInventory["uv_python"]
    assert ["uv-test", "tool", "dir"] in runtimeInventory["calls"]
    assert all("install" not in cmd and "run" not in cmd for cmd in runtimeInventory["calls"])


def testUvDoesNotFallBackToAvailableLocal(runtimeInventory):
    runtimeInventory["uv"] = False
    with pytest.raises(graphify_runtime.GraphifyUnavailable, match="uv"):
        graphify_runtime.resolveGraphifyRuntime("uv")


def testExplicitLocalCommandWithSpacesUsesItsOwnPython(runtimeInventory):
    launcher = runtimeInventory["launcher"]
    launcher.write_bytes(b'#!"' + str(runtimeInventory["local_python"]).encode("utf-8") + b'"\n')
    runtime = graphify_runtime.resolveGraphifyRuntime("local", command=str(launcher))
    assert runtime.python == runtimeInventory["local_python"]


def testExplicitUvLauncherCannotMasqueradeAsLocal(runtimeInventory):
    with pytest.raises(graphify_runtime.GraphifyUnavailable, match="uv 工具环境"):
        graphify_runtime.resolveGraphifyRuntime("local", command=str(runtimeInventory["launcher"]))


def testExplicitMissingCommandDoesNotFallBack(runtimeInventory):
    with pytest.raises(graphify_runtime.GraphifyUnavailable, match="命令不存在"):
        graphify_runtime.resolveGraphifyRuntime(command="missing-graphify")
    assert runtimeInventory["calls"] == []


def testCliReportsInstallationsAndSelectedRuntime(runtimeInventory):
    result = CliRunner().invoke(main, ["--graphify-source", "uv", "graph", "runtime"])
    assert result.exit_code == 0, result.output
    assert "local: 9.8.7" in result.output
    assert "uv: 9.8.7" in result.output
    assert "选中: uv" in result.output


def testCliSourceOverridesEnvironment(runtimeInventory, monkeypatch):
    monkeypatch.setenv("PAPERBASE_GRAPHIFY_SOURCE", "local")
    result = CliRunner().invoke(main, ["--graphify-source", "uv", "graph", "runtime"])
    assert result.exit_code == 0, result.output
    assert "选中: uv" in result.output


def testCliMissingLocalStopsBeforeTouchingGraph(runtimeInventory, tmp_path):
    runtimeInventory["local"] = False
    graph_dir = tmp_path / "library" / "papers" / "graphify-out"
    graph_dir.mkdir(parents=True)
    sentinel = graph_dir / "sentinel"
    sentinel.write_text("original", encoding="utf-8")
    result = CliRunner().invoke(main, [
        "--base-dir", str(tmp_path), "--graphify-source", "local", "graph", "update", "--force",
    ])
    assert result.exit_code == 1
    assert "来源: local" in result.output
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert all("extract" not in cmd for cmd in runtimeInventory["calls"])


def testCliExplicitPythonOverridesEnvironmentCommand(runtimeInventory, monkeypatch):
    monkeypatch.setenv("PAPERBASE_GRAPHIFY_COMMAND", "missing-graphify")
    result = CliRunner().invoke(main, [
        "--graphify-python", str(runtimeInventory["local_python"]), "graph", "runtime",
    ])
    assert result.exit_code == 0, result.output
    assert "选中: local" in result.output


def testDoctorUsesSelectedRuntime(runtimeInventory):
    from paperbase.cli.commands.doctor import check_graphify

    passed, message = check_graphify({"source": "uv"})
    assert passed is True
    assert "uv;" in message
    assert str(runtimeInventory["uv_python"]) in message


@pytest.mark.parametrize("options", [
    {"source": "unknown"},
    {"python": "python", "command": "graphify"},
    {"source": "uv", "python": "python"},
])
def testInvalidSelectionNeverLaunchesAnything(options, runtimeInventory):
    with pytest.raises(graphify_runtime.GraphifyUnavailable):
        graphify_runtime.resolveGraphifyRuntime(**options)
    assert runtimeInventory["calls"] == []


def testUserSiteInstallationIsDetectedAndExecutable(tmp_path, monkeypatch):
    """模拟 pip --user 的包布局，实际启动 Python 验证探测与执行。"""
    monkeypatch.setenv("PYTHONUSERBASE", str(tmp_path / "user-base"))
    monkeypatch.delenv("PYTHONNOUSERSITE", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    base_python = getattr(sys, "_base_executable", sys.executable)
    site_result = subprocess.run(
        [base_python, "-c", "import json,site; print(json.dumps(site.getusersitepackages()))"],
        capture_output=True, text=True, check=True,
    )
    user_site = Path(json.loads(site_result.stdout))
    package = user_site / "graphify"
    package.mkdir(parents=True)
    for name, content in {
        "__init__.py": "",
        "__main__.py": "print('user-install-cli')",
        "detect.py": "def detect(): pass",
        "cache.py": "def check_semantic_cache(): pass",
    }.items():
        (package / name).write_text(content, encoding="utf-8")
    metadata = user_site / "graphify_test-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: graphify-test\nVersion: 1.0\n", encoding="utf-8")
    (metadata / "top_level.txt").write_text("graphify\n", encoding="utf-8")

    runtime = graphify_runtime.resolveGraphifyRuntime("local", python=base_python)
    result = subprocess.run(runtime.command + ["--version"], capture_output=True, text=True)

    assert runtime.source == "local"
    assert runtime.version == "1.0"
    assert result.returncode == 0
    assert result.stdout.strip() == "user-install-cli"
