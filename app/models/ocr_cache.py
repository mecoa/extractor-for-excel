from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OcrStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class OcrCacheEntry:
    file_path: str
    file_name: str
    status: OcrStatus = OcrStatus.PENDING
    markdown: Optional[str] = None
    raw_data: Optional[str] = None
    error: Optional[str] = None
    page_count: int = 0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "status": self.status.value,
            "markdown": self.markdown,
            "raw_data": self.raw_data,
            "error": self.error,
            "page_count": self.page_count,
        }
