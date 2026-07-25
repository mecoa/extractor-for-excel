# AGENTS.md — Extractor for Excel

## Overview

A Python web application that extracts structured data from PDF/images and writes it into Excel templates using a pipeline: **Excel template → filename matching → MinerU OCR → LLM extraction → Excel output**.

Built with FastAPI (web backend + single-page frontend), using MinerU cloud API for document parsing and OpenAI-compatible APIs (including local Ollama) for AI extraction.

## Tech Stack

- **UI**: FastAPI + vanilla JS single-page frontend (custom stepper in `web/static/`)
- **Package management**: uv (`uv sync && uv run python web_main.py`)
- **Excel**: openpyxl (write) + pandas (read)
- **HTTP**: httpx
- **Storage**: SQLite for OCR cache

## Architecture

The web layer wraps the same `core/` business logic:
- **WebUI (FastAPI)**: `web_main.py` → `web/server.py` → `web/service.py` (+ `web/static/`)

`web/service.py` is a `ProjectService` wrapper around `Project` + `core/` that manages
state and background jobs (OCR/extract) with progress polling via `/api/job/{id}`.
It's fully headless-testable via pytest (`tests/test_api.py`). Uploaded Excel/PDF files
land in a per-session temp workdir, so no local path typing is required.

```
web_main.py                 web entry point (uvicorn)
web/
  server.py                 FastAPI routes (/api/*), upload endpoints, serves static/
  service.py                ProjectService — core wrapper + job runner + upload handling
  static/                   single-page frontend (index.html, app.js, style.css)
tests/
  test_api.py               pytest API tests (TestClient)
core/                       business logic
  ocr/
    engine.py               OcrEngine abstract class
    mineru_engine.py        MinerU cloud API (Flash/Precision engines)
    cache.py                SQLite OCR result cache (check_same_thread=False)
  extract/
    llm_client.py           OpenAI-compatible API client
    prompt_builder.py       Builds prompts from field defs + OCR text + context
  excel/
    reader.py               pandas-based Excel reader
    writer.py               openpyxl writer with confidence color fills
  matcher.py                Filename broadcast matching engine
  project.py                Project configuration (save/load .json)
models/                     data models
  field.py                  FieldDef, Confidence, MatchRule
  ocr_cache.py              OcrCacheEntry, OcrStatus
  extract_result.py         ExtractResult, FieldResult
```

## Key Design Decisions

### Confidence pipeline

```
OCR置信度 → embedding in LLM prompt → LLM输出置信度 → final = min(ocr, llm)
```

Four levels: `high` / `medium` / `low` / `missing`. LLM is instructed to output `missing` (not fabricate) for fields absent from the document.

### SQLite threading

Cache connections use `check_same_thread=False`. Background job threads (OCR/extract) in `web/service.py` share the DB safely.

### Prompt structure

LLM prompts are assembled from three parts:
1. `<call_context>` — existing Excel row values injected as background (user-toggled per field)
2. `<field_hints>` — extraction instructions + example values (static per template)
3. `<ocr_text>` — MinerU markdown output with confidence annotations

### Filename matching ("广播")

Uses Python's `string.Formatter` to expand field values into filenames:
```
Pattern: "{年}-{月}-{号}#"
Row data: 年=2024, 月=01, 号=001
→ Generated filename: "2024-01-001#"
```
This is then matched against actual PDF filenames in the selected folder.

## System Dependencies

All Python deps are in `pyproject.toml`. Run `uv sync` once.

## Running

```bash
uv sync           # first time only

uv run python web_main.py     # → http://127.0.0.1:8000
```

## Common Issues

- **SQLite threading error**: Already fixed (`check_same_thread=False`). If reappears, ensure OcrCache connections aren't shared across threads.
- **MinerU 404**: MinerU API endpoints changed. Agent API uses `/api/v1/agent/parse/file` (signature upload), Precision API uses `/api/v4/file-urls/batch` (batch upload).
- **Directory upload unsupported**: Step 2 uses `webkitdirectory` for folder upload — works in Chromium/Firefox desktop; older Safari may not support it.

## Testing

WebUI API tests (preferred — headless, no Qt):

```bash
uv run pytest              # runs tests/test_api.py via FastAPI TestClient
```

`tests/test_api.py` covers steps 1-2 end-to-end (Excel load, field config, filename
matching, project save/open) plus error paths for OCR/extract/export. Network-dependent
steps (MinerU OCR, LLM extract) are validated only for their guard conditions.

### E2E UI 测试 (playwright-cli，真实 API)

完整浏览器流程（步骤 1-4，含真实 MinerU OCR + LLM 提取）:

```bash
# 生成夹具（xlsx 模板 + 匹配 PDF，产物在 tests/fixtures/generated/，已 gitignore）
uv run python tests/fixtures/generate_fixtures.py

# 跑完整 E2E（密钥通过环境变量传入，切勿硬编码）
MINERU_TOKEN=sk-xxx DEEPSEEK_KEY=sk-yyy bash tests/e2e_ui.sh
```

- 需先安装浏览器: `playwright-cli install-browser chrome-for-testing`
- 需系统库: `libnspr4 libnss3`（`sudo apt-get install -y libnspr4 libnss3`）
- 可覆盖变量: `DEEPSEEK_URL`、`DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）、`PW_BROWSER`（默认 chromium）
- 夹具生成器 `tests/fixtures/generate_fixtures.py` 无第三方 PDF 依赖，手写合法单页 PDF

Manual core checks:

```bash
uv run python -c "
from models.field import Confidence
assert Confidence.from_ocr(0.95) == Confidence.HIGH
from core.matcher import FilenameMatcher
# ... (see git log for test snippets)
"
```
