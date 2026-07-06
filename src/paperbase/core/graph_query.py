"""Graph Query

基于 graphify 输出的图谱实现查询功能
"""

import json
from pathlib import Path
from typing import List, Set, Dict, Any


def _load_graph(graph_dir: Path) -> Dict[str, Any]:
    """
    加载图谱 JSON 文件

    Args:
        graph_dir: graph 目录路径

    Returns:
        dict: 图谱数据 {"nodes": [...], "edges": [...]}

    Raises:
        FileNotFoundError: 如果 graph.json 不存在
    """
    graph_file = graph_dir / "graph.json"

    if not graph_file.exists():
        raise FileNotFoundError(f"Graph file not found: {graph_file}")

    with open(graph_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_adjacency_list(edges: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """
    构建邻接表（无向图）

    Args:
        edges: 边列表

    Returns:
        dict: 邻接表 {node_id: {neighbor_id, ...}}
    """
    adj_list = {}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if not source or not target:
            continue

        # 无向图：双向添加
        if source not in adj_list:
            adj_list[source] = set()
        if target not in adj_list:
            adj_list[target] = set()

        adj_list[source].add(target)
        adj_list[target].add(source)

    return adj_list


def find_related_papers(
    graph_dir: Path,
    paper_id: str,
    depth: int = 1
) -> List[str]:
    """
    查找相关论文（通过图遍历）

    Args:
        graph_dir: graph 目录路径
        paper_id: 论文 ID
        depth: 遍历深度（1=直接相关，2=二度相关）

    Returns:
        list[str]: 相关论文的 paper_id 列表

    Raises:
        FileNotFoundError: 如果 graph.json 不存在
    """
    # 加载图谱
    graph = _load_graph(graph_dir)
    edges = graph.get("edges", [])

    # 构建邻接表
    adj_list = _build_adjacency_list(edges)

    # 如果论文不在图中，返回空列表
    if paper_id not in adj_list:
        return []

    # BFS 遍历
    visited = set()
    current_level = {paper_id}
    visited.add(paper_id)

    for _ in range(depth):
        next_level = set()
        for node in current_level:
            if node in adj_list:
                for neighbor in adj_list[node]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_level.add(neighbor)
        current_level = next_level

    # 移除起始节点，返回相关节点
    visited.discard(paper_id)
    return sorted(list(visited))


def find_papers_by_topic(
    graph_dir: Path,
    topic: str
) -> List[str]:
    """
    按主题查找论文

    Args:
        graph_dir: graph 目录路径
        topic: 主题关键词（大小写不敏感）

    Returns:
        list[str]: 匹配的 paper_id 列表

    Raises:
        FileNotFoundError: 如果 graph.json 不存在
    """
    # 加载图谱
    graph = _load_graph(graph_dir)
    nodes = graph.get("nodes", [])

    # 规范化主题（小写）
    topic_lower = topic.lower()

    # 查找匹配的论文节点
    matched_papers = []

    for node in nodes:
        # 只处理 paper 类型的节点
        if node.get("type") != "paper":
            continue

        node_id = node.get("id")
        attributes = node.get("attributes", {})
        topics = attributes.get("topics", [])

        # 检查主题列表
        if isinstance(topics, list):
            for t in topics:
                if isinstance(t, str) and topic_lower in t.lower():
                    matched_papers.append(node_id)
                    break  # 找到一个匹配即可

    return sorted(matched_papers)
