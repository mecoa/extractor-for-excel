import json
import os
import shutil
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
            "excel_path": self._abs_to_rel(self.excel_path),
            "pdf_folder": self._abs_to_rel(self.pdf_folder),
            "fields": [f.to_dict() for f in self.fields],
            "match_rule": self.match_rule.to_dict() if self.match_rule else {},
            "context_fields": self.context_fields,
            "llm_config": {k: v for k, v in self.llm_config.items() if k != "api_key"},
            "ocr_provider": self.ocr_provider,
            "mineru_precision": self.mineru_precision,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        self.path = path
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.excel_path = self._rel_to_abs(data.get("excel_path", ""))
        self.pdf_folder = self._rel_to_abs(data.get("pdf_folder", ""))
        self.fields = [FieldDef.from_dict(fd) for fd in data.get("fields", [])]
        self.match_rule = MatchRule.from_dict(data.get("match_rule", {}))
        self.context_fields = data.get("context_fields", [])
        self.llm_config = data.get("llm_config", {})
        self.ocr_provider = data.get("ocr_provider", "mineru")
        self.mineru_precision = data.get("mineru_precision", False)

    @classmethod
    def from_path(cls, path: str) -> "Project":
        p = cls()
        p.load(path)
        return p

    def save_as(self, project_dir: str):
        os.makedirs(project_dir, exist_ok=True)
        if self.excel_path and os.path.isfile(self.excel_path):
            excel_dest = os.path.join(project_dir, "template.xlsx")
            shutil.copy2(self.excel_path, excel_dest)
            self.excel_path = excel_dest
        self.path = os.path.join(project_dir, "project.json")
        self.save()

    @property
    def excel_name(self) -> str:
        return os.path.basename(self.excel_path) if self.excel_path else ""

    @property
    def project_dir(self) -> str:
        return os.path.dirname(self.path) if self.path else ""

    def cache_db_path(self) -> str:
        if not self.project_dir:
            return ""
        return os.path.join(self.project_dir, "cache.db")

    def update_llm_config(self, base_url: str, api_key: str, model: str):
        self.llm_config = {"base_url": base_url, "api_key": api_key, "model": model}

    def _abs_to_rel(self, abs_path: str) -> str:
        if not abs_path or not self.project_dir:
            return abs_path
        try:
            rel = os.path.relpath(abs_path, self.project_dir)
            if not rel.startswith(".."):
                return rel
            return abs_path
        except ValueError:
            return abs_path

    def _rel_to_abs(self, stored_path: str) -> str:
        if not stored_path or not self.project_dir:
            return stored_path
        if os.path.isabs(stored_path):
            return stored_path
        return os.path.join(self.project_dir, stored_path)
