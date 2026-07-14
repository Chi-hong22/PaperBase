from click.testing import CliRunner

from paperbase.cli.main import main
from paperbase.core.manifest import create_manifest, save_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def test_sync_treats_missing_canonical_as_orphan_even_if_resource_dir_exists(tmp_path):
    paper_id = "doi:10.1234/orphan"
    paths = PaperPaths(storage_id="p_orphan00001", base_dir=tmp_path)
    paths.create_directories()

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=paper_id,
            storage_id=paths.storage_id,
            state=PaperState.NORMALIZED,
            title="Orphaned record",
        )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "孤立记录" in result.output
    assert paper_id in result.output


def test_sync_dry_run_reports_unregistered_canonical_without_mutating_registry(tmp_path):
    paper_id = "doi:10.1234/unregistered"
    paths = PaperPaths(storage_id="p_unreg000001", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text(
        """---
paper_id: doi:10.1234/unregistered
storage_id: p_unreg000001
title: Unregistered Paper
authors:
  - name: Ada Lovelace
year: 2024
doi: 10.1234/unregistered
---
# Body
""",
        encoding="utf-8",
    )
    save_manifest(create_manifest(paper_id, paths.storage_id), paths.manifest_json)

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path):
        pass

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "Canonical 未注册" in result.output
    assert paths.storage_id in result.output
    with PaperRegistry(registry_path) as registry:
        assert registry.list_papers() == []


def test_sync_yes_deletes_orphans_and_rebuilds_unregistered_records(tmp_path):
    orphan_id = "doi:10.1234/orphan"
    orphan_paths = PaperPaths(storage_id="p_orphan00002", base_dir=tmp_path)
    orphan_paths.create_directories()

    rebuilt_id = "doi:10.1234/rebuilt"
    rebuilt_paths = PaperPaths(storage_id="p_rebuild00001", base_dir=tmp_path)
    rebuilt_paths.create_directories()
    rebuilt_paths.paper_md.write_text(
        """---
paper_id: doi:10.1234/rebuilt
storage_id: p_rebuild00001
title: Rebuilt Paper
authors:
  - name: Ada Lovelace
  - Grace Hopper
year: 2025
doi: 10.1234/rebuilt
---
# Body
""",
        encoding="utf-8",
    )
    manifest = create_manifest(rebuilt_id, rebuilt_paths.storage_id)
    manifest.state = PaperState.READY
    save_manifest(manifest, rebuilt_paths.manifest_json)

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=orphan_id,
            storage_id=orphan_paths.storage_id,
            state=PaperState.NORMALIZED,
            title="Orphaned record",
        )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync", "--yes"],
    )

    assert result.exit_code == 0, result.output
    with PaperRegistry(registry_path) as registry:
        assert registry.get_paper(orphan_id) is None
        rebuilt = registry.get_paper(rebuilt_id)

    assert rebuilt is not None
    assert {
        key: rebuilt[key]
        for key in ("paper_id", "storage_id", "state", "title", "authors", "year", "doi")
    } == {
        "paper_id": rebuilt_id,
        "storage_id": rebuilt_paths.storage_id,
        "state": "ready",
        "title": "Rebuilt Paper",
        "authors": ["Ada Lovelace", "Grace Hopper"],
        "year": 2025,
        "doi": "10.1234/rebuilt",
    }

    doctor_result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "doctor"],
    )
    assert "Registry and Canonical Markdown are consistent" in doctor_result.output


def test_sync_yes_reports_canonical_that_cannot_be_rebuilt(tmp_path):
    paths = PaperPaths(storage_id="p_invalid00001", base_dir=tmp_path)
    paths.paper_md.parent.mkdir(parents=True)
    paths.paper_md.write_text(
        """---
title: Missing Manifest
---
# Body
""",
        encoding="utf-8",
    )

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path):
        pass

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert "无法重建" in result.output
    assert paths.storage_id in result.output
    with PaperRegistry(registry_path) as registry:
        assert registry.list_papers() == []


def test_sync_interactive_prompt_describes_rebuild_when_only_canonical_is_unregistered(tmp_path):
    paper_id = "doi:10.1234/interactive"
    paths = PaperPaths(storage_id="p_interact001", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text(
        """---
title: Interactive Paper
authors: [Ada Lovelace]
year: 2025
doi: 10.1234/interactive
---
# Body
""",
        encoding="utf-8",
    )
    save_manifest(create_manifest(paper_id, paths.storage_id), paths.manifest_json)

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path):
        pass

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync"],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert "删除 0 条孤立记录，重建 1 条" in result.output
    assert "确认同步" in result.output
    with PaperRegistry(registry_path) as registry:
        assert registry.list_papers() == []


def test_sync_yes_creates_missing_registry_from_valid_canonical(tmp_path):
    paper_id = "doi:10.1234/new-registry"
    paths = PaperPaths(storage_id="p_newreg00001", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text(
        """---
title: New Registry Paper
authors: [Ada Lovelace]
year: 2026
doi: 10.1234/new-registry
---
# Body
""",
        encoding="utf-8",
    )
    save_manifest(create_manifest(paper_id, paths.storage_id), paths.manifest_json)

    registry_path = tmp_path / "registry" / "papers.db"
    assert not registry_path.exists()

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "sync", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert registry_path.exists()
    with PaperRegistry(registry_path) as registry:
        rebuilt = registry.get_paper(paper_id)
    assert rebuilt is not None
    assert rebuilt["storage_id"] == paths.storage_id
