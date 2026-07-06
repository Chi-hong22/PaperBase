"""PDF 到 Markdown 转换器"""

from pathlib import Path
from markitdown import MarkItDown


def convert_pdf_to_markdown(pdf_path: Path) -> str:
    """
    将 PDF 转换为 Markdown

    使用 markitdown 进行转换

    Args:
        pdf_path: PDF 文件路径

    Returns:
        str: Markdown 文本
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    md = MarkItDown()
    result = md.convert(str(pdf_path))

    return result.text_content
