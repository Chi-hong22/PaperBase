"""Unit tests for entity query functionality"""

import json
from pathlib import Path
import pytest
from paperbase.core.graph_query import find_papers_by_entity


@pytest.fixture
def temp_graph_with_entities(tmp_path):
    """创建包含 entities.jsonl 的临时图谱"""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()

    # 创建 entities.jsonl
    entities_file = graph_dir / "entities.jsonl"

    # 节点：实体
    nodes = [
        {"id": "method:SLAM", "type": "Method", "name": "SLAM", "category": "methods"},
        {"id": "method:Deep Learning", "type": "Method", "name": "Deep Learning", "category": "methods"},
        {"id": "dataset:ImageNet", "type": "Dataset", "name": "ImageNet", "category": "datasets"},
        {"id": "domain:Computer Vision", "type": "Domain", "name": "Computer Vision", "category": "domains"},
        {"id": "platform:ROS", "type": "Platform", "name": "ROS", "category": "platforms"},
    ]

    # 边：Paper -> Entity
    edges = [
        {"source": "doi:10.1038/nature01", "target": "method:SLAM", "relation": "uses_method"},
        {"source": "doi:10.1038/nature01", "target": "method:Deep Learning", "relation": "uses_method"},
        {"source": "doi:10.1038/nature01", "target": "dataset:ImageNet", "relation": "uses_dataset"},
        {"source": "doi:10.1038/nature01", "target": "domain:Computer Vision", "relation": "in_domain"},
        {"source": "doi:10.1038/nature02", "target": "method:SLAM", "relation": "uses_method"},
        {"source": "doi:10.1038/nature02", "target": "platform:ROS", "relation": "on_platform"},
    ]

    with open(entities_file, "w", encoding="utf-8") as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    return graph_dir


@pytest.fixture
def temp_graph_with_graph_json_only(tmp_path):
    """创建只有 graph.json 的临时图谱（fallback 场景）"""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()

    # 创建 graph.json（包含实体节点和边）
    graph_file = graph_dir / "graph.json"

    graph_data = {
        "nodes": [
            {"id": "doi:10.1038/nature01", "type": "paper", "attributes": {}},
            {"id": "doi:10.1038/nature02", "type": "paper", "attributes": {}},
            {"id": "method:SLAM", "type": "Method", "name": "SLAM", "category": "methods"},
            {"id": "dataset:KITTI", "type": "Dataset", "name": "KITTI", "category": "datasets"},
        ],
        "edges": [
            {"source": "doi:10.1038/nature01", "target": "method:SLAM", "relation": "uses_method"},
            {"source": "doi:10.1038/nature02", "target": "method:SLAM", "relation": "uses_method"},
            {"source": "doi:10.1038/nature02", "target": "dataset:KITTI", "relation": "uses_dataset"},
        ]
    }

    with open(graph_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    return graph_dir


class TestEntityQueryBasic:
    """测试基本实体查询功能"""

    def test_find_papers_by_entity_single_match(self, temp_graph_with_entities):
        """Step 1: 查找使用特定实体的论文（单个匹配）"""
        papers = find_papers_by_entity(temp_graph_with_entities, "dataset:ImageNet")

        assert papers == ["doi:10.1038/nature01"]

    def test_find_papers_by_entity_multiple_matches(self, temp_graph_with_entities):
        """Step 2: 查找使用特定实体的论文（多个匹配）"""
        papers = find_papers_by_entity(temp_graph_with_entities, "methods:SLAM")

        # SLAM 被两篇论文使用
        assert len(papers) == 2
        assert "doi:10.1038/nature01" in papers
        assert "doi:10.1038/nature02" in papers

        # 验证排序
        assert papers == sorted(papers)

    def test_find_papers_by_entity_no_match(self, temp_graph_with_entities):
        """Step 3: 查找不存在的实体"""
        papers = find_papers_by_entity(temp_graph_with_entities, "methods:NonExistent")

        assert papers == []


class TestEntityQueryCaseInsensitive:
    """测试大小写不敏感匹配"""

    def test_find_papers_case_insensitive_category(self, temp_graph_with_entities):
        """Step 4: 类别大小写不敏感"""
        papers_lower = find_papers_by_entity(temp_graph_with_entities, "methods:SLAM")
        papers_upper = find_papers_by_entity(temp_graph_with_entities, "METHODS:SLAM")
        papers_mixed = find_papers_by_entity(temp_graph_with_entities, "Methods:SLAM")

        assert papers_lower == papers_upper == papers_mixed

    def test_find_papers_case_insensitive_name(self, temp_graph_with_entities):
        """Step 5: 实体名称大小写不敏感"""
        papers_exact = find_papers_by_entity(temp_graph_with_entities, "methods:SLAM")
        papers_lower = find_papers_by_entity(temp_graph_with_entities, "methods:slam")
        papers_upper = find_papers_by_entity(temp_graph_with_entities, "methods:SLAM")

        assert papers_exact == papers_lower == papers_upper

    def test_find_papers_case_insensitive_full(self, temp_graph_with_entities):
        """Step 6: 完整过滤器大小写不敏感"""
        papers_normal = find_papers_by_entity(temp_graph_with_entities, "datasets:ImageNet")
        papers_lower = find_papers_by_entity(temp_graph_with_entities, "datasets:imagenet")
        papers_upper = find_papers_by_entity(temp_graph_with_entities, "DATASETS:IMAGENET")

        assert papers_normal == papers_lower == papers_upper


class TestEntityQueryFallback:
    """测试 fallback 到 graph.json"""

    def test_find_papers_fallback_to_graph_json(self, temp_graph_with_graph_json_only):
        """Step 7: 当 entities.jsonl 不存在时，fallback 到 graph.json"""
        papers = find_papers_by_entity(temp_graph_with_graph_json_only, "methods:SLAM")

        assert len(papers) == 2
        assert "doi:10.1038/nature01" in papers
        assert "doi:10.1038/nature02" in papers

    def test_find_papers_fallback_case_insensitive(self, temp_graph_with_graph_json_only):
        """Step 8: fallback 模式下大小写不敏感"""
        papers = find_papers_by_entity(temp_graph_with_graph_json_only, "datasets:kitti")

        assert papers == ["doi:10.1038/nature02"]


class TestEntityQueryEdgeCases:
    """测试边界情况"""

    def test_find_papers_invalid_filter_format(self, temp_graph_with_entities):
        """测试无效的过滤器格式"""
        # 缺少冒号
        papers = find_papers_by_entity(temp_graph_with_entities, "methodsSLAM")
        assert papers == []

    def test_find_papers_empty_filter(self, temp_graph_with_entities):
        """测试空过滤器"""
        papers = find_papers_by_entity(temp_graph_with_entities, "")
        assert papers == []

    def test_find_papers_graph_dir_not_exists(self, tmp_path):
        """测试图谱目录不存在"""
        non_existent = tmp_path / "non_existent"

        with pytest.raises(FileNotFoundError):
            find_papers_by_entity(non_existent, "methods:SLAM")

    def test_find_papers_no_graph_files(self, tmp_path):
        """测试图谱文件都不存在"""
        empty_graph = tmp_path / "empty_graph"
        empty_graph.mkdir()

        with pytest.raises(FileNotFoundError):
            find_papers_by_entity(empty_graph, "methods:SLAM")
