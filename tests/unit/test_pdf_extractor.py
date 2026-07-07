# tests/unit/test_pdf_extractor.py
import pytest
from pathlib import Path
from paperbase.adapters.pdf_extractor import extract_pdf_metadata, extract_pdf_text


def test_extract_pdf_metadata_file_not_found():
    """文件不存在应该抛出 FileNotFoundError"""
    with pytest.raises(FileNotFoundError):
        extract_pdf_metadata(Path("/nonexistent/file.pdf"))


def test_extract_pdf_text_file_not_found():
    """文件不存在应该抛出 FileNotFoundError"""
    with pytest.raises(FileNotFoundError):
        extract_pdf_text(Path("/nonexistent/file.pdf"))
