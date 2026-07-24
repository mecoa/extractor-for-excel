import json
import os
import time
import httpx
from .engine import OcrEngine, OcrResult


class MineruFlashEngine(OcrEngine):
    """Agent 轻量解析 API — 免 Token，≤10MB/20页，签名上传"""

    def __init__(self, token: str = "", base_url: str = "https://mineru.net/api/v1/agent"):
        self.token = token
        self.base_url = base_url

    def parse(self, file_path: str) -> OcrResult:
        file_name = os.path.basename(file_path)
        try:
            step1 = httpx.post(
                f"{self.base_url}/parse/file",
                json={"file_name": file_name, "language": "ch", "is_ocr": True, "enable_table": True},
                timeout=30,
            )
            step1.raise_for_status()
            data = step1.json()
            if data.get("code") != 0:
                return OcrResult("", "", error=data.get("msg", "create task failed"))

            task_id = data["data"]["task_id"]
            file_url = data["data"]["file_url"]

            with open(file_path, "rb") as f:
                put_resp = httpx.put(file_url, content=f.read(), timeout=120)
                put_resp.raise_for_status()

            for _ in range(60):
                poll_resp = httpx.get(
                    f"{self.base_url}/parse/{task_id}",
                    timeout=15,
                )
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()
                state = poll_data["data"]["state"]
                if state == "done":
                    markdown_url = poll_data["data"]["markdown_url"]
                    md_resp = httpx.get(markdown_url, timeout=30)
                    md_resp.raise_for_status()
                    return OcrResult(
                        markdown=md_resp.text,
                        raw_data=json.dumps(poll_data, ensure_ascii=False),
                        page_count=1,
                    )
                elif state == "failed":
                    return OcrResult("", "", error=poll_data["data"].get("err_msg", "parse failed"))
                time.sleep(2)
            return OcrResult("", "", error="timeout")
        except Exception as e:
            return OcrResult("", "", error=str(e))

    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        return [self.parse(fp) for fp in file_paths]


class MineruPrecisionEngine(OcrEngine):
    """精准解析 API — 需 Token，≤200MB/200页，批量上传"""

    def __init__(self, token: str, base_url: str = "https://mineru.net/api/v4"):
        self.token = token
        self.base_url = base_url

    def parse(self, file_path: str) -> OcrResult:
        results = self.batch_parse([file_path])
        return results[0]

    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        if not file_paths:
            return []
        results: list[OcrResult] = [OcrResult("", "", error="pending") for _ in file_paths]

        try:
            files_payload = []
            for fp in file_paths:
                files_payload.append({"name": os.path.basename(fp)})

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            }

            step1 = httpx.post(
                f"{self.base_url}/file-urls/batch",
                headers=headers,
                json={"files": files_payload, "model_version": "vlm", "is_ocr": True, "enable_table": True},
                timeout=30,
            )
            step1.raise_for_status()
            data1 = step1.json()
            if data1.get("code") != 0:
                error_msg = data1.get("msg", "batch create failed")
                return [OcrResult("", "", error=error_msg) for _ in file_paths]

            batch_id = data1["data"]["batch_id"]
            upload_urls = data1["data"]["file_urls"]

            for i, fp in enumerate(file_paths):
                if i >= len(upload_urls):
                    results[i] = OcrResult("", "", error="no upload url")
                    continue
                try:
                    with open(fp, "rb") as f:
                        put_resp = httpx.put(upload_urls[i], content=f.read(), timeout=120)
                        put_resp.raise_for_status()
                except Exception as e:
                    results[i] = OcrResult("", "", error=f"upload: {e}")

            for _ in range(120):
                poll_resp = httpx.get(
                    f"https://mineru.net/api/v4/extract-results/batch/{batch_id}",
                    headers=headers,
                    timeout=15,
                )
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()
                extract = poll_data["data"].get("extract_result", [])

                all_done = True
                for ei, er in enumerate(extract):
                    state = er.get("state")
                    if state == "done" and results[ei].markdown == "" and "pending" in results[ei].error:
                        zip_url = er.get("full_zip_url", "")
                        if zip_url:
                            try:
                                zip_resp = httpx.get(zip_url, timeout=60)
                                zip_resp.raise_for_status()
                                markdown = self._extract_markdown(zip_resp.content)
                                results[ei] = OcrResult(
                                    markdown=markdown,
                                    raw_data=json.dumps(er, ensure_ascii=False),
                                    page_count=1,
                                )
                            except Exception as e:
                                results[ei] = OcrResult("", "", error=f"download: {e}")
                    elif state == "failed":
                        if results[ei].markdown == "" and "pending" in results[ei].error:
                            results[ei] = OcrResult("", "", error=er.get("err_msg", "failed"))
                    elif state != "done":
                        all_done = False

                if all_done:
                    break
                time.sleep(3)

        except Exception as e:
            for i in range(len(results)):
                if results[i].markdown == "" and "pending" in results[i].error:
                    results[i] = OcrResult("", "", error=str(e))

        return results

    def _extract_markdown(self, zip_bytes: bytes) -> str:
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.endswith("full.md"):
                    return zf.read(name).decode("utf-8", errors="replace")
        return ""


def create_engine(
    token: str = "",
    use_precision: bool = False,
    provider: str = "mineru",
    baidu_api_key: str = "",
    baidu_secret_key: str = "",
) -> OcrEngine:
    if provider == "baidu":
        if not baidu_api_key or not baidu_secret_key:
            raise ValueError("baidu API Key and Secret Key required")
        from .baidu_engine import BaiduDocParseEngine
        return BaiduDocParseEngine(api_key=baidu_api_key, secret_key=baidu_secret_key)
    if use_precision:
        if not token:
            raise ValueError("token required for precision mode")
        return MineruPrecisionEngine(token=token)
    return MineruFlashEngine(token=token)
