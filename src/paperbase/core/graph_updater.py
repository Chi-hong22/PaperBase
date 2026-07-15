"""图谱增量更新检测模块"""

from pathlib import Path
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.utils.hash import sha256_file
from paperbase.schemas.manifest import ManifestSchema, PaperState


def detect_changed_papers(library_path: Path) -> list[dict]:
    """检测内容发生变化的论文

    返回需要重新图谱化的论文列表，每项包含：
    - storage_id: 存储 ID
    - paper_id: 论文 ID
    - reason: 变化原因
    """
    changed_papers = []

    # 遍历 library 目录
    for paper_dir in library_path.iterdir():
        if not paper_dir.is_dir():
            continue

        storage_id = paper_dir.name
        manifest_path = paper_dir / "manifest.json"

        if not manifest_path.exists():
            continue

        try:
            manifest = load_manifest(manifest_path)

            # 检查是否需要更新
            if should_update_graph(manifest):
                changed_papers.append({
                    "storage_id": storage_id,
                    "paper_id": manifest.paper_id,
                    "reason": _get_change_reason(manifest, paper_dir)
                })
        except Exception:
            # 跳过无法解析的 manifest
            continue

    return changed_papers


def should_update_graph(manifest: ManifestSchema) -> bool:
    """判断单篇论文是否需要更新图谱

    判断逻辑：
    1. 未图谱化 → 需要更新
    2. canonical_md SHA256 发生变化 → 需要更新
    3. graph.content_sha256_at_index 为空 → 需要更新（向后兼容）
    """
    # 已记录过同一份 Canonical 的质量问题时，等待内容哈希变化再重试。
    if (
        manifest.state == PaperState.NEEDS_REVIEW
        and manifest.graph
        and manifest.graph.content_sha256_at_index
        and manifest.canonical_md
        and manifest.canonical_md.sha256 == manifest.graph.content_sha256_at_index
    ):
        return False

    # 未图谱化
    if not manifest.graph or not manifest.graph.indexed:
        return True

    # 没有记录图谱化时的 SHA256（旧数据）
    if not manifest.graph.content_sha256_at_index:
        return True

    # 内容 SHA256 发生变化
    if manifest.canonical_md:
        current_sha256 = manifest.canonical_md.sha256
        indexed_sha256 = manifest.graph.content_sha256_at_index

        if current_sha256 != indexed_sha256:
            return True

    return False


def _get_change_reason(manifest: ManifestSchema, paper_dir: Path) -> str:
    """获取变化原因（用于日志）"""
    if not manifest.graph or not manifest.graph.indexed:
        return "未图谱化"

    if not manifest.graph.content_sha256_at_index:
        return "缺少 SHA256 记录"

    if manifest.canonical_md:
        current_sha256 = manifest.canonical_md.sha256
        indexed_sha256 = manifest.graph.content_sha256_at_index

        if current_sha256 != indexed_sha256:
            return f"内容变化 ({indexed_sha256[:8]}... → {current_sha256[:8]}...)"

    return "未知原因"
