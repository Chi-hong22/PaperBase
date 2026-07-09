"""Graphify Adapter

调用全局安装的 graphify 命令构建知识图谱
"""

import os
import subprocess
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
    llm_config: dict | None = None
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

    # 如果 force_rebuild，删除现有图谱
    if force_rebuild and graph_dir.exists():
        shutil.rmtree(graph_dir)

    # 确保 graph 目录存在
    graph_dir.mkdir(parents=True, exist_ok=True)

    # graphify 不能递归扫描 library/papers/，需要扫描所有论文子目录
    papers_dir = library_dir / "papers"
    if not papers_dir.exists():
        return {
            "success": False,
            "output": "",
            "error": f"Papers 目录不存在: {papers_dir}"
        }

    # 收集所有论文目录（p_xxx 格式）
    paper_dirs = [d for d in papers_dir.iterdir() if d.is_dir() and d.name.startswith("p_")]

    if not paper_dirs:
        return {
            "success": False,
            "output": "",
            "error": "未找到任何论文目录（p_xxx 格式）"
        }

    # 构建 graphify 命令：扫描所有论文目录
    # 格式：graphify extract <path1> <path2> ... --backend <name> --model <name>
    cmd = [
        "graphify",
        "extract",  # 使用 extract 子命令
    ] + [str(d) for d in paper_dirs] + [  # 所有论文目录
        "--backend", "openai",  # 明确指定 backend
    ]

    # 准备环境变量（继承当前环境 + PaperBase LLM 配置）
    import os
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

    try:
        # 运行 graphify，传入修改后的环境变量
        # graphify 会在第一个扫描目录的父目录下创建 graphify-out/
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
            cwd=str(papers_dir),  # 在 papers 目录运行
            env=env  # 传递环境变量
        )

        # 如果成功，将 graphify-out/ 移动到目标 graph/ 目录
        if result.returncode == 0:
            graphify_out = papers_dir / "graphify-out"
            if graphify_out.exists():
                # 将内容复制到 graph/ 目录
                if graph_dir.exists():
                    shutil.rmtree(graph_dir)
                shutil.copytree(graphify_out, graph_dir)
                # 清理 graphify-out
                shutil.rmtree(graphify_out)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "graphify 执行超时（>5分钟）"
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": f"graphify 执行失败: {str(e)}"
        }


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
            stats["edges"] = len(graph_data.get("edges", []))
        except (json.JSONDecodeError, OSError):
            # 优雅降级：解析失败时返回 0
            pass

    return stats
