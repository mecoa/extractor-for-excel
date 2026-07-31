from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MISSING = "missing"

    @classmethod
    def from_ocr(cls, score: float) -> Confidence:
        if score >= 0.9:
            return cls.HIGH
        elif score >= 0.7:
            return cls.MEDIUM
        else:
            return cls.LOW

    @classmethod
    def merge(cls, ocr_conf: Confidence, llm_conf: Confidence) -> Confidence:
        rank = {cls.HIGH: 3, cls.MEDIUM: 2, cls.LOW: 1, cls.MISSING: 0}
        ocr_r = rank.get(ocr_conf, 0)
        llm_r = rank.get(llm_conf, 0)
        merged = min(ocr_r, llm_r)
        rev = {3: cls.HIGH, 2: cls.MEDIUM, 1: cls.LOW, 0: cls.MISSING}
        return rev[merged]

    def display(self) -> str:
        return self.value


@dataclass
class FieldDef:
    name: str
    annotation: str = ""
    examples: List[str] = field(default_factory=list)
    is_context: bool = False
    selected: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "examples": self.examples,
            "is_context": self.is_context,
            "selected": self.selected,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FieldDef:
        return cls(
            name=d["name"],
            annotation=d.get("annotation", ""),
            examples=d.get("examples", []),
            is_context=d.get("is_context", False),
            selected=d.get("selected", True),
        )


@dataclass
class MatchRule:
    pattern: str = ""
    match_fields: List[str] = field(default_factory=list)
    pdf_folder: str = ""

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "match_fields": self.match_fields,
            "pdf_folder": self.pdf_folder,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MatchRule:
        return cls(
            pattern=d.get("pattern", ""),
            match_fields=d.get("match_fields", []),
            pdf_folder=d.get("pdf_folder", ""),
        )
