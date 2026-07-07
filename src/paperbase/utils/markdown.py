# src/paperbase/utils/markdown.py
"""Markdown 工具函数"""

import yaml
from pathlib import Path
import tempfile
import shutil


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter

    Args:
        content: Markdown 内容

    Returns:
        (metadata_dict, body_content) 元组

    Raises:
        ValueError: frontmatter 格式错误或 YAML 无效
    """
    parts = content.split("---\n")

    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format: expected '---' delimiters")

    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must be a dictionary")

    # Body 是第三部分之后的所有内容
    body = "---\n".join(parts[2:])

    return metadata, body


def generate_canonical_markdown(metadata: dict, body: str) -> str:
    """生成 Canonical Markdown

    Args:
        metadata: 论文元数据字典
        body: Markdown 正文

    Returns:
        完整的 Canonical Markdown 内容
    """
    frontmatter_yaml = yaml.dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,  # 保持原始顺序
        default_flow_style=False
    )

    return f"---\n{frontmatter_yaml}---\n\n{body}"


def update_frontmatter_file(file_path: Path, updates: dict) -> None:
    """原子更新 Markdown 文件的 frontmatter

    使用临时文件 + rename 保证原子性

    Args:
        file_path: Markdown 文件路径
        updates: 要更新的字段字典

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: frontmatter 格式错误
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # 读取原内容
    content = file_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)

    # 更新 metadata
    metadata.update(updates)

    # 生成新内容
    new_content = generate_canonical_markdown(metadata, body)

    # 原子写入（临时文件 + rename）
    temp_file = file_path.with_suffix('.tmp')
    try:
        temp_file.write_text(new_content, encoding="utf-8")
        temp_file.replace(file_path)  # 原子操作
    finally:
        if temp_file.exists():
            temp_file.unlink()
