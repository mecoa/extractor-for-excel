import json
import os
import time
import httpx
from .engine import OcrEngine, OcrResult


class MineruFlashEngine(OcrEngine):
    def __init__(self, token: str = "", base_url: str = "https://mineru.net/api/v1/agent"):
        self.token = token
        self.base_url = base_url

    def _upload_and_parse(self, file_path: str) -> OcrResult:
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "application/pdf")}
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            resp = httpx.post(
                f"{self.base_url}/parse/file",
                files=files,
                headers=headers,
                timeout=120,
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            return OcrResult("", "", error=data.get("msg", "unknown error"))
        result = data.get("data", {})
        markdown = result.get("markdown", "")
        return OcrResult(markdown=markdown, raw_data=json.dumps(data, ensure_ascii=False), page_count=1)

    def parse(self, file_path: str) -> OcrResult:
        return self._upload_and_parse(file_path)

    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        results = []
        for fp in file_paths:
            try:
                results.append(self.parse(fp))
            except Exception as e:
                results.append(OcrResult("", "", error=str(e)))
        return results


class MineruPrecisionEngine(OcrEngine):
    def __init__(self, token: str, base_url: str = "https://mineru.net/api/v4"):
        self.token = token
        self.base_url = base_url
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def parse(self, file_path: str) -> OcrResult:
        import hashlib
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        data_id = hashlib.md5(file_path.encode()).hexdigest()[:16]

        raw_resp = httpx.post(
            f"{self.base_url}/file-urls/upload",
            headers=self._headers,
            json={
                "data_id": data_id,
                "file_name": file_name,
                "file_size": file_size,
            },
            timeout=30,
        )
        raw_resp.raise_for_status()
        upload_info = raw_resp.json()
        if upload_info.get("code") != 0:
            return OcrResult("", "", error=upload_info.get("msg", "upload failed"))
        upload_data = upload_info["data"]

        with open(file_path, "rb") as f:
            upload_resp = httpx.put(
                upload_data["upload_url"],
                content=f,
                headers={"Content-Type": "application/octet-stream"},
                timeout=300,
            )
        upload_resp.raise_for_status()

        task_resp = httpx.post(
            f"{self.base_url}/extract/task",
            headers=self._headers,
            json={
                "url": upload_data["url"],
                "data_id": data_id,
                "is_ocr": True,
                "enable_table": True,
                "enable_formula": False,
            },
            timeout=30,
        )
        task_resp.raise_for_status()
        task_data = task_resp.json()
        if task_data.get("code") != 0:
            return OcrResult("", "", error=task_data.get("msg", "task creation failed"))
        task_id = task_data["data"]["task_id"]

        for _ in range(60):
            status_resp = httpx.get(
                f"{self.base_url}/extract/task-status",
                headers=self._headers,
                params={"task_id": task_id},
                timeout=15,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            state = status_data["data"]["state"]
            if state == "done":
                result = status_data["data"]["result"]
                markdown = result.get("markdown", "")
                full = json.dumps(status_data["data"], ensure_ascii=False)
                return OcrResult(markdown=markdown, raw_data=full, page_count=result.get("page_count", 0))
            elif state == "failed":
                return OcrResult("", "", error=status_data["data"].get("error", "parse failed"))
            time.sleep(2)

        return OcrResult("", "", error="timeout")

    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        results = []
        for fp in file_paths:
            try:
                results.append(self.parse(fp))
            except Exception as e:
                results.append(OcrResult("", "", error=str(e)))
        return results


def create_engine(token: str = "", use_precision: bool = False) -> OcrEngine:
    if use_precision:
        if not token:
            raise ValueError("token required for precision mode")
        return MineruPrecisionEngine(token=token)
    return MineruFlashEngine(token=token)
