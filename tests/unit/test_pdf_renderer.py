import hashlib
import json
import subprocess
from pathlib import Path

import pymupdf
import pytest

from paperbase.adapters import pdf_renderer
from paperbase.adapters.pdf_renderer import renderPdfPages


def _create_pdf(pdf_path: Path, page_count: int = 2, text_prefix: str = "page") -> None:
    document = pymupdf.open()
    try:
        for page_number in range(page_count):
            page = document.new_page()
            page.insert_text((72, 72), f"{text_prefix} {page_number + 1}")
        document.save(pdf_path)
    finally:
        document.close()


def _make_junction_or_skip(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("当前 Windows 环境不允许创建 junction")


def _remove_junction(link_path: Path) -> None:
    subprocess.run(
        ["cmd.exe", "/d", "/c", "rmdir", str(link_path)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_render_pdf_pages_creates_named_pngs_within_rendered_root(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "run" / "rendered"
    _create_pdf(source_pdf, page_count=2)

    page_paths = renderPdfPages(source_pdf, rendered_dir)

    assert page_paths == {
        1: rendered_dir.resolve() / "page-0001.png",
        2: rendered_dir.resolve() / "page-0002.png",
    }
    for page_path in page_paths.values():
        assert page_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert page_path.resolve().is_relative_to(rendered_dir.resolve())

    provenance = json.loads((rendered_dir / ".paperbase-render.json").read_text(encoding="utf-8"))
    assert provenance == {
        "page_count": 2,
        "render_zoom": 2.0,
        "source_pdf_sha256": hashlib.sha256(source_pdf.read_bytes()).hexdigest(),
    }


def test_render_pdf_pages_reuses_complete_existing_page_set(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=2)

    first_paths = renderPdfPages(source_pdf, rendered_dir)
    first_mtime = first_paths[1].stat().st_mtime_ns
    second_paths = renderPdfPages(source_pdf, rendered_dir)

    assert second_paths == first_paths
    assert second_paths[1].stat().st_mtime_ns == first_mtime


def test_render_pdf_pages_rejects_existing_conflict(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=2)
    rendered_dir.mkdir()
    (rendered_dir / "unexpected.txt").write_text("existing output", encoding="utf-8")

    with pytest.raises(FileExistsError, match="冲突文件"):
        renderPdfPages(source_pdf, rendered_dir)


def test_render_pdf_pages_rejects_invalid_complete_page_set(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=1)
    rendered_dir.mkdir()
    (rendered_dir / "page-0001.png").write_bytes(b"not a PNG")

    with pytest.raises(FileExistsError, match="无效页图像"):
        renderPdfPages(source_pdf, rendered_dir)


def test_render_pdf_pages_resumes_after_page_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=2)
    original_writer = pdf_renderer._writePixmapAtomically

    def fail_second_page(pixmap: pymupdf.Pixmap, page_path: Path, rendered_root: Path) -> None:
        if page_path.name == "page-0002.png":
            raise RuntimeError("second page failed")
        original_writer(pixmap, page_path, rendered_root)

    monkeypatch.setattr(pdf_renderer, "_writePixmapAtomically", fail_second_page)
    with pytest.raises(RuntimeError, match="second page failed"):
        renderPdfPages(source_pdf, rendered_dir)

    assert (rendered_dir / "page-0001.png").exists()
    temporary_page = rendered_dir / ".page-0002.png.tmp"
    temporary_page.write_bytes(b"interrupted write")
    monkeypatch.setattr(pdf_renderer, "_writePixmapAtomically", original_writer)

    page_paths = renderPdfPages(source_pdf, rendered_dir)

    assert all(page_path.exists() for page_path in page_paths.values())
    assert not temporary_page.exists()


def test_render_pdf_pages_rejects_different_source_with_same_page_count(tmp_path: Path) -> None:
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(first_source, page_count=1, text_prefix="first")
    _create_pdf(second_source, page_count=1, text_prefix="second")
    renderPdfPages(first_source, rendered_dir)

    with pytest.raises(ValueError, match="provenance 不匹配"):
        renderPdfPages(second_source, rendered_dir)


def test_render_pdf_pages_rejects_render_parameter_provenance_mismatch(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_dir = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=1)
    renderPdfPages(source_pdf, rendered_dir)
    provenance_path = rendered_dir / ".paperbase-render.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["render_zoom"] = 1.0
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance 不匹配"):
        renderPdfPages(source_pdf, rendered_dir)


def test_render_pdf_pages_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="PDF 文件不存在"):
        renderPdfPages(tmp_path / "missing.pdf", tmp_path / "rendered")


def test_render_pdf_pages_rejects_non_file_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    with pytest.raises(ValueError, match="不是文件"):
        renderPdfPages(source_dir, tmp_path / "rendered")


def test_render_pdf_pages_rejects_damaged_pdf(tmp_path: Path) -> None:
    source_pdf = tmp_path / "damaged.pdf"
    source_pdf.write_bytes(b"not a PDF")

    with pytest.raises(ValueError, match="无法打开 PDF"):
        renderPdfPages(source_pdf, tmp_path / "rendered")


def test_render_pdf_pages_rejects_zero_page_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_pdf = tmp_path / "source.pdf"
    _create_pdf(source_pdf, page_count=1)

    class EmptyDocument:
        def __len__(self) -> int:
            return 0

        def close(self) -> None:
            pass

    monkeypatch.setattr(pdf_renderer.pymupdf, "open", lambda _path: EmptyDocument())

    with pytest.raises(ValueError, match="不包含可渲染页面"):
        renderPdfPages(source_pdf, tmp_path / "rendered")


def test_render_pdf_pages_rejects_non_directory_output_path(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    rendered_file = tmp_path / "rendered"
    _create_pdf(source_pdf, page_count=1)
    rendered_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="不是目录"):
        renderPdfPages(source_pdf, rendered_file)


def test_render_pdf_pages_rejects_junctioned_output_without_writing_target(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    _create_pdf(source_pdf, page_count=1)
    rendered_dir = tmp_path / "rendered"
    external_target = tmp_path / "external-rendered"
    _make_junction_or_skip(rendered_dir, external_target)
    try:
        with pytest.raises(ValueError, match="reparse"):
            renderPdfPages(source_pdf, rendered_dir)

        assert list(external_target.iterdir()) == []
    finally:
        _remove_junction(rendered_dir)


def test_render_pdf_pages_rejects_source_parent_junction(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    external_source = tmp_path / "external-source"
    _make_junction_or_skip(source_root, external_source)
    _create_pdf(external_source / "source.pdf", page_count=1)
    try:
        with pytest.raises(ValueError, match="reparse"):
            renderPdfPages(source_root / "source.pdf", tmp_path / "rendered")
    finally:
        _remove_junction(source_root)


def test_render_pdf_pages_rejects_junctioned_output_parent_without_writing_target(
    tmp_path: Path,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    _create_pdf(source_pdf, page_count=1)
    output_parent = tmp_path / "run"
    external_target = tmp_path / "external-run"
    _make_junction_or_skip(output_parent, external_target)
    try:
        with pytest.raises(ValueError, match="reparse"):
            renderPdfPages(source_pdf, output_parent / "rendered")

        assert list(external_target.iterdir()) == []
    finally:
        _remove_junction(output_parent)
