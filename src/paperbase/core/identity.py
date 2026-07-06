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
    hash_value = sha256_string(paper_id)
    return f"p_{hash_value[:12]}"


def parse_paper_id(paper_id: str) -> dict[str, str]:
    """
    解析 paper_id

    返回: {type: str, value: str}
    """
    if ":" in paper_id:
        type_part, value_part = paper_id.split(":", 1)
        return {"type": type_part, "value": value_part}
    return {"type": "unknown", "value": paper_id}
