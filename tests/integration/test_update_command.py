"""集成测试: paperbase update 命令"""

import json
import pytest
from pathlib import Path
from click.testing import CliRunner
from paperbase.cli.main import main


@pytest.fixture
def runner():
    """Click CLI runner"""
    return CliRunner()


@pytest.fixture
def test_paper(tmp_path):
    """创建测试论文"""
    from paperbase.core.registry import PaperRegistry
    from paperbase.core.paths import PaperPaths
    from paperbase.schemas.paper import PaperMetadata
    from paperbase.schemas.manifest import ManifestSchema, CanonicalMD
    from paperbase.core.manifest import save_manifest
    import yaml

    # 创建目录结构
    library_dir = tmp_path / "library" / "papers"
    library_dir.mkdir(parents=True)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(parents=True)

    # 创建论文
    paper_id = "doi:10.1234/test"
    storage_id = "test-2024-nature-vision"
    paths = PaperPaths(storage_id=storage_id, base_dir=tmp_path)
    paths.paper_dir.mkdir(parents=True)

    # 创建 paper.md
    from paperbase.schemas.paper import PaperAuthor

    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id=paper_id,
        storage_id=storage_id,
        title="Test Paper",
        year=2024,
        authors=[PaperAuthor(name="Alice")],
        abstract="Test abstract",
        entities={}
    )

    frontmatter = metadata.model_dump(mode="json", exclude_none=True)
    yaml_str = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
    content = f"---\n{yaml_str}---\n\n# Test Paper\n\nContent here.\n"

    paths.paper_md.write_text(content, encoding="utf-8")

    # 创建 manifest.json
    from paperbase.utils.hash import sha256_string
    manifest = ManifestSchema(
        paper_id=paper_id,
        storage_id=storage_id,
        state="ready",
        canonical_md=CanonicalMD(
            path="./paper.md",
            sha256=sha256_string(content),
            schema_version="1.0"
        )
    )
    save_manifest(manifest, paths.manifest_json)

    # 注册到 registry
    from paperbase.schemas.manifest import PaperState

    registry = PaperRegistry(registry_dir / "papers.db")
    registry.register_paper(
        paper_id=paper_id,
        storage_id=storage_id,
        state=PaperState.READY,
        title="Test Paper",
        year=2024
    )
    registry.close()

    return {
        "base_dir": tmp_path,
        "paper_id": paper_id,
        "storage_id": storage_id,
        "paths": paths
    }


def test_update_replace_mode(runner, test_paper):
    """测试替换模式更新实体"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]

    entities_json = json.dumps({
        "methods": [{"name": "SLAM", "description": "Simultaneous Localization and Mapping"}],
        "datasets": [{"name": "KITTI"}]
    })

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--json", entities_json
    ])

    assert result.exit_code == 0
    assert "成功更新实体" in result.output

    # 验证 paper.md 被更新
    paths = test_paper["paths"]
    content = paths.paper_md.read_text(encoding="utf-8")
    assert "SLAM" in content
    assert "KITTI" in content


def test_update_merge_mode(runner, test_paper):
    """测试合并模式更新实体"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]
    paths = test_paper["paths"]

    # 先添加一些实体
    entities_json_1 = json.dumps({
        "methods": [{"name": "SLAM"}]
    })
    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--json", entities_json_1
    ])
    assert result.exit_code == 0

    # 合并新实体
    entities_json_2 = json.dumps({
        "methods": [{"name": "ORB-SLAM"}],
        "datasets": [{"name": "KITTI"}]
    })
    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--merge",
        "--json", entities_json_2
    ])
    assert result.exit_code == 0

    # 验证两个 method 都存在
    content = paths.paper_md.read_text(encoding="utf-8")
    assert "SLAM" in content
    assert "ORB-SLAM" in content
    assert "KITTI" in content


def test_update_invalid_paper_id(runner, test_paper):
    """测试无效的 paper_id"""
    base_dir = test_paper["base_dir"]

    entities_json = json.dumps({"methods": [{"name": "SLAM"}]})

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        "doi:invalid",
        "--json", entities_json
    ])

    assert result.exit_code == 1
    assert "未找到论文" in result.output


def test_update_invalid_json(runner, test_paper):
    """测试无效的 JSON"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--json", "{invalid json"
    ])

    assert result.exit_code == 1
    assert "JSON" in result.output


def test_update_output_json(runner, test_paper):
    """测试 --output-json 格式"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]

    entities_json = json.dumps({
        "methods": [{"name": "SLAM"}]
    })

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--json", entities_json,
        "--output-json"
    ])

    assert result.exit_code == 0

    # 解析 JSON 输出
    output_data = json.loads(result.output)
    assert output_data["success"] is True
    assert output_data["paper_id"] == paper_id


def test_update_missing_json_input(runner, test_paper):
    """测试缺少 --json 参数"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id
    ])

    # Click 在缺少必需参数时返回 exit code 2
    assert result.exit_code == 2
    assert "--json" in result.output or "required" in result.output.lower()


def test_update_schema_validation_error(runner, test_paper):
    """测试 schema 验证失败"""
    base_dir = test_paper["base_dir"]
    paper_id = test_paper["paper_id"]

    # 无效的实体格式（缺少 name 字段）
    entities_json = json.dumps({
        "methods": [{"description": "Invalid entity"}]
    })

    result = runner.invoke(main, [
        "--base-dir", str(base_dir),
        "update",
        paper_id,
        "--json", entities_json
    ])

    assert result.exit_code == 1
    assert "验证失败" in result.output
