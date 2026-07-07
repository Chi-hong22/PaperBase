"""Entity Graph Builder - 将论文实体导出为图谱格式"""

import json
from pathlib import Path
from paperbase.utils.markdown import parse_frontmatter


class EntityGraphBuilder:
    """将 paper.md 中的 entities 转换为 Graphify 图谱节点和边"""

    # 类别到关系类型的映射
    CATEGORY_TO_RELATION = {
        "methods": "uses_method",
        "datasets": "uses_dataset",
        "domains": "in_domain",
        "platforms": "on_platform",
        "constraints": "has_constraint",
    }

    # 类别到节点类型的映射
    CATEGORY_TO_TYPE = {
        "methods": "Method",
        "datasets": "Dataset",
        "domains": "Domain",
        "platforms": "Platform",
        "constraints": "Constraint",
    }

    def __init__(self, base_dir: Path):
        """
        初始化 EntityGraphBuilder

        Args:
            base_dir: 项目根目录
        """
        self.base_dir = Path(base_dir)

    def extract_all_entities(self, library_dir: Path) -> dict:
        """
        提取所有论文的 entities

        Args:
            library_dir: library 目录路径

        Returns:
            格式: {paper_id: {category: [entity_dict, ...]}}
        """
        library_dir = Path(library_dir)
        papers_dir = library_dir / "papers"

        if not papers_dir.exists():
            return {}

        entities_by_paper = {}

        # 遍历所有论文目录
        for paper_dir in papers_dir.iterdir():
            if not paper_dir.is_dir():
                continue

            paper_md = paper_dir / "paper.md"
            if not paper_md.exists():
                continue

            # 读取 frontmatter
            try:
                with open(paper_md, "r", encoding="utf-8") as f:
                    content = f.read()

                frontmatter, _ = parse_frontmatter(content)

                # 提取 entities 字段
                entities = frontmatter.get("entities", {})
                if not entities:
                    continue

                paper_id = frontmatter.get("paper_id")
                if not paper_id:
                    continue

                entities_by_paper[paper_id] = entities

            except Exception:
                # 静默跳过无法解析的论文
                continue

        return entities_by_paper

    def build_entity_nodes(self, entities_by_paper: dict) -> list[dict]:
        """
        生成去重的实体节点

        Args:
            entities_by_paper: extract_all_entities 返回的字典

        Returns:
            节点列表，格式: [{id, type, name, category}, ...]
        """
        unique_entities = {}  # {entity_id: node_dict}

        for paper_id, entities_dict in entities_by_paper.items():
            for category, entity_list in entities_dict.items():
                if category not in self.CATEGORY_TO_RELATION:
                    continue

                for entity in entity_list:
                    entity_name = entity.get("name")
                    if not entity_name:
                        continue

                    # 生成唯一 ID: category_singular:name
                    category_singular = category.rstrip("s")  # methods -> method
                    entity_id = f"{category_singular}:{entity_name}"

                    # 去重
                    if entity_id not in unique_entities:
                        unique_entities[entity_id] = {
                            "id": entity_id,
                            "type": self.CATEGORY_TO_TYPE[category],
                            "name": entity_name,
                            "category": category,
                        }

        return list(unique_entities.values())

    def build_entity_edges(self, entities_by_paper: dict) -> list[dict]:
        """
        生成 Paper -> Entity 关系边

        Args:
            entities_by_paper: extract_all_entities 返回的字典

        Returns:
            边列表，格式: [{source, target, relation}, ...]
        """
        edges = []

        for paper_id, entities_dict in entities_by_paper.items():
            for category, entity_list in entities_dict.items():
                if category not in self.CATEGORY_TO_RELATION:
                    continue

                relation = self.CATEGORY_TO_RELATION[category]
                category_singular = category.rstrip("s")

                for entity in entity_list:
                    entity_name = entity.get("name")
                    if not entity_name:
                        continue

                    entity_id = f"{category_singular}:{entity_name}"

                    edges.append({
                        "source": paper_id,
                        "target": entity_id,
                        "relation": relation,
                    })

        return edges

    def export_to_jsonl(self, nodes: list, edges: list, output_path: Path) -> None:
        """
        导出为 JSONL 格式

        Args:
            nodes: 节点列表
            edges: 边列表
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            # 先写入所有节点
            for node in nodes:
                f.write(json.dumps(node, ensure_ascii=False) + "\n")

            # 再写入所有边
            for edge in edges:
                f.write(json.dumps(edge, ensure_ascii=False) + "\n")
