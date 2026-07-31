import base64
import json
import os
import time
import httpx
from .engine import OcrEngine, OcrResult


class BaiduDocParseEngine(OcrEngine):
    """百度智能云文档解析 API — 需 API Key/Secret Key，异步接口(提交+轮询)

    支持 pdf/图片/doc/xlsx 等 18 种格式，返回 Markdown。
    文档: https://cloud.baidu.com/doc/OCR/s/Klxag8wiy
    """

    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    SUBMIT_URL = "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task"
    QUERY_URL = "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task/query"

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self._token = ""

    def _access_token(self) -> str:
        if self._token:
            return self._token
        resp = httpx.post(
            self.TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ValueError(data.get("error_description", "get access_token failed"))
        self._token = token
        return token

    def parse(self, file_path: str) -> OcrResult:
        try:
            token = self._access_token()
        except Exception as e:
            return OcrResult("", "", error=f"auth: {e}")

        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read())

            submit = httpx.post(
                self.SUBMIT_URL,
                params={"access_token": token},
                data={"file_data": file_data, "file_name": file_name},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=60,
            )
            submit.raise_for_status()
            sdata = submit.json()
            if sdata.get("error_code"):
                return OcrResult("", "", error=sdata.get("error_msg", "submit failed"))

            task_id = sdata["result"]["task_id"]

            time.sleep(5)
            for _ in range(120):
                query = httpx.post(
                    self.QUERY_URL,
                    params={"access_token": token},
                    data={"task_id": task_id},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30,
                )
                query.raise_for_status()
                qdata = query.json()
                if qdata.get("error_code"):
                    return OcrResult("", "", error=qdata.get("error_msg", "query failed"))

                result = qdata["result"]
                status = result.get("status")
                if status == "success":
                    markdown = self._fetch_markdown(result)
                    return OcrResult(
                        markdown=markdown,
                        raw_data=json.dumps(result, ensure_ascii=False),
                        page_count=1,
                    )
                elif status == "failed":
                    return OcrResult("", "", error=result.get("task_error") or "parse failed")
                time.sleep(3)
            return OcrResult("", "", error="timeout")
        except Exception as e:
            return OcrResult("", "", error=str(e))

    def _fetch_markdown(self, result: dict) -> str:
        markdown_url = result.get("markdown_url")
        if markdown_url:
            resp = httpx.get(markdown_url, timeout=60)
            resp.raise_for_status()
            return resp.text

        parse_url = result.get("parse_result_url")
        if parse_url:
            resp = httpx.get(parse_url, timeout=60)
            resp.raise_for_status()
            return self._markdown_from_parse_result(resp.json())
        return ""

    def _markdown_from_parse_result(self, data: dict) -> str:
        parts: list[str] = []
        for page in data.get("pages", []):
            tables = {t["layout_id"]: t.get("markdown", "") for t in page.get("tables", [])}
            for layout in page.get("layouts", []):
                ltype = layout.get("type")
                if ltype == "table":
                    parts.append(tables.get(layout["layout_id"], ""))
                elif ltype in ("image", "seal"):
                    continue
                else:
                    text = layout.get("text", "")
                    if text:
                        parts.append(text)
        return "\n\n".join(p for p in parts if p)

    def batch_parse(self, file_paths: list[str]) -> list[OcrResult]:
        return [self.parse(fp) for fp in file_paths]
