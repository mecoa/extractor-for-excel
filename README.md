# Extractor for Excel

AI 驱动的文档 → Excel 数据提取工具。

从 PDF / 图片中提取结构化数据，写入 Excel 模板。适用于审计、财务、合同管理等场景。基于 Web 界面，浏览器即可使用。

## 工作流程

```
Excel 模板 → 文件名匹配 → MinerU OCR → LLM 提取 → Excel 输出
```

1. **Excel 模板配置**：上传 Excel，勾选要提取的字段，填写字段说明和示例值
2. **文件名匹配**：上传 PDF 文件夹，用广播语法（`{年}-{月}-{号}#`）自动匹配 PDF 到 Excel 行
3. **批量 OCR**：通过 MinerU 云端 API 解析文档，结果缓存到本地
4. **LLM 提取**：AI 按字段说明提取数据，置信度着色展示，人工复核后导出

## 快速开始

### 系统要求

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv)

### 安装与运行

```bash
git clone <repo-url>
cd extractor-for-excel
uv sync
uv run python web_main.py    # → http://127.0.0.1:8000
```

浏览器打开 http://127.0.0.1:8000 即可使用。

### 配置

- **MinerU**：默认使用免 Token 的 Agent 模式（≤10MB/20页）。如需处理大文件，在设置中填入 Token 切换精准模式。
- **LLM**：支持 OpenAI 兼容接口，可接入云端 API 或本地 Ollama。

## 功能特性

- 字段注解自动转为 LLM 提示词
- 已有 Excel 行数据可注入 LLM 作为背景信息
- 文件名广播匹配（`{字段}` → 文件名）
- 行级勾选，可部分处理
- OCR 结果 SQLite 缓存，避免重复解析
- 置信度四档着色：高/中/低/缺失
- 提取结果人工复核后导出

## 项目结构

```
web_main.py             入口（uvicorn）
web/                    FastAPI 后端 + 单页前端（static/）
core/                   业务逻辑（OCR、提取、Excel、匹配）
models/                 数据模型
tests/                  pytest API 测试
```

## 技术栈

- **UI**: FastAPI + 原生 JS 单页前端
- **OCR**: MinerU 云 API
- **LLM**: OpenAI 兼容接口
- **Excel**: openpyxl + pandas
- **包管理**: uv

## License

MIT
