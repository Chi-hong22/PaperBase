"""引用提取器

从 Markdown 文本中提取结构化引用信息
"""

import json
import re
from pathlib import Path
from typing import List, Dict


def extract_references(markdown: str, paper_id: str) -> List[Dict[str, any]]:
    """
    从 Markdown 文本中提取引用信息

    策略：
    1. 定位 References/Bibliography 部分
    2. 解析每个引用条目（通常以 [数字] 开头）
    3. 提取：title, authors, year, doi

    Args:
        markdown: Markdown 文本内容
        paper_id: 论文 ID

    Returns:
        List[Dict]: 引用列表，每个引用包含：
            - id: 引用唯一标识 (paper_id:ref:position)
            - paper_id: 所属论文 ID
            - title: 论文标题
            - authors: 作者字符串
            - year: 发表年份
            - doi: DOI（可能为 None）
            - position: 引用位置索引
    """
    # 处理空内容
    if not markdown or not markdown.strip():
        return []

    # 定位 References 或 Bibliography 部分
    references_text = _extract_references_section(markdown)
    if not references_text:
        return []

    # 解析引用条目
    references = _parse_references(references_text, paper_id)

    return references


def _extract_references_section(markdown: str) -> str:
    """
    提取 References/Bibliography 部分

    Args:
        markdown: 完整 Markdown 文本

    Returns:
        str: References 部分的文本，如果没有则返回空字符串
    """
    # 匹配 ## References, # References, ## Bibliography, # Bibliography
    pattern = r'^#+ (References?|Bibliography)\s*$'

    lines = markdown.split('\n')
    start_idx = None

    # 查找 References 标题
    for i, line in enumerate(lines):
        if re.match(pattern, line, re.IGNORECASE):
            start_idx = i + 1
            break

    if start_idx is None:
        return ""

    # 提取从 References 标题到文档末尾或下一个同级/上级标题的内容
    references_lines = []
    start_heading_level = len(re.match(r'^(#+)', lines[start_idx - 1]).group(1))

    for i in range(start_idx, len(lines)):
        line = lines[i]

        # 如果遇到同级或更高级标题，停止
        if line.strip().startswith('#'):
            heading_match = re.match(r'^(#+)', line)
            if heading_match:
                current_level = len(heading_match.group(1))
                if current_level <= start_heading_level:
                    break

        references_lines.append(line)

    references_text = '\n'.join(references_lines).strip()
    return references_text


def _parse_references(references_text: str, paper_id: str) -> List[Dict[str, any]]:
    """
    解析引用条目

    Args:
        references_text: References 部分的文本
        paper_id: 论文 ID

    Returns:
        List[Dict]: 解析后的引用列表
    """
    if not references_text:
        return []

    # 按引用条目分割（通常以 [数字] 开头）
    # 匹配 [1], [2], 等等
    pattern = r'^\[\d+\]'

    lines = references_text.split('\n')
    references = []
    current_ref = []
    position = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 如果是新引用的开始
        if re.match(pattern, line):
            # 处理前一个引用
            if current_ref:
                ref_text = ' '.join(current_ref)
                parsed_ref = _parse_single_reference(ref_text, paper_id, position)
                if parsed_ref:
                    references.append(parsed_ref)
                    position += 1

            # 开始新引用
            current_ref = [line]
        else:
            # 继续当前引用（多行引用）
            if current_ref:
                current_ref.append(line)

    # 处理最后一个引用
    if current_ref:
        ref_text = ' '.join(current_ref)
        parsed_ref = _parse_single_reference(ref_text, paper_id, position)
        if parsed_ref:
            references.append(parsed_ref)

    return references


def _parse_single_reference(ref_text: str, paper_id: str, position: int) -> Dict[str, any] | None:
    """
    解析单个引用条目

    Args:
        ref_text: 单个引用的文本
        paper_id: 论文 ID
        position: 引用位置

    Returns:
        Dict: 解析后的引用信息，如果解析失败返回 None
    """
    # 移除开头的 [数字]
    ref_text = re.sub(r'^\[\d+\]\s*', '', ref_text)

    if not ref_text.strip():
        return None

    # 提取年份（通常是括号中的四位数字，如 (2020) 或 2020）
    year = None
    year_match = re.search(r'\((\d{4})\)|(\d{4})', ref_text)
    if year_match:
        year = int(year_match.group(1) or year_match.group(2))

    # 提取 DOI
    doi = None
    doi_match = re.search(r'DOI:\s*([^\s,]+)', ref_text, re.IGNORECASE)
    if doi_match:
        doi = doi_match.group(1).rstrip('.')

    # 提取作者（通常在年份之前）
    authors = ""
    if year_match:
        # 作者通常在年份之前
        authors_text = ref_text[:year_match.start()].strip()
        # 清理常见分隔符
        authors_text = authors_text.rstrip('.,')
        authors = authors_text
    else:
        # 如果没有年份，尝试提取第一个句子作为作者
        first_sentence = ref_text.split('.')[0] if '.' in ref_text else ref_text[:50]
        authors = first_sentence.strip()

    # 提取标题（通常在年份之后、期刊名之前，可能有引号或斜体）
    title = ""
    if year_match:
        # 标题通常在年份之后
        after_year = ref_text[year_match.end():].strip()

        # 移除开头的标点
        after_year = after_year.lstrip('.,:;')

        # 尝试提取引号中的内容
        quoted_match = re.search(r'["""]([^"""]+)["""]', after_year)
        if quoted_match:
            title = quoted_match.group(1)
        else:
            # 尝试提取到第一个句号或期刊标记
            # 期刊通常是斜体 *Journal* 或粗体 **Journal**
            title_match = re.match(r'([^.*]+?)[\.*]', after_year)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # 取前面的部分作为标题
                title = after_year.split('.')[0] if '.' in after_year else after_year[:100]
    else:
        # 如果没有年份，尝试从整个文本中提取标题
        title = ref_text[:100]

    title = title.strip().rstrip('.,')

    # 构建引用对象
    reference = {
        "id": f"{paper_id}:ref:{position}",
        "paper_id": paper_id,
        "title": title if title else ref_text[:50],  # 如果没有标题，使用前50个字符
        "authors": authors if authors else "Unknown",
        "year": year,
        "doi": doi,
        "position": position,
    }

    return reference


def write_references_jsonl(references: List[Dict[str, any]], output_path: Path) -> None:
    """
    将引用写入 JSONL 文件

    Args:
        references: 引用列表
        output_path: 输出文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for reference in references:
            json_line = json.dumps(reference, ensure_ascii=False)
            f.write(json_line + "\n")
