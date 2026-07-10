"""PDF 结构化文本提取器

从 PDF 第一页提取摘要、关键词、DOI 等结构化数据
"""

import re
from pathlib import Path
from typing import Optional

import pymupdf


class PDFTextExtractor:
    """PDF 文本结构化提取器"""

    # DOI 正则：10.xxxx/xxx，容错空格和换行
    # 扩展支持更多 DOI 格式和常见前缀
    DOI_PATTERNS = [
        re.compile(r'(?:doi[:\s]*)?10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', re.IGNORECASE),
        re.compile(r'https?://doi\.org/10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', re.IGNORECASE),
        re.compile(r'https?://dx\.doi\.org/10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', re.IGNORECASE),
    ]

    # 章节标题模式（大小写不敏感，支持更多变体）
    ABSTRACT_STARTS = [
        re.compile(r'\bABSTRACT\b', re.IGNORECASE),
        re.compile(r'\bSUMMARY\b', re.IGNORECASE),
        re.compile(r'\b摘要\b'),  # 中文论文
    ]
    ABSTRACT_ENDS = [
        re.compile(r'\b(INTRODUCTION|KEYWORDS?|INDEX\s+TERMS|1\.|I\.|II\.)\b', re.IGNORECASE),
        re.compile(r'\n\s*\n\s*[A-Z][A-Z\s]{10,}'),  # 全大写标题
    ]
    KEYWORDS_STARTS = [
        re.compile(r'\bKEYWORDS?\b', re.IGNORECASE),
        re.compile(r'\bINDEX\s+TERMS\b', re.IGNORECASE),
        re.compile(r'\bKEY\s+WORDS\b', re.IGNORECASE),
        re.compile(r'\b关键词\b'),  # 中文
    ]
    KEYWORDS_ENDS = [
        re.compile(r'\b(INTRODUCTION|1\.|I\.)\b', re.IGNORECASE),
        re.compile(r'\n\s*\n\s*[A-Z]'),  # 新段落开始
    ]

    def __init__(self, pdf_path: Path):
        """
        初始化提取器

        Args:
            pdf_path: PDF 文件路径

        Raises:
            FileNotFoundError: PDF 文件不存在
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        self.pdf_path = pdf_path
        self._first_page_text: Optional[str] = None

    def _get_first_page_text(self) -> str:
        """提取第一页文本（懒加载）"""
        if self._first_page_text is None:
            try:
                with pymupdf.open(self.pdf_path) as doc:
                    if len(doc) > 0:
                        self._first_page_text = doc[0].get_text()
                    else:
                        self._first_page_text = ""
            except Exception:
                self._first_page_text = ""
        return self._first_page_text

    def extract_doi(self) -> Optional[str]:
        """
        提取 DOI

        Returns:
            str | None: DOI 字符串，未找到返回 None
        """
        text = self._get_first_page_text()
        if not text:
            return None

        # 移除换行和多余空格
        cleaned_text = re.sub(r'\s+', ' ', text)

        # 尝试多种 DOI 模式
        for pattern in self.DOI_PATTERNS:
            match = pattern.search(cleaned_text)
            if match:
                doi = match.group(0)
                # 提取纯 DOI（移除前缀和协议）
                doi = re.sub(r'^(doi[:\s]*|https?://(?:dx\.)?doi\.org/)', '', doi, flags=re.IGNORECASE)
                # 清理尾部可能的标点符号
                doi = doi.rstrip('.,;')
                return doi

        return None

    def extract_abstract(self) -> Optional[str]:
        """
        提取摘要

        Returns:
            str | None: 摘要文本，未找到返回 None
        """
        text = self._get_first_page_text()
        if not text:
            return None

        # 尝试多种 Abstract 起始模式
        start_match = None
        start_pos = 0
        for pattern in self.ABSTRACT_STARTS:
            match = pattern.search(text)
            if match:
                start_match = match
                start_pos = match.end()
                break

        if not start_match:
            return None

        # 尝试多种结束模式
        end_pos = None
        for pattern in self.ABSTRACT_ENDS:
            match = pattern.search(text, start_pos)
            if match:
                end_pos = match.start()
                break

        # 如果未找到结束标记，取后续 1500 字符（提高容错）
        if end_pos is None:
            end_pos = min(start_pos + 1500, len(text))

        abstract_text = text[start_pos:end_pos].strip()

        # 清理：移除多余空白、连字符换行
        abstract_text = re.sub(r'-\s+', '', abstract_text)  # 处理连字符换行
        abstract_text = re.sub(r'\s+', ' ', abstract_text)  # 规范化空白

        # 过滤太短或太长的结果（可能是误匹配）
        if len(abstract_text) < 50 or len(abstract_text) > 3000:
            return None

        return abstract_text

    def extract_keywords(self) -> Optional[list[str]]:
        """
        提取关键词

        Returns:
            list[str] | None: 关键词列表，未找到返回 None
        """
        text = self._get_first_page_text()
        if not text:
            return None

        # 尝试多种 Keywords 起始模式
        start_match = None
        start_pos = 0
        for pattern in self.KEYWORDS_STARTS:
            match = pattern.search(text)
            if match:
                start_match = match
                start_pos = match.end()
                break

        if not start_match:
            return None

        # 尝试多种结束模式
        end_pos = None
        for pattern in self.KEYWORDS_ENDS:
            match = pattern.search(text, start_pos)
            if match:
                end_pos = match.start()
                break

        # 如果未找到结束标记，取后续 500 字符
        if end_pos is None:
            end_pos = min(start_pos + 500, len(text))

        keywords_text = text[start_pos:end_pos].strip()

        # 清理：移除换行、多余空格、冒号
        keywords_text = re.sub(r'\s+', ' ', keywords_text)
        keywords_text = keywords_text.lstrip(':—-')  # 移除开头的冒号和破折号

        # 分割关键词（支持多种分隔符，优先级从高到低）
        keywords = []
        for sep in [';', ',', '·', '•', '、', '|']:
            if sep in keywords_text:
                keywords = [kw.strip() for kw in keywords_text.split(sep) if kw.strip()]
                break

        # 如果没有明确分隔符，尝试按多个空格或换行分割
        if not keywords:
            keywords = [kw.strip() for kw in re.split(r'[\s]{2,}|\n', keywords_text) if kw.strip()]

        # 过滤不合理的关键词
        filtered = []
        for kw in keywords:
            # 跳过太短（< 2 字符）或太长（> 100 字符）的关键词
            if 2 <= len(kw) <= 100:
                # 跳过纯数字或明显不是关键词的内容
                if not kw.isdigit() and not re.match(r'^[^a-zA-Z一-鿿]+$', kw):
                    filtered.append(kw)

        return filtered if filtered else None

    def extract_all(self) -> dict:
        """
        提取所有结构化数据

        Returns:
            dict: {
                "doi": str | None,
                "abstract": str | None,
                "keywords": list[str] | None
            }
        """
        return {
            "doi": self.extract_doi(),
            "abstract": self.extract_abstract(),
            "keywords": self.extract_keywords(),
        }


def extract_structured_data(pdf_path: Path) -> dict:
    """
    便捷函数：提取 PDF 结构化数据

    Args:
        pdf_path: PDF 文件路径

    Returns:
        dict: {
            "doi": str | None,
            "abstract": str | None,
            "keywords": list[str] | None
        }

    Note:
        提取失败不抛出异常，返回空值
    """
    try:
        extractor = PDFTextExtractor(pdf_path)
        return extractor.extract_all()
    except Exception:
        # 优雅降级
        return {
            "doi": None,
            "abstract": None,
            "keywords": None,
        }
