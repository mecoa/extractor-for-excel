import json
import os
from typing import List, Optional
from models.field import FieldDef, MatchRule


class Project:
    def __init__(self, path: str = ""):
        self.path = path
        self.excel_path: str = ""
        self.pdf_folder: str = ""
        self.fields: List[FieldDef] = []
        self.match_rule: MatchRule = MatchRule()
        self.context_fields: List[str] = []
        self.llm_config: dict = {}
        self.ocr_provider: str = "mineru"
        self.mineru_token: str = ""
        self.mineru_precision: bool = False
        self.baidu_api_key: str = ""
        self.baidu_secret_key: str = ""
        self.match_results: list = []
        self.selected_rows: list[int] = []

    def save(self):
        data = {
            "excel_path": self.excel_path,
            "pdf_folder": self.pdf_folder,
            "fields": [f.to_dict() for f in self.fields],
            "match_rule": self.match_rule.to_dict() if self.match_rule else {},
            "context_fields": self.context_fields,
            "llm_config": self.llm_config,
            "ocr_provider": self.ocr_provider,
            "mineru_token": self.mineru_token,
            "mineru_precision": self.mineru_precision,
            "baidu_api_key": self.baidu_api_key,
            "baidu_secret_key": self.baidu_secret_key,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        self.path = path
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.excel_path = data.get("excel_path", "")
        self.pdf_folder = data.get("pdf_folder", "")
        self.fields = [FieldDef.from_dict(fd) for fd in data.get("fields", [])]
        self.match_rule = MatchRule.from_dict(data.get("match_rule", {}))
        self.context_fields = data.get("context_fields", [])
        self.llm_config = data.get("llm_config", {})
        self.ocr_provider = data.get("ocr_provider", "mineru")
        self.mineru_token = data.get("mineru_token", "")
        self.mineru_precision = data.get("mineru_precision", False)
        self.baidu_api_key = data.get("baidu_api_key", "")
        self.baidu_secret_key = data.get("baidu_secret_key", "")

    @classmethod
    def from_path(cls, path: str) -> "Project":
        p = cls()
        p.load(path)
        return p

    @property
    def excel_name(self) -> str:
        return os.path.basename(self.excel_path) if self.excel_path else ""

    @property
    def project_dir(self) -> str:
        return os.path.dirname(self.path) if self.path else ""

    def cache_db_path(self) -> str:
        if not self.path:
            return ""
        base = os.path.splitext(self.path)[0]
        return base + ".db"

    def update_llm_config(self, base_url: str, api_key: str, model: str):
        self.llm_config = {"base_url": base_url, "api_key": api_key, "model": model}
