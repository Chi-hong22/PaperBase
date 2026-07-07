"""Paper Registry 实现

使用 SQLite 存储论文索引和状态
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, UTC
from paperbase.schemas.manifest import PaperState


class PaperRegistry:
    """论文索引 Registry"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=10.0)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 启用 WAL 模式提升并发性能
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
        return False

    def _init_schema(self):
        """初始化数据库 schema"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                storage_id TEXT NOT NULL,
                state TEXT NOT NULL,
                title TEXT,
                authors TEXT,  -- JSON array
                year INTEGER,
                doi TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_state ON papers(state)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)
        """)
        self.conn.commit()

    def register_paper(
        self,
        paper_id: str,
        storage_id: str,
        state: PaperState,
        title: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        doi: str | None = None
    ):
        """注册或更新论文"""
        authors_json = json.dumps(authors or [])
        now = datetime.now(UTC).isoformat()

        self.conn.execute("""
            INSERT INTO papers (paper_id, storage_id, state, title, authors, year, doi, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                storage_id = excluded.storage_id,
                state = excluded.state,
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                doi = excluded.doi,
                updated_at = excluded.updated_at
        """, (paper_id, storage_id, state.value, title, authors_json, year, doi, now))
        self.conn.commit()

    def get_paper(self, paper_id: str) -> dict | None:
        """查询单篇论文"""
        cursor = self.conn.execute(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["authors"] = json.loads(result["authors"])
            return result
        return None

    def update_state(self, paper_id: str, state: PaperState):
        """更新论文状态"""
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "UPDATE papers SET state = ?, updated_at = ? WHERE paper_id = ?",
            (state.value, now, paper_id)
        )
        self.conn.commit()

    def list_papers(self, state: PaperState | None = None) -> list[dict]:
        """列出论文"""
        if state:
            cursor = self.conn.execute(
                "SELECT * FROM papers WHERE state = ? ORDER BY updated_at DESC",
                (state.value,)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM papers ORDER BY updated_at DESC"
            )

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result["authors"] = json.loads(result["authors"])
            results.append(result)
        return results

    def close(self):
        """关闭连接"""
        self.conn.close()
