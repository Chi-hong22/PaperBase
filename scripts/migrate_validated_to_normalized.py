"""迁移 VALIDATED 状态的论文到 NORMALIZED 状态"""
from pathlib import Path
from paperbase.core.manifest import load_manifest, save_manifest
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def migrate_validated_papers(base_dir: Path):
    """将所有 VALIDATED 状态的论文迁移到 NORMALIZED"""
    library_dir = base_dir / "library"
    registry_path = base_dir / "registry" / "papers.db"

    if not registry_path.exists():
        print("Registry not found")
        return

    registry = PaperRegistry(registry_path)
    try:
        validated_papers = registry.list_papers(state=PaperState.VALIDATED)
    finally:
        registry.close()

    if not validated_papers:
        print("No VALIDATED papers found")
        return

    print(f"Found {len(validated_papers)} VALIDATED papers")

    migrated = 0
    for paper in validated_papers:
        storage_id = paper["storage_id"]
        paper_id = paper["paper_id"]
        manifest_path = library_dir / storage_id / "manifest.json"

        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            manifest.state = PaperState.NORMALIZED
            save_manifest(manifest, manifest_path)

            registry = PaperRegistry(registry_path)
            try:
                registry.update_state(paper_id, PaperState.NORMALIZED)
            finally:
                registry.close()

            migrated += 1
            print(f"✓ Migrated: {paper_id}")
        else:
            print(f"✗ Manifest not found: {storage_id}")

    print(f"\nTotal migrated: {migrated}/{len(validated_papers)}")


if __name__ == "__main__":
    migrate_validated_papers(Path.cwd())
