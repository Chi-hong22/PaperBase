"""Paper 路径管理"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PaperPaths:
    """论文存储路径管理"""
    storage_id: str
    base_dir: Path

    @property
    def paper_dir(self) -> Path:
        """论文目录"""
        return self.base_dir / "library" / "papers" / self.storage_id

    @property
    def paper_md(self) -> Path:
        """规范化 Markdown"""
        return self.paper_dir / "paper.md"

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
