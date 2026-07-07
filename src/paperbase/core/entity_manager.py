"""Entity Manager - 管理论文实体提取与更新"""

from pathlib import Path
import yaml
from paperbase.core.paths import PaperPaths
from paperbase.core.manifest import load_manifest, save_manifest
from paperbase.core.llm_client import LLMClient
from paperbase.schemas.paper import PaperMetadata, PaperEntity
from paperbase.utils.hash import sha256_string


class EntityManager:
    """管理论文实体（methods/datasets/domains/platforms/constraints）"""

    def __init__(self, base_dir: Path, llm_client: LLMClient | None = None):
        """
        初始化 EntityManager

        Args:
            base_dir: 项目根目录
            llm_client: LLM 客户端（可选，默认创建禁用的客户端）
        """
        self.base_dir = Path(base_dir)
        self.llm_client = llm_client or LLMClient()

    def update_entities(
        self,
        paper_id: str,
        storage_id: str,
        entities_dict: dict,
        merge: bool = False
    ) -> None:
        """
        更新论文的实体字段

        Args:
            paper_id: 论文 ID
            storage_id: 存储 ID
            entities_dict: 实体字典 {"methods": [...], "datasets": [...], ...}
            merge: 是否合并模式（True=追加，False=替换）

        Raises:
            FileNotFoundError: paper.md 不存在
            ValueError: frontmatter 格式错误或 schema 验证失败
        """
        paths = PaperPaths(storage_id=storage_id, base_dir=self.base_dir)

        # 读取 paper.md
        if not paths.paper_md.exists():
            raise FileNotFoundError(f"paper.md not found: {paths.paper_md}")

        with open(paths.paper_md, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 frontmatter
        frontmatter, body = self._parse_frontmatter(content)

        # 更新 entities（merge 或 replace）
        if merge:
            # 合并模式：追加到现有 entities
            existing_entities = frontmatter.get("entities", {})
            for category, items in entities_dict.items():
                if category not in existing_entities:
                    existing_entities[category] = []
                existing_entities[category].extend(items)
            frontmatter["entities"] = existing_entities
        else:
            # 替换模式：直接覆盖
            frontmatter["entities"] = entities_dict

        # 验证 schema
        try:
            PaperMetadata.model_validate(frontmatter)
        except Exception as e:
            raise ValueError(f"Schema validation failed: {e}") from e

        # 原子性写入
        new_content = self._build_markdown(frontmatter, body)
        self._atomic_write(paths.paper_md, new_content)

        # 更新 manifest.json 的 sha256
        self._update_manifest_hash(paths, new_content)

    def auto_extract_entities(
        self,
        paper_id: str,
        storage_id: str
    ) -> dict | None:
        """
        自动提取实体（使用 LLM）

        Args:
            paper_id: 论文 ID
            storage_id: 存储 ID

        Returns:
            提取的实体字典，或 None（LLM 禁用/失败）
        """
        # 检查 LLM 是否启用
        if not self.llm_client.enabled:
            return None

        # 读取 paper.md 内容
        paths = PaperPaths(storage_id=storage_id, base_dir=self.base_dir)

        if not paths.paper_md.exists():
            raise FileNotFoundError(f"paper.md not found: {paths.paper_md}")

        with open(paths.paper_md, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取实体
        entities_dict = self.llm_client.extract_entities(content)

        if entities_dict is None:
            return None

        # 更新到 paper.md
        self.update_entities(
            paper_id=paper_id,
            storage_id=storage_id,
            entities_dict=entities_dict,
            merge=False
        )

        return entities_dict

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """
        解析 YAML frontmatter

        Args:
            content: Markdown 内容

        Returns:
            (frontmatter_dict, body)

        Raises:
            ValueError: frontmatter 格式错误
        """
        parts = content.split("---\n")

        if len(parts) < 3:
            raise ValueError("Invalid frontmatter format: missing --- delimiters")

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in frontmatter: {e}") from e

        if not isinstance(frontmatter, dict):
            raise ValueError("Frontmatter must be a YAML dictionary")

        body = "---\n".join(parts[2:])
        return frontmatter, body

    def _build_markdown(self, frontmatter: dict, body: str) -> str:
        """
        构建 Markdown 内容

        Args:
            frontmatter: frontmatter 字典
            body: 正文内容

        Returns:
            完整的 Markdown 内容
        """
        yaml_str = yaml.dump(
            frontmatter,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
        return f"---\n{yaml_str}---\n{body}"

    def _atomic_write(self, path: Path, content: str) -> None:
        """
        原子性写入文件

        Args:
            path: 目标文件路径
            content: 文件内容

        Raises:
            Exception: 写入失败
        """
        temp_path = path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 原子性替换
            temp_path.replace(path)

        except Exception as e:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            raise RuntimeError(f"Atomic write failed: {e}") from e

    def _update_manifest_hash(self, paths: PaperPaths, new_content: str) -> None:
        """
        更新 manifest.json 的 canonical_md.sha256

        Args:
            paths: PaperPaths 实例
            new_content: 新的 paper.md 内容
        """
        manifest = load_manifest(paths.manifest_json)

        # 更新 sha256
        new_hash = sha256_string(new_content)
        if manifest.canonical_md is not None:
            manifest.canonical_md.sha256 = new_hash
        else:
            # 如果 canonical_md 不存在，创建新的
            from paperbase.schemas.manifest import CanonicalMD
            manifest.canonical_md = CanonicalMD(
                path="./paper.md",
                sha256=new_hash,
                schema_version="1.0"
            )

        # 保存 manifest
        save_manifest(manifest, paths.manifest_json)
