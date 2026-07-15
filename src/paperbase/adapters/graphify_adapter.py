"""Graphify Adapter

调用全局安装的 graphify 命令构建知识图谱
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
import shutil


def check_graphify_installed() -> bool:
    """
    检查 graphify 是否已安装

    Returns:
        bool: True 如果已安装
    """
    return shutil.which("graphify") is not None


def run_graphify(
    library_dir: Path,
    graph_dir: Path,
    force_rebuild: bool = False,
    llm_config: dict | None = None,
    process_timeout: float | None = None,
    api_timeout: float | None = None,
) -> dict:
    """
    运行 graphify 构建知识图谱

    注意：需要确保 .gitignore 正确配置，允许 graphify 扫描 library/papers/*.md 文件。

    Args:
        library_dir: library 目录路径
        graph_dir: graph 输出目录路径
        force_rebuild: 是否强制重建（删除现有图谱）
        llm_config: PaperBase LLM 配置（可选），包含：
            - api_key: LLM API Key
            - base_url: LLM API Base URL
            - model: LLM 模型名称
        process_timeout: PaperBase 外层进程超时；None 表示不限制批处理总时长
        api_timeout: graphify 单次 LLM 请求超时（秒）

    Returns:
        dict: {
            "success": bool,
            "output": str,
            "error": str | None
        }
    """
    # 检查 graphify 是否安装
    if not check_graphify_installed():
        return {
            "success": False,
            "output": "",
            "error": "graphify 未安装。请运行: uv tool install graphify"
        }

    # 检查 library 目录是否存在
    if not library_dir.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Library 目录不存在: {library_dir}"
        }

    # 确保 graph 目录存在
    graph_dir.mkdir(parents=True, exist_ok=True)

    # 检查 papers 目录
    papers_dir = library_dir / "papers"
    if not papers_dir.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Papers 目录不存在: {papers_dir}"
        }

    # 平面结构：graphify 可以直接扫描 papers/ 目录下的所有 .md 文件
    # 格式：graphify extract <path> --backend <name> --model <name>
    cmd = [
        "graphify",
        "extract",  # 使用 extract 子命令
        ".",  # cwd 已位于 papers 目录，避免 Windows 绝对路径被重复拼接
        "--backend", "openai",  # 明确指定 backend
    ]

    # 准备环境变量（继承当前环境 + PaperBase LLM 配置）
    env = os.environ.copy()

    # 如果提供了 llm_config，映射为 graphify 识别的环境变量
    if llm_config:
        api_key = llm_config.get("api_key", "")
        base_url = llm_config.get("base_url", "")
        model = llm_config.get("model", "")

        if api_key:
            # graphify 使用 OpenAI SDK，映射到 OPENAI_API_KEY
            env["OPENAI_API_KEY"] = api_key

        # 如果配置了 base_url（无论是否为 OpenAI），都设置环境变量
        # 让 graphify 的 OpenAI SDK 使用自定义 endpoint
        if base_url:
            env["OPENAI_BASE_URL"] = base_url

        # 如果配置了 model，添加到命令参数
        if model:
            cmd.extend(["--model", model])

    if api_timeout is not None:
        cmd.extend(["--api-timeout", str(api_timeout)])

    try:
        graphify_out = papers_dir / "graphify-out"
        if force_rebuild and graphify_out.exists():
            shutil.rmtree(graphify_out)

        # 运行 graphify，传入修改后的环境变量
        # graphify 会在第一个扫描目录的父目录下创建 graphify-out/
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=process_timeout,
            cwd=str(papers_dir),  # 在 papers 目录运行
            env=env  # 传递环境变量
        )

        # 如果成功，将 graphify-out/ 复制到目标 graph/ 目录，保留源端缓存供下次增量运行。
        if result.returncode == 0:
            if not (graphify_out / "graph.json").is_file():
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": "graphify 执行成功但未生成 graphify-out/graph.json",
                }

            adoption = adopt_graphify_output(library_dir, graph_dir)
            if not adoption["success"]:
                adoption["output"] = result.stdout
                return adoption

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }

    except subprocess.TimeoutExpired as exc:
        limit = "未设置" if process_timeout is None else f"{process_timeout:g} 秒"
        return {
            "success": False,
            "output": _timeout_output(exc),
            "error": f"graphify 执行超时（外层限制: {limit}）"
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": f"graphify 执行失败: {str(e)}"
        }


def adopt_graphify_output(library_dir: Path, graph_dir: Path) -> dict:
    """将 Agent/Graphify 已生成的 graphify-out 原子投影到 PaperBase graph/。"""
    papers_dir = library_dir / "papers"
    graphify_out = papers_dir / "graphify-out"

    if not graphify_out.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Graphify 输出目录不存在: {graphify_out}",
        }
    if not (graphify_out / "graph.json").is_file():
        return {
            "success": False,
            "output": "",
            "error": f"Graphify 输出缺少 graph.json: {graphify_out}",
        }

    source_errors = _validate_canonical_graph_sources(
        graphify_out / "graph.json",
        papers_dir,
    )
    if source_errors:
        details = "；".join(source_errors[:3])
        remaining = len(source_errors) - 3
        if remaining > 0:
            details += f"；另有 {remaining} 项"
        return {
            "success": False,
            "output": "",
            "error": (
                "Graphify 输出违反 Canonical Markdown 唯一来源约束: "
                f"{details}。请先将 PDF/URL 转换并写回 paper.md，再重新建图。"
            ),
        }

    try:
        _replace_graph_output(graphify_out, graph_dir)
    except Exception as exc:
        return {
            "success": False,
            "output": "",
            "error": f"Graphify 输出投影失败: {exc}",
        }

    return {"success": True, "output": "", "error": None}


def _validate_canonical_graph_sources(graph_json: Path, papers_dir: Path) -> list[str]:
    """验证图谱证据只来自 library/papers/*.md。"""
    try:
        graph_data = json.loads(graph_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"无法读取 graph.json ({exc})"]

    errors: list[str] = []
    papers_root = papers_dir.resolve()
    buckets = (
        graph_data.get("nodes", []),
        graph_data.get("edges", []),
        graph_data.get("links", []),
        graph_data.get("hyperedges", []),
    )

    for records in buckets:
        for record in records:
            if not isinstance(record, dict):
                continue

            source_location = str(record.get("source_location") or "").lower()
            if source_location.startswith(("external_pdf:", "source_pdf:", "external_url:")):
                errors.append(f"发现外部来源定位 {record.get('source_location')}")

            extraction_source = record.get("extraction_source")
            if extraction_source not in (None, "canonical_markdown"):
                errors.append(f"发现非 Canonical 抽取来源 {extraction_source}")

            raw_source = record.get("source_file")
            if not raw_source:
                continue
            source_text = str(raw_source).strip()
            if source_text.lower().startswith(("http://", "https://", "file:")):
                errors.append(f"发现 URL/本地文件来源 {source_text}")
                continue

            source_path = Path(source_text)
            if source_path.suffix.lower() != ".md":
                errors.append(f"发现非 Markdown 来源 {source_text}")
                continue

            candidate = source_path if source_path.is_absolute() else papers_root / source_path
            try:
                resolved = candidate.resolve()
                resolved.relative_to(papers_root)
            except (OSError, ValueError):
                errors.append(f"来源不在 Canonical 目录 {source_text}")
                continue
            if not resolved.is_file():
                errors.append(f"Canonical Markdown 不存在 {source_text}")

    return list(dict.fromkeys(errors))


def _replace_graph_output(graphify_out: Path, graph_dir: Path) -> None:
    """原子替换 PaperBase 图谱目录，保留 Graphify 自身缓存。"""
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{graph_dir.name}-swap-", dir=graph_dir.parent)
    )
    staged_graph = staging_root / "new"
    previous_graph = staging_root / "previous"

    try:
        shutil.copytree(graphify_out, staged_graph)
        if graph_dir.exists():
            graph_dir.replace(previous_graph)

        try:
            staged_graph.replace(graph_dir)
        except Exception:
            if previous_graph.exists() and not graph_dir.exists():
                previous_graph.replace(graph_dir)
            raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    """提取超时时已捕获的输出，便于定位批量任务卡点。"""
    stdout = _stringify_output(exc.stdout)
    stderr = _stringify_output(exc.stderr)
    return "\n".join(part for part in (stdout, stderr) if part)


def _stringify_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def get_graph_stats(graph_dir: Path) -> dict:
    """
    获取图谱统计信息

    Args:
        graph_dir: graph 目录路径

    Returns:
        dict: {
            "nodes": int,
            "edges": int,
            "files": list[str]
        }
    """
    graph_dir = Path(graph_dir)

    stats = {
        "files": [],
        "nodes": 0,
        "edges": 0
    }

    # 列出所有文件
    if graph_dir.exists():
        stats["files"] = [f.name for f in graph_dir.iterdir() if f.is_file()]

    # 读取 graph.json 统计节点和边
    graph_json = graph_dir / "graph.json"
    if graph_json.exists():
        try:
            import json
            with open(graph_json, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            stats["nodes"] = len(graph_data.get("nodes", []))
            stats["edges"] = len(graph_data.get("edges") or graph_data.get("links", []))
        except (json.JSONDecodeError, OSError):
            # 优雅降级：解析失败时返回 0
            pass

    return stats
