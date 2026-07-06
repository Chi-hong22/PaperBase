"""PDF 元数据提取器

使用 PyMuPDF 提取 PDF 元数据和文本
"""

from pathlib import Path
import pymupdf


def extract_pdf_metadata(pdf_path: Path) -> dict:
    """
    提取 PDF 元数据

    Returns:
        dict: {
            "title": str | None,
            "authors": list[str],
            "year": int | None,
            "doi": str | None,
            "subject": str | None,
            "keywords": str | None
        }
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    metadata = doc.metadata or {}

    # 提取作者列表
    authors = []
    if metadata.get("author"):
        # 处理多种作者分隔符
        author_str = metadata["author"]
        for sep in [";", ",", " and ", "，"]:
            if sep in author_str:
                authors = [a.strip() for a in author_str.split(sep) if a.strip()]
                break
        if not authors:
            authors = [author_str.strip()]

    # 提取年份
    year = None
    if metadata.get("creationDate"):
        # PyMuPDF 日期格式：D:YYYYMMDD...
        date_str = metadata["creationDate"]
        if date_str.startswith("D:") and len(date_str) >= 10:
            try:
                year = int(date_str[2:6])
            except ValueError:
                pass

    # 提取 DOI（从 subject 或 keywords 中）
    doi = None
    for field in ["subject", "keywords"]:
        if field in metadata and metadata[field]:
            text = metadata[field].lower()
            if "doi" in text or "10." in text:
                # 简单的 DOI 提取
                import re
                match = re.search(r'10\.\d{4,}/[^\s]+', text)
                if match:
                    doi = match.group(0)
                    break

    doc.close()

    return {
        "title": metadata.get("title"),
        "authors": authors,
        "year": year,
        "doi": doi,
        "subject": metadata.get("subject"),
        "keywords": metadata.get("keywords"),
    }


def extract_pdf_text(pdf_path: Path, max_pages: int = 10) -> str:
    """
    提取 PDF 文本内容

    Args:
        pdf_path: PDF 文件路径
        max_pages: 最多提取页数（用于摘要提取）

    Returns:
        str: 文本内容
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    text_parts = []

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        text_parts.append(page.get_text())

    doc.close()

    return "\n\n".join(text_parts)
