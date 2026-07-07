"""Unit tests for EntityGraphBuilder"""

import json
from pathlib import Path
import pytest
from paperbase.core.entity_graph_builder import EntityGraphBuilder


@pytest.fixture
def temp_library(tmp_path):
    """创建临时 library 目录结构"""
    library_dir = tmp_path / "library" / "papers"
    library_dir.mkdir(parents=True)

    # Paper 1: 包含多种实体
    paper1_dir = library_dir / "paper1"
    paper1_dir.mkdir()
    paper1_md = paper1_dir / "paper.md"
    paper1_md.write_text("""---
schema_version: '1.0'
paper_id: doi:10.1038/nature01
storage_id: paper1
title: Sample Paper 1
authors:
  - name: Alice
year: 2023
abstract: Test abstract
entities:
  methods:
    - name: SLAM
      type: Method
      confidence: 0.9
    - name: Deep Learning
      type: Method
      confidence: 0.85
  datasets:
    - name: ImageNet
      type: Dataset
      confidence: 0.95
  domains:
    - name: Computer Vision
      type: Domain
---
# Content
""", encoding="utf-8")

    # Paper 2: 包含部分重复实体
    paper2_dir = library_dir / "paper2"
    paper2_dir.mkdir()
    paper2_md = paper2_dir / "paper.md"
    paper2_md.write_text("""---
schema_version: '1.0'
paper_id: doi:10.1038/nature02
storage_id: paper2
title: Sample Paper 2
authors:
  - name: Bob
year: 2024
abstract: Test abstract 2
entities:
  methods:
    - name: SLAM
      type: Method
      confidence: 0.88
  platforms:
    - name: ROS
      type: Platform
      confidence: 0.92
---
# Content 2
""", encoding="utf-8")

    # Paper 3: 无 entities 字段
    paper3_dir = library_dir / "paper3"
    paper3_dir.mkdir()
    paper3_md = paper3_dir / "paper.md"
    paper3_md.write_text("""---
schema_version: '1.0'
paper_id: doi:10.1038/nature03
storage_id: paper3
title: Sample Paper 3
authors:
  - name: Carol
year: 2024
abstract: Test abstract 3
---
# Content 3
""", encoding="utf-8")

    return tmp_path


class TestEntityExtraction:
    """测试实体提取功能"""

    def test_extract_all_entities_from_multiple_papers(self, temp_library):
        """Step 1: 从多篇论文提取实体"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")

        # 验证提取了2篇有实体的论文
        assert len(entities_dict) == 2
        assert "doi:10.1038/nature01" in entities_dict
        assert "doi:10.1038/nature02" in entities_dict

        # 验证 paper1 的实体
        paper1_entities = entities_dict["doi:10.1038/nature01"]
        assert "methods" in paper1_entities
        assert len(paper1_entities["methods"]) == 2
        assert paper1_entities["methods"][0]["name"] == "SLAM"

        # 验证 paper2 的实体
        paper2_entities = entities_dict["doi:10.1038/nature02"]
        assert "methods" in paper2_entities
        assert "platforms" in paper2_entities

    def test_extract_handles_empty_entities(self, temp_library):
        """测试处理空 entities 字段"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")

        # paper3 没有 entities，不应出现在结果中
        assert "doi:10.1038/nature03" not in entities_dict

    def test_extract_handles_empty_library(self, tmp_path):
        """测试处理空 library"""
        empty_lib = tmp_path / "empty_library"
        empty_lib.mkdir()

        builder = EntityGraphBuilder(base_dir=tmp_path)
        entities_dict = builder.extract_all_entities(empty_lib)

        assert entities_dict == {}


