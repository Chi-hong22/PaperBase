"""Markdown 文本分块器

将 Markdown 文本分割为可检索的 chunk
"""

import json
from pathlib import Path
from typing import List, Dict


# 每个 chunk 的最大字符数（约 512 token）
MAX_CHUNK_CHARS = 2048


def generate_chunks(markdown: str, paper_id: str) -> List[Dict[str, any]]:
    """
    将 Markdown 文本分块

    策略：
    1. 按段落分块（\n\n 分割）
    2. 段落过长时按固定字符数切分
    3. 每个 chunk 包含：id, paper_id, content, position

    Args:
        markdown: Markdown 文本内容
        paper_id: 论文 ID

    Returns:
        List[Dict]: chunk 列表，每个 chunk 包含：
            - id: chunk 唯一标识 (paper_id:chunk:position)
            - paper_id: 所属论文 ID
            - content: chunk 文本内容
            - position: chunk 位置索引
    """
    # 处理空内容
    if not markdown or not markdown.strip():
        return []

    # 按段落分割（双换行）
    paragraphs = markdown.split("\n\n")

    chunks = []
    position = 0

    for para in paragraphs:
        # 清理段落，保留格式
        para = para.strip()
        if not para:
            continue

        # 如果段落不超过最大长度，直接作为一个 chunk
        if len(para) <= MAX_CHUNK_CHARS:
            chunk = {
                "id": f"{paper_id}:chunk:{position}",
                "paper_id": paper_id,
                "content": para,
                "position": position,
            }
            chunks.append(chunk)
            position += 1
        else:
            # 段落过长，按固定字符数切分
            sub_chunks = _split_long_paragraph(para, paper_id, position)
            chunks.extend(sub_chunks)
            position += len(sub_chunks)

    return chunks


def _split_long_paragraph(text: str, paper_id: str, start_position: int) -> List[Dict[str, any]]:
    """
    切分超长段落

    Args:
        text: 超长文本
        paper_id: 论文 ID
        start_position: 起始位置索引

    Returns:
        List[Dict]: 切分后的 chunk 列表
    """
    chunks = []
    position = start_position

    # 按固定长度切分
    for i in range(0, len(text), MAX_CHUNK_CHARS):
        sub_text = text[i : i + MAX_CHUNK_CHARS]

        # 尝试在句号、问号、感叹号处断句（如果在最后 100 字符内）
        if i + MAX_CHUNK_CHARS < len(text):
            last_100 = sub_text[-100:]
            for sep in [".", "?", "!", "。", "？", "！"]:
                last_sep_pos = last_100.rfind(sep)
                if last_sep_pos != -1:
                    # 在句号后断开
                    actual_end = len(sub_text) - len(last_100) + last_sep_pos + 1
                    sub_text = sub_text[:actual_end]
                    break

        chunk = {
            "id": f"{paper_id}:chunk:{position}",
            "paper_id": paper_id,
            "content": sub_text.strip(),
            "position": position,
        }
        chunks.append(chunk)
        position += 1

    return chunks


def write_chunks_jsonl(chunks: List[Dict[str, any]], output_path: Path) -> None:
    """
    将 chunks 写入 JSONL 文件

    Args:
        chunks: chunk 列表
        output_path: 输出文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            json_line = json.dumps(chunk, ensure_ascii=False)
            f.write(json_line + "\n")
