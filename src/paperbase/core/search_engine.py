"""全文检索引擎

基于 SQLite FTS5 实现全文检索功能
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict


class SearchEngine:
    """全文检索引擎"""

    def __init__(self, index_path: Path, library_path: Path):
        """
        初始化搜索引擎

        Args:
            index_path: FTS5 索引数据库路径
            library_path: library/papers 目录路径
        """
        self.index_path = Path(index_path)
        self.library_path = Path(library_path)
        self.conn = None
        self._connect()

    def _connect(self):
        """连接或创建索引数据库"""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.index_path, timeout=10.0)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 启用 WAL 模式提升并发性能
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
        return False

    def build_index(self):
        """构建 FTS5 索引"""
        # 创建 FTS5 虚拟表
        self.conn.execute("DROP TABLE IF EXISTS chunks_fts")
        self.conn.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id,
                paper_id,
                content,
                position,
                tokenize = 'porter unicode61'
            )
        """)

        # 扫描所有 chunks.jsonl 文件
        if not self.library_path.exists():
            return

        for chunks_file in self.library_path.glob("*/chunks.jsonl"):
            self._index_chunks_file(chunks_file)

        self.conn.commit()

    def _index_chunks_file(self, chunks_file: Path):
        """
        索引单个 chunks.jsonl 文件

        Args:
            chunks_file: chunks.jsonl 文件路径
        """
        with open(chunks_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                chunk = json.loads(line)
                self.conn.execute(
                    """
                    INSERT INTO chunks_fts (chunk_id, paper_id, content, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        chunk["id"],
                        chunk["paper_id"],
                        chunk["content"],
                        chunk["position"]
                    )
                )

    def search(self, query: str, limit: int = 10, paper_id_filter: str = None) -> List[Dict[str, any]]:
        """
        执行全文搜索

        Args:
            query: 搜索查询（支持 FTS5 查询语法：AND/OR/NOT）
            limit: 返回结果数量限制
            paper_id_filter: 可选，只在指定 paper_id 的论文中搜索

        Returns:
            List[Dict]: 搜索结果列表，每个结果包含：
                - paper_id: 论文 ID
                - score: 相关性分数（BM25）
                - snippet: 匹配片段
        """
        if not query or not query.strip():
            return []

        # 转换查询语法（FTS5 使用不同的语法）
        fts_query = self._convert_query(query)

        try:
            # 构建 SQL 查询
            sql = """
                SELECT
                    paper_id,
                    bm25(chunks_fts) as score,
                    snippet(chunks_fts, 2, '<b>', '</b>', '...', 64) as snippet
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
            """

            params = [fts_query]

            # 如果指定了 paper_id，添加过滤条件
            if paper_id_filter:
                sql += " AND paper_id = ?"
                params.append(paper_id_filter)

            sql += " ORDER BY score LIMIT ?"
            params.append(limit)

            cursor = self.conn.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                results.append({
                    "paper_id": row["paper_id"],
                    "score": abs(row["score"]),  # BM25 分数是负数，取绝对值
                    "snippet": row["snippet"]
                })

            return results

        except sqlite3.OperationalError as e:
            # 查询语法错误，返回空结果
            return []

    def _convert_query(self, query: str) -> str:
        """
        转换查询语法为 FTS5 格式

        FTS5 支持：
        - AND (默认)
        - OR
        - NOT (使用 - 前缀)
        - 短语搜索 "phrase"

        Args:
            query: 用户查询

        Returns:
            str: FTS5 查询语法
        """
        # 替换 NOT 为 FTS5 的 NOT 语法
        # FTS5: "term1 NOT term2" 需要写成 "term1 -term2"
        query = query.replace(" NOT ", " NOT ")  # 保持原样，FTS5 支持 NOT

        return query

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
