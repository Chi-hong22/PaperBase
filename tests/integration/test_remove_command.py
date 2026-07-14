from click.testing import CliRunner

from paperbase.cli.main import main
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def test_remove_deletes_canonical_files_and_registry_record(tmp_path):
    paper_id = "doi:10.1234/remove"
    paths = PaperPaths(storage_id="p_remove000001", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=paper_id,
            storage_id=paths.storage_id,
            state=PaperState.NORMALIZED,
            title="Paper to remove",
        )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "remove", paper_id, "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    assert not paths.paper_md.exists()
    with PaperRegistry(registry_path) as registry:
        assert registry.get_paper(paper_id) is None


def test_remove_deletes_canonical_when_resource_directory_is_missing(tmp_path):
    paper_id = "doi:10.1234/remove-flat-only"
    paths = PaperPaths(storage_id="p_remove000002", base_dir=tmp_path)
    paths.paper_md.parent.mkdir(parents=True)
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")

    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir()
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=paper_id,
            storage_id=paths.storage_id,
            state=PaperState.NORMALIZED,
            title="Flat-only paper",
        )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "remove", paper_id, "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert "删除完成" in result.output
    assert "仅 Registry" not in result.output
    assert not paths.paper_md.exists()
    with PaperRegistry(registry_path) as registry:
        assert registry.get_paper(paper_id) is None
