"""测试 remove 命令的视觉审计缓存 stash 行为"""

import pytest
from click.testing import CliRunner

from paperbase.cli.main import main
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState

AUDIT_ID = "abcdef123456-abcdef123456-1"


def _register_paper(tmp_path, paper_id: str, storage_id: str) -> None:
    registry_path = tmp_path / "registry" / "papers.db"
    registry_path.parent.mkdir(exist_ok=True)
    with PaperRegistry(registry_path) as registry:
        registry.register_paper(
            paper_id=paper_id,
            storage_id=storage_id,
            state=PaperState.NORMALIZED,
            title="Paper to remove",
        )


def _make_audit_dir(paths: PaperPaths) -> None:
    audit_dir = paths.paper_dir / ".visual-auto-audit" / AUDIT_ID
    audit_dir.mkdir(parents=True)
    (audit_dir / "result.json").write_text('{"state": "completed"}', encoding="utf-8")


def _invoke_remove(tmp_path, paper_id: str):
    # COLUMNS 调大避免 rich 换行截断输出中较长的 stash 路径
    return CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "remove", paper_id, "--yes"],
        env={"COLUMNS": "400"},
    )


def test_remove_stashes_visual_auto_audit_directory(tmp_path):
    paper_id = "doi:10.1234/remove-stash"
    paths = PaperPaths(storage_id="p_stash000001", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")
    _make_audit_dir(paths)
    _register_paper(tmp_path, paper_id, paths.storage_id)

    stash_target = tmp_path / "library" / "audits-stash" / paths.storage_id

    result = _invoke_remove(tmp_path, paper_id)

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    stashed_result = stash_target / AUDIT_ID / "result.json"
    assert stashed_result.read_text(encoding="utf-8") == '{"state": "completed"}'
    assert str(stash_target) in result.output
    assert "重摄入同一 PDF 前" in result.output
    assert f"library/papers/{paths.storage_id}/.visual-auto-audit" in result.output
    with PaperRegistry(tmp_path / "registry" / "papers.db") as registry:
        assert registry.get_paper(paper_id) is None


def test_remove_stash_appends_suffix_when_target_exists(tmp_path):
    paper_id = "doi:10.1234/remove-stash-suffix"
    paths = PaperPaths(storage_id="p_stash000002", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")
    _make_audit_dir(paths)
    _register_paper(tmp_path, paper_id, paths.storage_id)

    stash_root = tmp_path / "library" / "audits-stash"
    existing_stash = stash_root / paths.storage_id
    existing_stash.mkdir(parents=True)
    (existing_stash / "keep.txt").write_text("previous stash", encoding="utf-8")

    result = _invoke_remove(tmp_path, paper_id)

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    assert (existing_stash / "keep.txt").read_text(encoding="utf-8") == "previous stash"
    new_stash = stash_root / f"{paths.storage_id}-2"
    assert (new_stash / AUDIT_ID / "result.json").exists()
    assert str(new_stash) in result.output


def test_remove_without_visual_auto_audit_keeps_previous_behavior(tmp_path):
    paper_id = "doi:10.1234/remove-stash-none"
    paths = PaperPaths(storage_id="p_stash000003", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")
    _register_paper(tmp_path, paper_id, paths.storage_id)

    result = _invoke_remove(tmp_path, paper_id)

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    assert not (tmp_path / "library" / "audits-stash").exists()
    assert "视觉审计" not in result.output
    with PaperRegistry(tmp_path / "registry" / "papers.db") as registry:
        assert registry.get_paper(paper_id) is None


def test_remove_skips_stash_for_symlinked_audit_directory(tmp_path):
    paper_id = "doi:10.1234/remove-stash-link"
    paths = PaperPaths(storage_id="p_stash000004", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")

    real_audit = tmp_path / "audit-real"
    real_audit.mkdir()
    (real_audit / "result.json").write_text('{"state": "completed"}', encoding="utf-8")
    audit_dir = paths.paper_dir / ".visual-auto-audit"
    try:
        audit_dir.symlink_to(real_audit, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not available on this platform")

    _register_paper(tmp_path, paper_id, paths.storage_id)

    result = _invoke_remove(tmp_path, paper_id)

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    assert not (tmp_path / "library" / "audits-stash").exists()
    assert "视觉审计缓存已保留" not in result.output
    assert (real_audit / "result.json").exists()


def test_stash_failure_does_not_block_removal(monkeypatch, tmp_path):
    """审计缓存移动失败时仅打印警告，删除流程继续完成。"""
    paper_id = "doi:10.1234/remove-stash-failure"
    paths = PaperPaths(storage_id="p_stash000009", base_dir=tmp_path)
    paths.create_directories()
    paths.paper_md.write_text("# Canonical paper", encoding="utf-8")
    _make_audit_dir(paths)
    _register_paper(tmp_path, paper_id, paths.storage_id)

    def _raise_move(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("paperbase.cli.commands.remove.shutil.move", _raise_move)

    result = _invoke_remove(tmp_path, paper_id)

    assert result.exit_code == 0, result.output
    assert not paths.paper_dir.exists()
    assert "视觉审计缓存暂存失败" in result.output
    with PaperRegistry(tmp_path / "registry" / "papers.db") as registry:
        assert registry.get_paper(paper_id) is None
