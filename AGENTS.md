# AGENTS.md — Extractor for Excel

## Overview

A Python desktop application that extracts structured data from PDF/images and writes it into Excel templates using a pipeline: **Excel template → filename matching → MinerU OCR → LLM extraction → Excel output**.

Built with PySide6 (desktop GUI), using MinerU cloud API for document parsing and OpenAI-compatible APIs (including local Ollama) for AI extraction.

## Tech Stack

- **UI**: PySide6 (QStackedWidget custom stepper, no QWizard — avoid it, it deadlocks on `removePage`)
- **Package management**: uv (`uv sync && uv run python main.py`)
- **Excel**: openpyxl (write) + pandas (read)
- **HTTP**: httpx
- **Storage**: SQLite for OCR cache

## Architecture

Two frontends share the same `core/` business logic:
- **Desktop (PySide6)**: `main.py` → `app.py` → `ui/`
- **WebUI (FastAPI)**: `web_main.py` → `web/server.py` → `web/service.py` (+ `web/static/`)

The web layer is preferred for development/testing — it's headless-testable via pytest
(`tests/test_api.py`) and avoids Qt/libEGL setup. `web/service.py` is a Qt-free wrapper
around `Project` + `core/` that manages state and background jobs (OCR/extract) with
progress polling via `/api/job/{id}`.

```
main.py                     desktop entry point
app.py                      QApplication setup
web_main.py                 web entry point (uvicorn)
web/
  server.py                 FastAPI routes (/api/*), serves static/
  service.py                ProjectService — headless core wrapper + job runner
  static/                   single-page frontend (index.html, app.js, style.css)
tests/
  test_api.py               pytest API tests (TestClient)
ui/                         desktop GUI layer
  main_window.py            Stepper layout, step indicator, navigation
  step1_template.py         Excel load → field selector + annotations
  step2_matching.py         Filename pattern + broadcast matching
  step3_import.py           MinerU OCR import + cache
  step4_review.py           LLM extraction + confidence review + export
  widgets/conf_label.py     Colored confidence badge (high/medium/low/missing)
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

### Steering away from QWizard

QWizard.removePage() freezes the app when called during page transitions. The app uses QStackedWidget + a custom `StepIndicator` widget instead. Steps are freely navigable — click any step dot to jump. No forced sequential order.

### Confidence pipeline

```
OCR置信度 → embedding in LLM prompt → LLM输出置信度 → final = min(ocr, llm)
```

Four levels: `high` / `medium` / `low` / `missing`. LLM is instructed to output `missing` (not fabricate) for fields absent from the document.

### SQLite threading

Cache connections use `check_same_thread=False`. Worker threads in step3/step4 share the DB safely.

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

**Linux (Debian/Ubuntu/WSL):** `sudo apt-get install -y libegl1` (PySide6 needs EGL)

All Python deps are in `pyproject.toml`. Run `uv sync` once.

## Running

```bash
uv sync           # first time only

# WebUI (preferred for dev/testing)
uv run python web_main.py     # → http://127.0.0.1:8000

# Desktop
uv run python main.py
# or:
./run.sh          # auto-detects and fixes libEGL
```

## Common Issues

- **"打不开" on WSL**: Missing `libegl1`. `sudo apt-get install -y libegl1`
- **SQLite threading error**: Already fixed (`check_same_thread=False`). If reappears, ensure OcrCache connections aren't shared across threads.
- **MinerU 404**: MinerU API endpoints changed. Agent API uses `/api/v1/agent/parse/file` (signature upload), Precision API uses `/api/v4/file-urls/batch` (batch upload).
- **QWizard deadlock**: Don't use QWizard in this project. It's been replaced with QStackedWidget.

## Testing

WebUI API tests (preferred — headless, no Qt):

```bash
uv run pytest              # runs tests/test_api.py via FastAPI TestClient
```

`tests/test_api.py` covers steps 1-2 end-to-end (Excel load, field config, filename
matching, project save/open) plus error paths for OCR/extract/export. Network-dependent
steps (MinerU OCR, LLM extract) are validated only for their guard conditions.

Manual core checks:

```bash
uv run python -c "
from models.field import Confidence
assert Confidence.from_ocr(0.95) == Confidence.HIGH
from core.matcher import FilenameMatcher
# ... (see git log for test snippets)
"
```