class TestNodeGeneration:
    """测试节点生成功能"""

    def test_build_entity_nodes_deduplication(self, temp_library):
        """Step 3: 实体去重"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")

        nodes = builder.build_entity_nodes(entities_dict)

        # 验证节点数量（SLAM 应该去重）
        # paper1: SLAM, Deep Learning, ImageNet, Computer Vision (4)
        # paper2: SLAM (重复), ROS (1 新)
        # 总计: 5 个唯一实体
        assert len(nodes) == 5

        # 验证节点格式
        slam_node = next((n for n in nodes if n["name"] == "SLAM"), None)
        assert slam_node is not None
        assert slam_node["id"] == "method:SLAM"
        assert slam_node["type"] == "Method"
        assert slam_node["category"] == "methods"

    def test_build_entity_nodes_all_categories(self, temp_library):
        """测试所有类别的实体"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")
        nodes = builder.build_entity_nodes(entities_dict)

        # 验证不同类别的节点
        categories = {n["category"] for n in nodes}
        assert "methods" in categories
        assert "datasets" in categories
        assert "domains" in categories
        assert "platforms" in categories

    def test_build_entity_nodes_empty_input(self, temp_library):
        """测试空输入"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        nodes = builder.build_entity_nodes({})

        assert nodes == []


class TestEdgeGeneration:
    """测试边生成功能"""

    def test_build_entity_edges_correct_relations(self, temp_library):
        """Step 5: 生成正确的关系边"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")

        edges = builder.build_entity_edges(entities_dict)

        # paper1: 4 个实体 -> 4 条边
        # paper2: 2 个实体 -> 2 条边
        assert len(edges) == 6

        # 验证边格式
        slam_edges = [e for e in edges if e["target"] == "method:SLAM"]
        assert len(slam_edges) == 2  # paper1 和 paper2 都用了 SLAM

        # 验证关系类型
        method_edge = next((e for e in edges if e["relation"] == "uses_method"), None)
        assert method_edge is not None
        assert method_edge["target"].startswith("method:")

    def test_build_entity_edges_relation_mapping(self, temp_library):
        """测试关系映射"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")
        edges = builder.build_entity_edges(entities_dict)

        # 验证关系映射
        relations = {e["relation"] for e in edges}
        assert "uses_method" in relations
        assert "uses_dataset" in relations
        assert "in_domain" in relations
        assert "on_platform" in relations

    def test_build_entity_edges_empty_input(self, temp_library):
        """测试空输入"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        edges = builder.build_entity_edges({})

        assert edges == []


class TestJSONLExport:
    """测试 JSONL 导出功能"""

    def test_export_to_jsonl_format(self, temp_library, tmp_path):
        """Step 7: 导出 JSONL 格式"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")
        nodes = builder.build_entity_nodes(entities_dict)
        edges = builder.build_entity_edges(entities_dict)

        output_path = tmp_path / "entities.jsonl"
        builder.export_to_jsonl(nodes, edges, output_path)

        # 验证文件存在
        assert output_path.exists()

        # 验证每行都是有效 JSON
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == len(nodes) + len(edges)

        # 验证第一行是节点
        first_obj = json.loads(lines[0])
        assert "id" in first_obj
        assert "type" in first_obj
        assert "name" in first_obj

        # 验证最后一行是边
        last_obj = json.loads(lines[-1])
        assert "source" in last_obj
        assert "target" in last_obj
        assert "relation" in last_obj

    def test_export_to_jsonl_utf8_encoding(self, temp_library, tmp_path):
        """测试 UTF-8 编码"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        entities_dict = builder.extract_all_entities(temp_library / "library")
        nodes = builder.build_entity_nodes(entities_dict)
        edges = builder.build_entity_edges(entities_dict)

        output_path = tmp_path / "entities.jsonl"
        builder.export_to_jsonl(nodes, edges, output_path)

        # 验证可以用 UTF-8 读取
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert len(content) > 0

    def test_export_to_jsonl_empty_data(self, temp_library, tmp_path):
        """测试空数据导出"""
        builder = EntityGraphBuilder(base_dir=temp_library)
        output_path = tmp_path / "empty.jsonl"

        builder.export_to_jsonl([], [], output_path)

        assert output_path.exists()
        assert output_path.stat().st_size == 0


class TestEndToEnd:
    """端到端测试"""

    def test_full_pipeline(self, temp_library, tmp_path):
        """测试完整流程"""
        builder = EntityGraphBuilder(base_dir=temp_library)

        # 提取
        entities_dict = builder.extract_all_entities(temp_library / "library")
        assert len(entities_dict) == 2

        # 生成节点
        nodes = builder.build_entity_nodes(entities_dict)
        assert len(nodes) == 5

        # 生成边
        edges = builder.build_entity_edges(entities_dict)
        assert len(edges) == 6

        # 导出
        output_path = tmp_path / "full_test.jsonl"
        builder.export_to_jsonl(nodes, edges, output_path)
        assert output_path.exists()

        # 验证可以重新加载
        with open(output_path, "r", encoding="utf-8") as f:
            objects = [json.loads(line) for line in f]

        assert len(objects) == 11  # 5 nodes + 6 edges
