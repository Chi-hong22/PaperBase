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
    def papers_dir(self) -> Path:
        """Papers 根目录"""
        return self.base_dir / "library" / "papers"

    @property
    def paper_dir(self) -> Path:
        """论文子目录（用于存放 source、assets 等）"""
        return self.papers_dir / self.storage_id

    @property
    def paper_md(self) -> Path:
        """
        规范化 Markdown 文件路径（扁平化结构）

        新结构: library/papers/p_xxx.md
        旧结构: library/papers/p_xxx/paper.md（向后兼容）
        """
        # 优先使用新的扁平化路径
        flat_path = self.papers_dir / f"{self.storage_id}.md"
        if flat_path.exists():
            return flat_path

        # 回退到旧的嵌套路径（向后兼容）
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
