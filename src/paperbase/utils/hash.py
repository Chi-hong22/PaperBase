"""Hash 工具函数"""

import hashlib
from pathlib import Path


def sha256_string(text: str) -> str:
    """计算字符串的 SHA256"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件的 SHA256"""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
