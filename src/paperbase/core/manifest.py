"""Manifest 管理工具"""

import json
from pathlib import Path
from datetime import datetime, UTC
from paperbase.schemas.manifest import ManifestSchema, PaperState


def create_manifest(paper_id: str, storage_id: str) -> ManifestSchema:
    """创建新的 manifest"""
    now = datetime.now(UTC).isoformat()
    return ManifestSchema(
        paper_id=paper_id,
        storage_id=storage_id,
        state=PaperState.DISCOVERED,
        created_at=now,
        updated_at=now
    )


def load_manifest(path: Path) -> ManifestSchema:
    """从文件加载 manifest"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ManifestSchema.model_validate(data)


def save_manifest(manifest: ManifestSchema, path: Path):
    """保存 manifest 到文件"""
    path.parent.mkdir(parents=True, exist_ok=True)

    # 更新 updated_at
    manifest.updated_at = datetime.now(UTC).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            manifest.model_dump(mode="json", exclude_none=True),
            f,
            indent=2,
            ensure_ascii=False
        )
