import pytest
import json
from pathlib import Path
from paperbase.core.manifest import load_manifest, save_manifest, create_manifest
from paperbase.schemas.manifest import PaperState


def test_create_manifest():
    """测试创建 manifest"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )
    assert manifest.paper_id == "doi:10.1234/test"
    assert manifest.storage_id == "p_abc123"
    assert manifest.state == PaperState.NORMALIZED


def test_save_and_load_manifest(tmp_path):
    """测试保存和加载 manifest"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )

    manifest_path = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_path)

    assert manifest_path.exists()

    loaded = load_manifest(manifest_path)
    assert loaded.paper_id == manifest.paper_id
    assert loaded.state == manifest.state


def test_manifest_json_format(tmp_path):
    """测试 manifest JSON 格式"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )
    manifest.state = PaperState.READY

    manifest_path = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_path)

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["paper_id"] == "doi:10.1234/test"
    assert data["state"] == "ready"
