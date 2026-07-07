"""Paper Identity 工具

处理 paper_id 规范化、storage_id 生成
"""

import re
from paperbase.utils.hash import sha256_string


def normalize_paper_id(raw: str) -> str:
    """
    规范化 paper_id

    优先级：doi > pmid > arxiv > openalex > s2 > fallback
    """
    raw = raw.strip()

    # 限制最大长度
    if len(raw) > 500:
        raise ValueError(f"paper_id 过长: {len(raw)} 字符（最大 500）")

    # 验证非空
    if not raw:
        raise ValueError("paper_id 不能为空")

    # 验证字符集（可打印 ASCII）
    if not re.match(r'^[\x20-\x7E]+$', raw):
        raise ValueError(f"paper_id 包含非法字符")

    # DOI
    if raw.lower().startswith("doi:"):
        return f"doi:{raw[4:].strip()}"
    if raw.startswith("10."):
        return f"doi:{raw}"

    # arXiv
    arxiv_pattern = r"^(arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$"
    match = re.match(arxiv_pattern, raw, re.IGNORECASE)
    if match:
        return f"arxiv:{match.group(2)}"

    # PMID
    if raw.lower().startswith("pmid:"):
        return f"pmid:{raw[5:].strip()}"
    if raw.startswith("PMID"):
        return f"pmid:{raw[4:].strip()}"

    # OpenAlex
    if raw.lower().startswith("openalex:"):
        return raw.lower()

    # Semantic Scholar
    if raw.lower().startswith("s2:"):
        return raw.lower()

    # Fallback: 使用原始值
    return f"fallback:{sha256_string(raw)[:16]}"


def generate_storage_id(paper_id: str) -> str:
    """
    生成 storage_id

    格式: p_<12位hash>
    """
    if not paper_id:
        raise ValueError("paper_id 不能为空")

    hash_value = sha256_string(paper_id)
    return f"p_{hash_value[:12]}"


def parse_paper_id(paper_id: str) -> dict[str, str]:
    """
    解析 paper_id

    返回: {type: str, value: str}
    """
    if ":" not in paper_id:
        return {"type": "unknown", "value": paper_id}

    parts = paper_id.split(":", 1)
    type_part = parts[0]

    # 验证类型是否合法
    valid_types = {"doi", "arxiv", "pmid", "openalex", "s2", "fallback"}
    if type_part not in valid_types:
        return {"type": "unknown", "value": paper_id}

    return {"type": type_part, "value": parts[1]}
