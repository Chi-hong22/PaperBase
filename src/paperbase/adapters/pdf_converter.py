"""PDF 到 Markdown 转换器"""

from pathlib import Path
from markitdown import MarkItDown


def convert_pdf_to_markdown(pdf_path: Path, timeout: int = 300) -> str:
    """
    将 PDF 转换为 Markdown

    使用 markitdown 进行转换

    Args:
        pdf_path: PDF 文件路径
        timeout: 超时时间（秒），默认 300 秒

    Returns:
        str: Markdown 文本

    Raises:
        FileNotFoundError: PDF 文件不存在
        ValueError: 转换结果为空
        RuntimeError: 转换失败
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    # 验证文件大小（限制 100MB）
    file_size = pdf_path.stat().st_size
    max_size = 100 * 1024 * 1024
    if file_size > max_size:
        raise ValueError(f"PDF 文件过大: {file_size / 1024 / 1024:.1f}MB (最大 {max_size / 1024 / 1024}MB)")

    try:
        md = MarkItDown()
        result = md.convert(str(pdf_path))

        if not result or not result.text_content:
            raise ValueError("PDF 转换结果为空")

        return result.text_content
    except Exception as e:
        raise RuntimeError(f"PDF 转换失败: {str(e)}") from e
