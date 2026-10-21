"""已安装 Graphify 的命令与 Python 身份。"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


class GraphifyUnavailable(RuntimeError):
    """指定来源没有可用的 Graphify。"""


@dataclass(frozen=True)
class GraphifyRuntime:
    source: str
    python: Path
    version: str

    @property
    def command(self) -> list[str]:
        return [str(self.python), "-m", "graphify"]


def probePython(python_path: str | Path) -> GraphifyRuntime:
    """向解释器查询自身身份，并验证本项目需要的模块与 CLI 入口。"""
    probe = (
        "import json,sys,importlib.util; from importlib.metadata import version,packages_distributions; "
        "from graphify.detect import detect; from graphify.cache import check_semantic_cache; "
        "assert importlib.util.find_spec('graphify.__main__'), 'missing graphify.__main__'; "
        "print(json.dumps({'python':sys.executable,'prefix':sys.prefix,"
        "'version':version(packages_distributions()['graphify'][0])}))"
    )
    try:
        result = subprocess.run(
            [str(python_path), "-c", probe],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        if result.returncode:
            raise GraphifyUnavailable(f"{python_path}: Graphify 模块或 CLI 入口不可用")
        identity = json.loads(result.stdout)
        prefix = Path(identity["prefix"])
        source = "uv" if (prefix / "uv-receipt.toml").is_file() else "local"
        return GraphifyRuntime(source, Path(identity["python"]), identity["version"])
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        raise GraphifyUnavailable(f"{python_path}: 无法验证 Graphify 环境（{type(exc).__name__}）") from exc


def pythonFromCommand(command: str) -> Path:
    """读取脚本/Windows launcher 的 shebang；不猜测命令的父目录。"""
    executable = shutil.which(command)
    if not executable:
        raise GraphifyUnavailable(f"Graphify 命令不存在: {command}")
    try:
        content = Path(executable).resolve().read_bytes()
        match = re.search(rb"#!([^\r\n]+)", content)
        if match:
            shebang = match[1].decode("utf-8").strip()
            if Path(shebang.strip('"')).is_file():
                return Path(shebang.strip('"'))
            tokens = shlex.split(shebang, posix=os.name != "nt")
            if tokens and Path(tokens[0]).name == "env":
                tokens = tokens[1:]
            if tokens and (python_path := shutil.which(tokens[0].strip('"'))):
                return Path(python_path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise GraphifyUnavailable(f"无法读取 Graphify 命令: {command}") from exc
    raise GraphifyUnavailable(f"无法识别命令的 Python，请显式指定 --graphify-python: {command}")


def installedUvPythons() -> list[Path]:
    """只读取 uv 已安装工具记录，不使用可能下载环境的 uv tool run。"""
    uv_command = shutil.which("uv")
    if not uv_command:
        return []
    try:
        result = subprocess.run(
            [uv_command, "tool", "dir"], capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        if result.returncode or not result.stdout.strip():
            return []
        tools_dir = Path(result.stdout.strip())
        candidates = []
        for receipt in sorted(tools_dir.glob("*/uv-receipt.toml")):
            data = tomllib.loads(receipt.read_text(encoding="utf-8"))
            if any(entry["name"] == "graphify" for entry in data.get("tool", {}).get("entrypoints", [])):
                candidates.extend(
                    path for relative in ("Scripts/python.exe", "bin/python")
                    if (path := receipt.parent / relative).is_file()
                )
        return candidates
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        raise GraphifyUnavailable("无法读取 uv 已安装工具记录") from exc


def resolveGraphifyRuntime(
    source: str | None = None, python: str | None = None, command: str | None = None,
) -> GraphifyRuntime:
    """auto 优先本地再 uv；显式选择失败时不安装、不换源。"""
    if source is None and python is None and command is None:
        python = os.environ.get("PAPERBASE_GRAPHIFY_PYTHON")
        command = os.environ.get("PAPERBASE_GRAPHIFY_COMMAND")
    source = source or os.environ.get("PAPERBASE_GRAPHIFY_SOURCE", "auto")
    if source not in {"auto", "local", "uv"}:
        raise GraphifyUnavailable(f"未知 Graphify 来源: {source}")
    if python and command:
        raise GraphifyUnavailable("--graphify-python 与 --graphify-command 请选择其一")
    if python or command:
        if source == "uv":
            raise GraphifyUnavailable("uv 来源不能同时指定本地命令或 Python")
        runtime = probePython(python or pythonFromCommand(command))
        if runtime.source != "local":
            raise GraphifyUnavailable("指定的是 uv 工具环境，不是独立本地安装；请使用 --graphify-source uv")
        return runtime

    candidates = []
    if source != "uv":
        candidates.append(Path(sys.executable))
        for name in ("python", "python3"):
            if executable := shutil.which(name):
                candidates.append(Path(executable))
    # PATH 入口也可能是 uv；probePython 根据实际环境分类。
    for directory in os.get_exec_path():
        if executable := shutil.which("graphify", path=directory):
            try:
                candidates.append(pythonFromCommand(executable))
            except GraphifyUnavailable:
                continue
    uv_runtime = None
    seen = set()
    for candidate in candidates:
        # 保留虚拟环境解释器的符号链接路径，否则不同环境会被误合并。
        candidate_key = os.path.normcase(os.path.abspath(candidate))
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        try:
            runtime = probePython(candidate)
        except GraphifyUnavailable:
            continue
        if runtime.source == source or (source == "auto" and runtime.source == "local"):
            return runtime
        if runtime.source == "uv":
            uv_runtime = runtime
    if source != "local":
        if uv_runtime:
            return uv_runtime
        for candidate in installedUvPythons():
            try:
                runtime = probePython(candidate)
            except GraphifyUnavailable:
                continue
            if runtime.source == "uv":
                return runtime
    raise GraphifyUnavailable(f"未找到可用的 Graphify（来源: {source}）；未安装工具或切换来源")
