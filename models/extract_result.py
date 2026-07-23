from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
from .field import Confidence


@dataclass
class FieldResult:
    value: str
    confidence: Confidence
    raw_ocr_text: str = ""
    manual_override: Optional[str] = None

    @property
    def display_value(self) -> str:
        return self.manual_override if self.manual_override else self.value


@dataclass
class ExtractResult:
    row_index: int
    file_path: str
    fields: Dict[str, FieldResult] = field(default_factory=dict)
    processed: bool = False

    def to_dict(self) -> dict:
        return {
            "row_index": self.row_index,
            "file_path": self.file_path,
            "fields": {
                k: {
                    "value": v.value,
                    "confidence": v.confidence.value,
                    "raw_ocr_text": v.raw_ocr_text,
                    "manual_override": v.manual_override,
                }
                for k, v in self.fields.items()
            },
        }
