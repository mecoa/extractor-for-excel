# AGENTS.md — Extractor for Excel

## Overview

A Python web application that extracts structured data from PDF/images and writes it into Excel templates using a pipeline: **Excel template → filename matching → MinerU OCR → LLM extraction → Excel output**.

Built with FastAPI (web backend + single-page frontend), using MinerU cloud API for document parsing and OpenAI-compatible APIs (including local Ollama) for AI extraction.

## Tech Stack

- **UI**: FastAPI + vanilla JS single-page frontend (custom stepper in `app/web/static/`)
- **Package management**: uv (`uv sync && uv run python web_main.py`)
- **Excel**: openpyxl (write) + pandas (read)
- **HTTP**: httpx
- **Storage**: SQLite (`cache.db`) for OCR results + extraction results
- **Secrets**: OS keyring (via `keyring` library) with `project.keys.json` fallback (chmod 600)

## Architecture

The web layer wraps the same `app/core/` business logic:
- **WebUI (FastAPI)**: `web_main.py` → `app.web.server` → `app.web.service` (+ `app/web/static/`)

`app/web/service.py` is a `ProjectService` wrapper around `Project` + `app/core/` that manages
state and background jobs (OCR/extract) with progress polling via `/api/job/{id}`.
It's fully headless-testable via pytest (`tests/test_api.py`). Uploaded Excel/PDF files
land in a per-session temp workdir, so no local path typing is required.

All backend Python code lives under `app/`. Entry points (`web_main.py`, `desktop_main.py`)
stay at the project root for `uv run` and PyInstaller.

```
web_main.py                 web entry point (uvicorn)
desktop_main.py             Windows exe entry (PyInstaller)
app/
  web/
    server.py               FastAPI routes (/api/*), upload endpoints, serves static/
    service.py              ProjectService — core wrapper + job runner + upload handling
    static/                 single-page frontend (index.html, app.js, style.css)
  core/                     business logic
    ocr/
      engine.py             OcrEngine abstract class
      mineru_engine.py      MinerU cloud API (Flash/Precision engines)
      cache.py              SQLite OCR result cache (check_same_thread=False)
    extract/
      llm_client.py         OpenAI-compatible API client
      prompt_builder.py     Builds prompts from field defs + OCR text + context
    excel/
      reader.py             pandas-based Excel reader
      writer.py             openpyxl writer with confidence color fills
    matcher.py              Filename broadcast matching engine
    project.py              Project configuration (save/load .json)
    storage.py              OcrCache + ResultCache (SQLite extract results persistence)
    keyring_manager.py      KeyManager — OS keyring + project.keys.json fallback
  models/                   data models
    field.py                FieldDef, Confidence, MatchRule
    ocr_cache.py            OcrCacheEntry, OcrStatus
    extract_result.py       ExtractResult, FieldResult
tests/
  test_api.py               pytest API tests (TestClient)
```

## Key Design Decisions

### Confidence pipeline

```
OCR置信度 → embedding in LLM prompt → LLM输出置信度 → final = min(ocr, llm)
```

Four levels: `high` / `medium` / `low` / `missing`. LLM is instructed to output `missing` (not fabricate) for fields absent from the document.

### Storage architecture

项目目录在 `~/Documents/extractor-projects/{项目名}/`（跨平台，Windows/macOS/Linux 通用）：

```
~/Documents/extractor-projects/发票提取/
├── project.json              ← 纯配置（相对路径，无 API Key）
├── project.keys.json         ← (仅 keyring 不可用时) chmod 600
├── cache.db                  ← SQLite: ocr_cache + extract_results 两张表
├── template.xlsx             ← Excel 模板副本
├── pdfs/                     ← PDF 文件（仅上传时存于此）
└── output/                   ← 导出产物
```

- **项目操作**：新建/打开都用原生文件管理器（`webkitdirectory`），选目录即项目目录。
- **新建**：`webkitdirectory` 选目录 → 取其名 → 创建到 `~/Documents/extractor-projects/{名}/`
- **打开**：`webkitdirectory` 选目录 → 上传 `project.json`/`cache.db`/`template.xlsx` → 自动导入到 managed 目录
- **PDF 不拷贝进项目目录**: 只保留绝对路径引用。重新打开时如果目录还在则直接复用 OCR 缓存（不重复 OCR）。
- **密钥管理**: `app/core/keyring_manager.py` → `KeyManager`。优先 OS keyring（GNOME Keyring / macOS Keychain），降级到 `{project_dir}/project.keys.json`（chmod 600）。`project.json` 不写任何密钥字段。

### SQLite threading

Cache connections use `check_same_thread=False`. Background job threads (OCR/extract) in `app/web/service.py` share the DB safely.

### Extract result persistence

`app/core/storage.py` 中的 `ResultCache` 将提取结果持久化到 `cache.db` 的 `extract_results` 表：
```sql
CREATE TABLE extract_results (
    row_index INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    value TEXT,
    confidence TEXT NOT NULL DEFAULT 'missing',
    llm_reasoning TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (row_index, field_name)
);
```

提取结果在每次行处理完成后自动写入 SQLite，打开项目时自动加载，重启不丢。用户手动修正字段值也会同步写回。

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
from app.models.field import Confidence
assert Confidence.from_ocr(0.95) == Confidence.HIGH
from app.core.matcher import FilenameMatcher
# ... (see git log for test snippets)
"
```
