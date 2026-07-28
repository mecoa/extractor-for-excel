import os
import shutil
import tempfile
import threading
import uuid
from typing import Optional

from core.project import Project
from core.excel.reader import ExcelReader
from core.matcher import FilenameMatcher
from core.ocr.mineru_engine import create_engine
from core.ocr.cache import OcrCache
from core.extract.llm_client import LlmClient
from core.extract.prompt_builder import PromptBuilder
from core.excel.writer import ExcelWriter
from models.field import FieldDef, Confidence
from models.ocr_cache import OcrCacheEntry, OcrStatus
from models.extract_result import ExtractResult, FieldResult


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.current = 0
        self.total = 0
        self.done = False
        self.error: Optional[str] = None
        self.thread: Optional[threading.Thread] = None


class ProjectService:
    """Headless wrapper around a Project + core logic. Reused by the web API."""

    def __init__(self, project: Optional[Project] = None):
        self.project = project or Project()
        self.results: dict[int, dict] = {}
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.workdir = os.path.join(tempfile.gettempdir(), "extractor_web", uuid.uuid4().hex)
        os.makedirs(self.workdir, exist_ok=True)
        if not self.project.path:
            self.project.path = os.path.join(self.workdir, "project.json")

    def _upload_dir(self, name: str) -> str:
        d = os.path.join(self.workdir, name)
        os.makedirs(d, exist_ok=True)
        return d

    # ---- project lifecycle ----
    def new_project(self):
        self.project = Project()
        self.results = {}
        self.jobs = {}

    def open_project(self, path: str):
        self.project = Project.from_path(path)
        self.results = {}

    def save_project(self, path: str = "") -> str:
        if path:
            if not path.endswith(".json"):
                path += ".json"
            self.project.path = path
        if not self.project.path:
            raise ValueError("no project path")
        self.project.save()
        return self.project.path

    def state(self) -> dict:
        p = self.project
        return {
            "path": p.path,
            "excel_path": p.excel_path,
            "excel_name": p.excel_name,
            "pdf_folder": p.pdf_folder,
            "fields": [f.to_dict() for f in p.fields],
            "match_rule": p.match_rule.to_dict(),
            "selected_rows": p.selected_rows,
            "match_results": p.match_results,
            "mineru_token": p.mineru_token,
            "mineru_precision": p.mineru_precision,
            "ocr_provider": p.ocr_provider,
            "baidu_api_key": p.baidu_api_key,
            "baidu_secret_key": p.baidu_secret_key,
            "llm_config": p.llm_config,
            "has_results": bool(self.results),
        }

    # ---- step 1: template ----
    def load_excel(self, path: str) -> list[str]:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        reader = ExcelReader(path)
        self.project.excel_path = path
        headers = reader.headers
        self.project.fields = [
            FieldDef(name=h, annotation="", examples=[], is_context=False, selected=True)
            for h in headers
        ]
        self.project.match_results = []
        self.project.selected_rows = []
        self.results = {}
        self.jobs = {}
        return headers

    def save_excel_upload(self, filename: str, content: bytes) -> list[str]:
        dest = os.path.join(self._upload_dir("excel"), os.path.basename(filename))
        with open(dest, "wb") as f:
            f.write(content)
        return self.load_excel(dest)

    def set_fields(self, fields: list[dict]):
        self.project.fields = [FieldDef.from_dict(fd) for fd in fields]

    # ---- step 2: matching ----
    def match_field_candidates(self) -> list[str]:
        return [f.name for f in self.project.fields]

    def save_pdf_uploads(self, files: list[tuple[str, bytes]]) -> str:
        folder = self._upload_dir("pdfs")
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))
        for filename, content in files:
            dest = os.path.join(folder, os.path.basename(filename))
            with open(dest, "wb") as f:
                f.write(content)
        self.project.pdf_folder = folder
        self.project.match_rule.pdf_folder = folder
        return folder

    def preview_match(self, pattern: str, match_fields: list[str], pdf_folder: str = "") -> list[dict]:
        folder = pdf_folder or self.project.pdf_folder
        if not self.project.excel_path:
            raise ValueError("请先加载 Excel")
        if not folder or not os.path.isdir(folder):
            raise ValueError("请先上传 PDF 文件")
        if not pattern:
            raise ValueError("请填写文件名模板")
        if not match_fields:
            raise ValueError("请选择至少一个匹配字段")

        self.project.pdf_folder = folder
        self.project.match_rule.pattern = pattern
        self.project.match_rule.match_fields = match_fields
        self.project.match_rule.pdf_folder = folder

        reader = ExcelReader(self.project.excel_path)
        matcher = FilenameMatcher(self.project.match_rule)
        self.project.match_results = matcher.match(reader.get_data())
        return self.project.match_results

    def set_selected_rows(self, rows: list[int]):
        self.project.selected_rows = rows

    # ---- step 3: OCR ----
    def set_mineru(self, token: str, precision: bool):
        self.project.mineru_token = token
        self.project.mineru_precision = precision

    def set_ocr_config(
        self,
        provider: str = "mineru",
        token: str = "",
        precision: bool = False,
        baidu_api_key: str = "",
        baidu_secret_key: str = "",
    ):
        self.project.ocr_provider = provider
        self.project.mineru_token = token
        self.project.mineru_precision = precision
        self.project.baidu_api_key = baidu_api_key
        self.project.baidu_secret_key = baidu_secret_key

    def _selected_files(self) -> list[tuple[int, str]]:
        matched = [r for r in self.project.match_results if r["matched"]]
        selected = set(self.project.selected_rows) if self.project.selected_rows else {
            r["row_index"] for r in matched
        }
        return [(r["row_index"], r["file_path"]) for r in matched if r["row_index"] in selected]

    def ocr_table(self) -> list[dict]:
        rows = []
        db_path = self.project.cache_db_path()
        cache = OcrCache(db_path) if db_path and os.path.exists(db_path) else None
        matched = [r for r in self.project.match_results if r["matched"]]
        selected = set(self.project.selected_rows) if self.project.selected_rows else {
            r["row_index"] for r in matched
        }
        for r in matched:
            entry = cache.get(r["file_path"]) if cache else None
            rows.append({
                "row_index": r["row_index"],
                "file_name": os.path.basename(r["file_path"]),
                "selected": r["row_index"] in selected,
                "status": entry.status.value if entry else "pending",
                "page_count": entry.page_count if entry else 0,
                "error": (entry.error or "") if entry else "",
            })
        if cache:
            cache.close()
        return rows

    def ocr_preview(self, row_index: int) -> str:
        db_path = self.project.cache_db_path()
        if not db_path or not os.path.exists(db_path):
            return ""
        fp = next(
            (r["file_path"] for r in self.project.match_results if r["row_index"] == row_index),
            "",
        )
        if not fp:
            return ""
        cache = OcrCache(db_path)
        entry = cache.get(fp)
        cache.close()
        if entry and entry.markdown:
            return entry.markdown
        if entry and entry.error:
            return f"错误: {entry.error}"
        return "等待处理"

    def start_ocr(self) -> str:
        db_path = self.project.cache_db_path()
        if not db_path:
            raise ValueError("请先保存项目")
        files = [fp for _, fp in self._selected_files()]
        if not files:
            raise ValueError("没有选中的 PDF 文件")

        engine = create_engine(
            token=self.project.mineru_token,
            use_precision=self.project.mineru_precision,
            provider=self.project.ocr_provider,
            baidu_api_key=self.project.baidu_api_key,
            baidu_secret_key=self.project.baidu_secret_key,
        )
        job = Job("ocr")
        job.total = len(files)
        self.jobs[job.id] = job

        def run():
            cache = OcrCache(db_path)
            try:
                for i, fp in enumerate(files):
                    try:
                        entry = cache.get(fp)
                        if entry and entry.status == OcrStatus.DONE:
                            job.current = i + 1
                            continue
                        cache.put(OcrCacheEntry(fp, os.path.basename(fp), OcrStatus.PROCESSING))
                        result = engine.parse(fp)
                        if result.error:
                            entry = OcrCacheEntry(
                                fp, os.path.basename(fp), OcrStatus.FAILED, error=result.error
                            )
                        else:
                            entry = OcrCacheEntry(
                                fp, os.path.basename(fp), OcrStatus.DONE,
                                markdown=result.markdown, raw_data=result.raw_data,
                                page_count=result.page_count,
                            )
                        cache.put(entry)
                    except Exception as e:
                        cache.put(OcrCacheEntry(fp, os.path.basename(fp), OcrStatus.FAILED, error=str(e)))
                    job.current = i + 1
            except Exception as e:
                job.error = str(e)
            finally:
                cache.close()
                job.done = True

        job.thread = threading.Thread(target=run, daemon=True)
        job.thread.start()
        return job.id

    # ---- step 4: extract ----
    def set_llm(self, base_url: str, api_key: str, model: str):
        self.project.update_llm_config(base_url, api_key, model)

    def start_extract(self) -> str:
        if not self.project.llm_config.get("base_url"):
            raise ValueError("请先配置 LLM")
        selected = self._selected_files()
        if not selected:
            raise ValueError("请选择要处理的行")

        db_path = self.project.cache_db_path()
        reader = ExcelReader(self.project.excel_path)
        df = reader.get_data()
        llm_client = LlmClient.from_config(self.project.llm_config)

        extract_fields = [f for f in self.project.fields if f.selected and not f.is_context]
        context_names = [f.name for f in self.project.fields if f.is_context]
        builder = PromptBuilder(extract_fields, context_names)

        rows = []
        for row_idx, file_path in selected:
            row_data = {str(k): str(v) for k, v in df.iloc[row_idx].items()}
            rows.append((row_idx, file_path, row_data))

        job = Job("extract")
        job.total = len(rows)
        self.jobs[job.id] = job

        def run():
            cache = OcrCache(db_path)
            try:
                for i, (row_idx, file_path, row_data) in enumerate(rows):
                    try:
                        entry = cache.get(file_path)
                        ocr_text = entry.markdown if entry and entry.markdown else ""
                        messages = builder.build_messages(ocr_text, row_data)
                        result = llm_client.extract_json(messages)
                        with self._lock:
                            self.results[row_idx] = result or {}
                    except Exception as e:
                        with self._lock:
                            self.results[row_idx] = {"_error": str(e)}
                    job.current = i + 1
            except Exception as e:
                job.error = str(e)
            finally:
                cache.close()
                job.done = True

        job.thread = threading.Thread(target=run, daemon=True)
        job.thread.start()
        return job.id

    def extract_table(self) -> list[dict]:
        matched = [r for r in self.project.match_results if r["matched"]]
        selected = set(self.project.selected_rows) if self.project.selected_rows else {
            r["row_index"] for r in matched
        }
        rows = []
        for r in matched:
            ridx = r["row_index"]
            data = self.results.get(ridx)
            if data is None:
                status = "待提取"
            elif "_error" in data:
                status = f"错误: {data['_error']}"
            else:
                status = "已提取"
            rows.append({
                "row_index": ridx,
                "file_name": os.path.basename(r["file_path"]),
                "selected": ridx in selected,
                "status": status,
            })
        return rows

    def row_detail(self, row_index: int) -> list[dict]:
        data = self.results.get(row_index, {})
        detail = []
        for f in self.project.fields:
            if f.is_context or not f.selected:
                continue
            fd = data.get(f.name, {})
            conf_str = fd.get("confidence", "missing")
            try:
                conf = Confidence(conf_str).value
            except ValueError:
                conf = Confidence.MISSING.value
            detail.append({
                "field": f.name,
                "value": fd.get("value", ""),
                "confidence": conf,
            })
        return detail

    def update_field(self, row_index: int, field_name: str, value: str):
        with self._lock:
            data = self.results.setdefault(row_index, {})
            fd = data.setdefault(field_name, {"value": "", "confidence": "high"})
            fd["value"] = value

    def export(self, output_path: str = "") -> str:
        if not self.results:
            raise ValueError("没有可导出的数据")
        if not output_path:
            output_path = os.path.join(self._upload_dir("output"), "output.xlsx")
        if not output_path.endswith(".xlsx"):
            output_path += ".xlsx"

        extract_fields = [f for f in self.project.fields if f.selected and not f.is_context]
        field_names = [f.name for f in extract_fields]

        results_list = []
        for row_idx, data in self.results.items():
            if "_error" in data:
                continue
            frs = {}
            for fname in field_names:
                fd = data.get(fname, {})
                conf_str = fd.get("confidence", "missing")
                try:
                    conf = Confidence(conf_str)
                except ValueError:
                    conf = Confidence.MISSING
                frs[fname] = FieldResult(value=fd.get("value", ""), confidence=conf)
            results_list.append(ExtractResult(row_index=row_idx, file_path="", fields=frs))

        writer = ExcelWriter(self.project.excel_path, output_path)
        writer.write_results(results_list, field_names)
        return output_path

    def job_status(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return {
            "id": job.id,
            "kind": job.kind,
            "current": job.current,
            "total": job.total,
            "done": job.done,
            "error": job.error,
        }
