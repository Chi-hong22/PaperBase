"""Paper 路径管理"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PaperPaths:
    """论文存储路径管理"""
    storage_id: str
    base_dir: Path

    def __post_init__(self):
        """验证 storage_id 安全性"""
        # 验证 storage_id 不包含路径遍历字符
        if ".." in self.storage_id or "/" in self.storage_id or "\\" in self.storage_id:
            raise ValueError(f"Invalid storage_id (contains path traversal characters): {self.storage_id}")

        # 验证非空
        if not self.storage_id.strip():
            raise ValueError("storage_id cannot be empty")

    @property
    def paper_dir(self) -> Path:
        """论文目录（存储 manifest 和资源）"""
        return self.base_dir / "library" / "papers" / self.storage_id

    @property
    def paper_md(self) -> Path:
        """规范化 Markdown（平面结构：与目录同级）"""
        return self.base_dir / "library" / "papers" / f"{self.storage_id}.md"

    @property
    def manifest_json(self) -> Path:
        """Manifest 文件"""
        return self.paper_dir / "manifest.json"

    @property
    def references_jsonl(self) -> Path:
        """引用文件"""
        return self.paper_dir / "references.jsonl"

    @property
    def chunks_jsonl(self) -> Path:
        """分块文件"""
        return self.paper_dir / "chunks.jsonl"

    @property
    def assets_dir(self) -> Path:
        """资产目录"""
        return self.paper_dir / "assets"

    @property
    def source_dir(self) -> Path:
        """源文件目录"""
        return self.paper_dir / "source"

    @property
    def source_pdf(self) -> Path:
        """源 PDF"""
        return self.source_dir / "source.pdf"

    def create_directories(self):
        """创建所有必需目录"""
        self.paper_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(exist_ok=True)
        self.source_dir.mkdir(exist_ok=True)
