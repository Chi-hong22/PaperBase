"""Graph Query

基于 graphify 输出的图谱实现查询功能
"""

import json
import re
from pathlib import Path
from typing import List, Set, Dict, Any


def _load_graph(graph_dir: Path) -> Dict[str, Any]:
    """
    加载图谱 JSON 文件

    Args:
        graph_dir: graph 目录路径

    Returns:
        dict: 图谱数据 {"nodes": [...], "edges": [...]}

        注意：graphify 0.9.10+ 使用 hyperedges 格式，会自动转换为标准 edges

    Raises:
        FileNotFoundError: 如果 graph.json 不存在
    """
    graph_file = graph_dir / "graph.json"

    if not graph_file.exists():
        raise FileNotFoundError(f"Graph file not found: {graph_file}")

    with open(graph_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 如果是 graphify 0.9.10+ 的 hyperedges 格式，转换为标准 edges
    if "edges" not in data and "graph" in data and "hyperedges" in data["graph"]:
        data["edges"] = _convert_hyperedges_to_edges(data["graph"]["hyperedges"])

    return data


def _convert_hyperedges_to_edges(hyperedges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将 graphify 0.9.10+ 的 hyperedges 格式转换为标准 edges

    hyperedge 格式：{"nodes": [n1, n2, n3], "relation": "..."}
    转换为：多条边 [(n1, n2), (n1, n3), (n2, n3)]

    Args:
        hyperedges: hyperedges 列表

    Returns:
        list[dict]: 标准 edges 列表
    """
    edges = []

    for hedge in hyperedges:
        nodes = hedge.get("nodes", [])
        relation = hedge.get("relation", "related")

        # 将 hyperedge 转换为完全图（所有节点两两相连）
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                edges.append({
                    "source": nodes[i],
                    "target": nodes[j],
                    "relation": relation
                })

    return edges


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
    topic: str,
    include_refs: bool = False
) -> List[str]:
    """
    按主题查找论文

    Args:
        graph_dir: graph 目录路径
        topic: 主题关键词（大小写不敏感）
               支持多词查询（如 "deep learning"），会分词匹配
        include_refs: 是否包含引用文献节点（默认 False，只返回本地论文）

    Returns:
        list[str]: 匹配的 storage_id 列表（本地论文）或节点 ID 列表（包含引用）

    Raises:
        FileNotFoundError: 如果 graph.json 不存在
    """
    # 加载图谱
    graph = _load_graph(graph_dir)
    nodes = graph.get("nodes", [])

    # 规范化主题（小写）
    topic_lower = topic.lower().strip()

    # 分词：按空格分割，过滤空字符串
    keywords = [kw for kw in topic_lower.split() if kw]

    # 查找匹配的论文节点
    matched_papers = set()

    for node in nodes:
        # 只处理 paper 类型的节点
        # graphify 0.9.10+ 使用 file_type 字段
        if node.get("file_type") != "paper":
            continue

        node_id = node.get("id")

        # 节点过滤逻辑
        if include_refs:
            # 包含引用文献：匹配标准节点 + 引用论文节点，但排除引用条目节点 (_ref_N)
            if not node_id or "_ref_" in node_id:
                continue
        else:
            # 仅本地论文：只保留标准格式 (p_xxxxxxxxxxxx)
            if not node_id or not re.match(r'^p_[0-9a-f]{12}$', node_id):
                continue
        label = node.get("label", "")
        norm_label = node.get("norm_label", "")

        # 构建搜索文本（合并多个字段）
        search_text = " ".join([
            label.lower(),
            norm_label.lower(),
        ])

        # 匹配策略：
        # 1. 如果只有一个关键词，直接子串匹配
        # 2. 如果有多个关键词，任意一个匹配即算匹配
        matched = False
        if len(keywords) == 1:
            # 单词查询：完整子串匹配
            if keywords[0] in search_text:
                matched = True
        else:
            # 多词查询：任意词匹配
            for kw in keywords:
                if kw in search_text:
                    matched = True
                    break

        if matched:
            matched_papers.add(node_id)

    return sorted(list(matched_papers))
