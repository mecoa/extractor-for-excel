from abc import ABC, abstractmethod
from typing import Optional


class OcrResult:
    def __init__(self, markdown: str, raw_data: str, page_count: int = 0, error: Optional[str] = None):
        self.markdown = markdown
        self.raw_data = raw_data
        self.page_count = page_count
        self.error = error


class OcrEngine(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> OcrResult:
        ...

    @abstractmethod
    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        ...
