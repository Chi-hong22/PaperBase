"""Graphify Adapter

调用全局安装的 graphify 命令构建知识图谱
"""

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
    force_rebuild: bool = False
) -> dict:
    """
    运行 graphify 构建知识图谱

    Args:
        library_dir: library 目录路径
        graph_dir: graph 输出目录路径
        force_rebuild: 是否强制重建（删除现有图谱）

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

    # 构建 graphify 命令
    # graphify 默认扫描当前目录，输出到 .graph/
    # 我们需要指定输入和输出路径
    cmd = [
        "graphify",
        str(library_dir),
        "--output", str(graph_dir),
    ]

    try:
        # 运行 graphify
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
            cwd=library_dir.parent  # 在 base_dir 运行
        )

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
    if not graph_dir.exists():
        return {"nodes": 0, "edges": 0, "files": []}

    # 统计图谱文件
    graph_files = list(graph_dir.glob("**/*.json"))

    return {
        "nodes": 0,  # TODO: 从图谱文件中解析
        "edges": 0,  # TODO: 从图谱文件中解析
        "files": [f.name for f in graph_files]
    }
