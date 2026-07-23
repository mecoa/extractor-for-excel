import json
import sqlite3
import os
from typing import Optional, List
from models.ocr_cache import OcrCacheEntry, OcrStatus


class OcrCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS ocr_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                markdown TEXT,
                raw_data TEXT,
                error TEXT,
                page_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_file_path ON ocr_cache(file_path);
        """)
        self._conn.commit()

    def put(self, entry: OcrCacheEntry):
        self._conn.execute(
            """INSERT OR REPLACE INTO ocr_cache
               (file_path, file_name, status, markdown, raw_data, error, page_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                entry.file_path,
                entry.file_name,
                entry.status.value,
                entry.markdown,
                entry.raw_data,
                entry.error,
                entry.page_count,
            ),
        )
        self._conn.commit()

    def get(self, file_path: str) -> Optional[OcrCacheEntry]:
        row = self._conn.execute(
            "SELECT * FROM ocr_cache WHERE file_path = ?", (file_path,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_by_status(self, status: OcrStatus) -> List[OcrCacheEntry]:
        rows = self._conn.execute(
            "SELECT * FROM ocr_cache WHERE status = ?", (status.value,)
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def all(self) -> List[OcrCacheEntry]:
        rows = self._conn.execute("SELECT * FROM ocr_cache ORDER BY file_name").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def exists(self, file_path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM ocr_cache WHERE file_path = ?", (file_path,)
        ).fetchone()
        return row is not None

    def update_status(self, file_path: str, status: OcrStatus, error: str = ""):
        self._conn.execute(
            "UPDATE ocr_cache SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE file_path = ?",
            (status.value, error, file_path),
        )
        self._conn.commit()

    def remove(self, file_path: str):
        self._conn.execute("DELETE FROM ocr_cache WHERE file_path = ?", (file_path,))
        self._conn.commit()

    def clear(self):
        self._conn.execute("DELETE FROM ocr_cache")
        self._conn.commit()

    def close(self):
        self._conn.close()

    @staticmethod
    def _row_to_entry(row) -> OcrCacheEntry:
        return OcrCacheEntry(
            file_path=row["file_path"],
            file_name=row["file_name"],
            status=OcrStatus(row["status"]),
            markdown=row["markdown"],
            raw_data=row["raw_data"],
            error=row["error"],
            page_count=row["page_count"],
        )
