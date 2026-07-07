"""Entity Manager 单元测试"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from paperbase.core.entity_manager import EntityManager
from paperbase.core.paths import PaperPaths
from paperbase.core.manifest import load_manifest, save_manifest, create_manifest
from paperbase.schemas.manifest import ManifestSchema
from paperbase.utils.hash import sha256_string
import yaml
import json


@pytest.fixture
def temp_paper_dir(tmp_path):
    """创建临时论文目录结构"""
    base_dir = tmp_path
    storage_id = "test_paper_001"

    # 创建目录结构
    paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
    paths.create_directories()

    # 创建 paper.md
    paper_content = """---
schema_version: "1.0"
paper_id: "doi:10.1234/test"
storage_id: "test_paper_001"
title: "Test Paper"
authors:
  - name: "John Doe"
year: 2024
abstract: "This is a test abstract."
provenance:
  ingested_at: "2024-01-01T00:00:00Z"
  converter:
    name: "test"
    version: "1.0"
  normalizer:
    name: "test"
    version: "1.0"
  canonical_content_sha256: "0000000000000000000000000000000000000000000000000000000000000000"
entities:
  methods:
    - name: "SLAM"
      type: "algorithm"
---

# Test Paper

This is the paper content.
"""

    with open(paths.paper_md, "w", encoding="utf-8") as f:
        f.write(paper_content)

    # 创建 manifest.json
    from paperbase.schemas.manifest import CanonicalMD
    manifest = create_manifest(paper_id="doi:10.1234/test", storage_id=storage_id)
    manifest.canonical_md = CanonicalMD(
        path="./paper.md",
        sha256=sha256_string(paper_content),
        schema_version="1.0"
    )
    save_manifest(manifest, paths.manifest_json)

    return {
        "base_dir": base_dir,
        "storage_id": storage_id,
        "paths": paths,
        "paper_content": paper_content
    }


class TestEntityManager:
    """EntityManager 测试"""

    def test_init_with_default_llm_client(self, temp_paper_dir):
        """测试：默认初始化（不启用 LLM）"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])
        assert manager.base_dir == temp_paper_dir["base_dir"]
        assert manager.llm_client is not None
        assert manager.llm_client.enabled is False

    def test_init_with_custom_llm_client(self, temp_paper_dir):
        """测试：使用自定义 LLM 客户端"""
        from paperbase.core.llm_client import LLMClient

        llm_client = LLMClient(config={"llm": {"enabled": True}})
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"], llm_client=llm_client)
        assert manager.llm_client is llm_client

    def test_update_entities_replace_mode(self, temp_paper_dir):
        """测试：更新实体（替换模式）"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        new_entities = {
            "methods": [
                {"name": "Particle Filter", "type": "localization"},
                {"name": "submap", "type": "mapping"}
            ],
            "datasets": [
                {"name": "AQUALOC"}
            ]
        }

        manager.update_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"],
            entities_dict=new_entities,
            merge=False
        )

        # 验证 paper.md 已更新
        paths = temp_paper_dir["paths"]
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 frontmatter
        parts = content.split("---\n")
        assert len(parts) >= 3
        frontmatter = yaml.safe_load(parts[1])

        # 验证 entities 字段
        assert "entities" in frontmatter
        assert frontmatter["entities"]["methods"] == new_entities["methods"]
        assert frontmatter["entities"]["datasets"] == new_entities["datasets"]
        assert "methods" in frontmatter["entities"]
        assert len(frontmatter["entities"]["methods"]) == 2

    def test_update_entities_merge_mode(self, temp_paper_dir):
        """测试：更新实体（合并模式）"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        # 第一次更新
        first_entities = {
            "methods": [
                {"name": "SLAM", "type": "algorithm"}
            ]
        }
        manager.update_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"],
            entities_dict=first_entities,
            merge=False
        )

        # 第二次更新（合并模式）
        additional_entities = {
            "methods": [
                {"name": "Particle Filter", "type": "localization"}
            ],
            "datasets": [
                {"name": "AQUALOC"}
            ]
        }
        manager.update_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"],
            entities_dict=additional_entities,
            merge=True
        )

        # 验证合并结果
        paths = temp_paper_dir["paths"]
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            content = f.read()

        parts = content.split("---\n")
        frontmatter = yaml.safe_load(parts[1])

        # 验证 methods 已合并
        assert len(frontmatter["entities"]["methods"]) == 2
        method_names = [m["name"] for m in frontmatter["entities"]["methods"]]
        assert "SLAM" in method_names
        assert "Particle Filter" in method_names

        # 验证 datasets 已添加
        assert "datasets" in frontmatter["entities"]
        assert len(frontmatter["entities"]["datasets"]) == 1

    def test_update_entities_validates_schema(self, temp_paper_dir):
        """测试：更新实体时验证 schema"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        # 尝试更新不合法的 entities（confidence 超出范围）
        invalid_entities = {
            "methods": [
                {"name": "SLAM", "confidence": 1.5}  # confidence 必须 0-1
            ]
        }

        with pytest.raises(ValueError, match="confidence"):
            manager.update_entities(
                paper_id="doi:10.1234/test",
                storage_id=temp_paper_dir["storage_id"],
                entities_dict=invalid_entities,
                merge=False
            )

    def test_update_entities_updates_manifest_hash(self, temp_paper_dir):
        """测试：更新实体后更新 manifest.json 的 sha256"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        # 记录原始 hash
        paths = temp_paper_dir["paths"]
        manifest_before = load_manifest(paths.manifest_json)
        old_hash = manifest_before.canonical_md.sha256

        # 更新 entities
        new_entities = {
            "methods": [
                {"name": "New Method"}
            ]
        }
        manager.update_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"],
            entities_dict=new_entities,
            merge=False
        )

        # 验证 manifest hash 已更新
        manifest_after = load_manifest(paths.manifest_json)
        new_hash = manifest_after.canonical_md.sha256

        assert new_hash != old_hash

        # 验证 hash 与实际文件内容一致
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            actual_content = f.read()
        expected_hash = sha256_string(actual_content)
        assert new_hash == expected_hash

    def test_auto_extract_entities_with_llm_enabled(self, temp_paper_dir):
        """测试：自动提取实体（LLM 启用）"""
        # Mock LLM 客户端
        mock_llm_client = Mock()
        mock_llm_client.enabled = True
        mock_llm_client.extract_entities.return_value = {
            "methods": [
                {"name": "SLAM", "type": "algorithm"}
            ],
            "datasets": [
                {"name": "TestDataset"}
            ]
        }

        manager = EntityManager(
            base_dir=temp_paper_dir["base_dir"],
            llm_client=mock_llm_client
        )

        result = manager.auto_extract_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"]
        )

        # 验证返回结果
        assert result is not None
        assert "methods" in result
        assert "datasets" in result

        # 验证调用了 LLM
        mock_llm_client.extract_entities.assert_called_once()

        # 验证 entities 已更新到 paper.md
        paths = temp_paper_dir["paths"]
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            content = f.read()

        parts = content.split("---\n")
        frontmatter = yaml.safe_load(parts[1])
        assert "entities" in frontmatter
        assert len(frontmatter["entities"]["methods"]) == 1
        assert frontmatter["entities"]["methods"][0]["name"] == "SLAM"

    def test_auto_extract_entities_with_llm_disabled(self, temp_paper_dir):
        """测试：自动提取实体（LLM 禁用）"""
        # 使用默认的 LLM 客户端（禁用）
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        result = manager.auto_extract_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"]
        )

        # 验证返回 None
        assert result is None

    def test_auto_extract_entities_llm_failure(self, temp_paper_dir):
        """测试：自动提取实体（LLM 失败）"""
        # Mock LLM 客户端返回 None（失败）
        mock_llm_client = Mock()
        mock_llm_client.enabled = True
        mock_llm_client.extract_entities.return_value = None

        manager = EntityManager(
            base_dir=temp_paper_dir["base_dir"],
            llm_client=mock_llm_client
        )

        result = manager.auto_extract_entities(
            paper_id="doi:10.1234/test",
            storage_id=temp_paper_dir["storage_id"]
        )

        # 验证返回 None
        assert result is None

    def test_update_entities_file_not_found(self, temp_paper_dir):
        """测试：更新不存在的论文"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        with pytest.raises(FileNotFoundError):
            manager.update_entities(
                paper_id="doi:10.1234/nonexistent",
                storage_id="nonexistent_paper",
                entities_dict={"methods": []},
                merge=False
            )

    def test_update_entities_invalid_frontmatter(self, temp_paper_dir):
        """测试：处理格式错误的 paper.md"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        # 写入格式错误的 paper.md
        paths = temp_paper_dir["paths"]
        with open(paths.paper_md, "w", encoding="utf-8") as f:
            f.write("This is not valid frontmatter\n\nContent")

        with pytest.raises(ValueError, match="frontmatter"):
            manager.update_entities(
                paper_id="doi:10.1234/test",
                storage_id=temp_paper_dir["storage_id"],
                entities_dict={"methods": []},
                merge=False
            )

    def test_update_entities_atomic_write(self, temp_paper_dir):
        """测试：原子性写入（失败不损坏原文件）"""
        manager = EntityManager(base_dir=temp_paper_dir["base_dir"])

        paths = temp_paper_dir["paths"]

        # 读取原始内容
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            original_content = f.read()

        # Mock 写入失败
        with patch("builtins.open", side_effect=IOError("Disk full")):
            with pytest.raises(Exception):
                manager.update_entities(
                    paper_id="doi:10.1234/test",
                    storage_id=temp_paper_dir["storage_id"],
                    entities_dict={"methods": []},
                    merge=False
                )

        # 验证原文件未损坏
        with open(paths.paper_md, "r", encoding="utf-8") as f:
            current_content = f.read()

        assert current_content == original_content

        # 验证没有残留 .tmp 文件
        tmp_files = list(paths.paper_dir.glob("*.tmp"))
        assert len(tmp_files) == 0
