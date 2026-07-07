"""集成测试: ingest 命令中的自动实体提取"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from paperbase.cli.main import main


@pytest.fixture
def runner():
    """Click CLI runner"""
    return CliRunner()


@pytest.fixture
def sample_pdf(tmp_path):
    """创建一个示例 PDF 文件"""
    pdf_path = tmp_path / "test_paper.pdf"
    # 创建一个空文件作为 PDF（实际测试会 mock PDF 处理）
    pdf_path.write_bytes(b"%PDF-1.4\nfake pdf content")
    return pdf_path


def test_ingest_without_llm_skips_auto_extract(runner, sample_pdf, tmp_path):
    """测试没有 LLM 配置时跳过自动提取"""
    with patch("paperbase.adapters.pdf_extractor.pymupdf.open") as mock_pymupdf, \
         patch("paperbase.adapters.pdf_converter.MarkItDown") as mock_markitdown, \
         patch("paperbase.core.entity_manager.EntityManager") as mock_em_class:

        # Mock PyMuPDF
        mock_doc = MagicMock()
        mock_doc.metadata = {
            "title": "Test Paper",
            "author": "Alice",
            "creationDate": "D:20240101"
        }
        mock_pymupdf.return_value = mock_doc

        # Mock MarkItDown
        mock_md_instance = MagicMock()
        mock_md_instance.convert.return_value.text_content = "# Test Paper\n\nContent here."
        mock_markitdown.return_value = mock_md_instance

        # Mock EntityManager - LLM 未启用
        mock_em = MagicMock()
        mock_em.llm_client.enabled = False
        mock_em_class.return_value = mock_em

        # 执行 ingest
        result = runner.invoke(main, [
            "--base-dir", str(tmp_path),
            "ingest",
            str(sample_pdf),
            "--no-graph"
        ])

        # 验证
        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "内部 LLM 未配置" in result.output or "跳过自动提取" in result.output
        assert "配置内部 LLM" in result.output

        # 确保没有调用 auto_extract_entities
        mock_em.auto_extract_entities.assert_not_called()


def test_ingest_with_llm_extracts_entities(runner, sample_pdf, tmp_path):
    """测试 LLM 启用时自动提取实体"""
    with patch("paperbase.adapters.pdf_extractor.pymupdf.open") as mock_pymupdf, \
         patch("paperbase.adapters.pdf_converter.MarkItDown") as mock_markitdown, \
         patch("paperbase.core.entity_manager.EntityManager") as mock_em_class:

        # Mock PyMuPDF
        mock_doc = MagicMock()
        mock_doc.metadata = {
            "title": "Test Paper",
            "author": "Alice",
            "creationDate": "D:20240101"
        }
        mock_pymupdf.return_value = mock_doc

        # Mock MarkItDown
        mock_md_instance = MagicMock()
        mock_md_instance.convert.return_value.text_content = "# Test Paper\n\nContent here."
        mock_markitdown.return_value = mock_md_instance

        # Mock EntityManager - LLM 已启用
        mock_em = MagicMock()
        mock_em.llm_client.enabled = True
        mock_em.auto_extract_entities.return_value = {
            "methods": [{"name": "SLAM", "description": "Simultaneous Localization"}],
            "datasets": [{"name": "KITTI"}]
        }
        mock_em_class.return_value = mock_em

        # 执行 ingest
        result = runner.invoke(main, [
            "--base-dir", str(tmp_path),
            "ingest",
            str(sample_pdf),
            "--no-graph"
        ])

        # 验证
        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "内部 LLM 已启用" in result.output or "正在提取实体" in result.output
        assert "实体已自动提取" in result.output
        assert "SLAM" in result.output
        assert "KITTI" in result.output

        # 确保调用了 auto_extract_entities
        mock_em.auto_extract_entities.assert_called_once()


def test_ingest_auto_extract_failure_does_not_block(runner, sample_pdf, tmp_path):
    """测试自动提取失败不会阻塞摄入流程"""
    with patch("paperbase.adapters.pdf_extractor.pymupdf.open") as mock_pymupdf, \
         patch("paperbase.adapters.pdf_converter.MarkItDown") as mock_markitdown, \
         patch("paperbase.core.entity_manager.EntityManager") as mock_em_class:

        # Mock PyMuPDF
        mock_doc = MagicMock()
        mock_doc.metadata = {
            "title": "Test Paper",
            "author": "Alice",
            "creationDate": "D:20240101"
        }
        mock_pymupdf.return_value = mock_doc

        # Mock MarkItDown
        mock_md_instance = MagicMock()
        mock_md_instance.convert.return_value.text_content = "# Test Paper\n\nContent here."
        mock_markitdown.return_value = mock_md_instance

        # Mock EntityManager - LLM 已启用但提取失败
        mock_em = MagicMock()
        mock_em.llm_client.enabled = True
        mock_em.auto_extract_entities.side_effect = Exception("LLM API timeout")
        mock_em_class.return_value = mock_em

        # 执行 ingest
        result = runner.invoke(main, [
            "--base-dir", str(tmp_path),
            "ingest",
            str(sample_pdf),
            "--no-graph"
        ])

        # 验证：摄入成功，但显示警告
        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "实体提取异常" in result.output or "实体提取失败" in result.output
        assert "论文已摄入" in result.output or "摄入完成" in result.output

        # 验证论文确实被摄入
        from paperbase.core.registry import PaperRegistry
        registry = PaperRegistry(tmp_path / "registry" / "papers.db")
        papers = registry.list_papers()
        assert len(papers) == 1
        registry.close()


def test_ingest_auto_extract_returns_empty(runner, sample_pdf, tmp_path):
    """测试自动提取返回空结果"""
    with patch("paperbase.adapters.pdf_extractor.pymupdf.open") as mock_pymupdf, \
         patch("paperbase.adapters.pdf_converter.MarkItDown") as mock_markitdown, \
         patch("paperbase.core.entity_manager.EntityManager") as mock_em_class:

        # Mock PyMuPDF
        mock_doc = MagicMock()
        mock_doc.metadata = {
            "title": "Test Paper",
            "author": "Alice",
            "creationDate": "D:20240101"
        }
        mock_pymupdf.return_value = mock_doc

        # Mock MarkItDown
        mock_md_instance = MagicMock()
        mock_md_instance.convert.return_value.text_content = "# Test Paper\n\nContent here."
        mock_markitdown.return_value = mock_md_instance

        # Mock EntityManager - LLM 已启用但返回空
        mock_em = MagicMock()
        mock_em.llm_client.enabled = True
        mock_em.auto_extract_entities.return_value = {}
        mock_em_class.return_value = mock_em

        # 执行 ingest
        result = runner.invoke(main, [
            "--base-dir", str(tmp_path),
            "ingest",
            str(sample_pdf),
            "--no-graph"
        ])

        # 验证：摄入成功，显示提取失败或返回空
        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"
        assert "实体提取失败或返回空" in result.output or "实体提取" in result.output
        assert "摄入完成" in result.output
