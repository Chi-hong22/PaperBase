"""Terminology Library for Fuzzy Entity Matching

支持实体名称的模糊匹配，处理变体（如 submap/sub-map/submapping）
"""

from pathlib import Path
import yaml
import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_terminology(config_path: Path | str) -> dict[str, Any]:
    """
    加载术语库配置

    Args:
        config_path: YAML 配置文件路径

    Returns:
        术语库字典，格式：
        {
            "aliases": {
                "methods": {
                    "canonical_term": ["variant1", "variant2"],
                    ...
                },
                ...
            }
        }

        如果文件不存在或加载失败，返回 {"aliases": {}}
    """
    config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"Terminology file not found: {config_path}")
        return {"aliases": {}}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            terminology = yaml.safe_load(f) or {}

        # 验证结构
        if "aliases" not in terminology:
            logger.warning(f"Invalid terminology structure: missing 'aliases' key")
            return {"aliases": {}}

        return terminology

    except Exception as e:
        logger.error(f"Failed to load terminology: {e}")
        return {"aliases": {}}


def fuzzy_match(term: str, category: str, terminology: dict[str, Any]) -> str | None:
    """
    模糊匹配术语，返回规范形式

    Args:
        term: 待匹配的术语
        category: 实体类别（methods/datasets/domains/platforms/constraints）
        terminology: 术语库字典（由 load_terminology 返回）

    Returns:
        规范术语（canonical term），如果无匹配则返回 None

    匹配规则：
    - 大小写不敏感
    - 先尝试匹配规范术语（canonical term）
    - 再尝试匹配变体（variants）
    """
    aliases = terminology.get("aliases", {})

    # 检查类别是否存在
    if category not in aliases:
        return None

    category_aliases = aliases[category]
    term_lower = term.lower()

    # 1. 尝试精确匹配规范术语
    for canonical_term in category_aliases:
        if canonical_term.lower() == term_lower:
            return canonical_term

    # 2. 尝试匹配变体
    for canonical_term, variants in category_aliases.items():
        if variants and isinstance(variants, list):
            for variant in variants:
                if variant.lower() == term_lower:
                    return canonical_term

    return None


def normalize_entities(entities: dict[str, Any], terminology: dict[str, Any]) -> dict[str, Any]:
    """
    规范化实体名称

    Args:
        entities: 实体字典，格式：
            {
                "methods": [{"name": "submapping", "type": "mapping"}, ...],
                "datasets": [{"name": "kitti"}, ...],
                ...
            }
        terminology: 术语库字典（由 load_terminology 返回）

    Returns:
        规范化后的实体字典，格式与输入相同

    处理规则：
    - 对每个实体的 "name" 字段进行模糊匹配
    - 如果匹配成功，替换为规范术语
    - 如果匹配失败，保持原始术语
    - 保留所有其他字段（type, confidence, 等）
    """
    normalized = {}

    # 支持的类别
    categories = ["methods", "datasets", "domains", "platforms", "constraints"]

    for category in categories:
        if category not in entities:
            continue

        category_entities = entities[category]

        # 空列表直接复制
        if not category_entities:
            normalized[category] = []
            continue

        # 规范化每个实体
        normalized_list = []
        for entity in category_entities:
            # 复制整个实体对象
            normalized_entity = entity.copy()

            # 只规范化 name 字段
            if "name" in entity:
                original_name = entity["name"]
                canonical_name = fuzzy_match(original_name, category, terminology)

                if canonical_name:
                    normalized_entity["name"] = canonical_name
                # 否则保持原始名称

            normalized_list.append(normalized_entity)

        normalized[category] = normalized_list

    return normalized
