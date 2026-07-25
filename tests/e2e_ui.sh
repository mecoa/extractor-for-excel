#!/bin/bash
# E2E UI 测试：用 playwright-cli 驱动浏览器完成步骤 1-4（含真实 MinerU OCR + DeepSeek LLM）
#
# 用法:
#   MINERU_TOKEN=sk-xxx DEEPSEEK_KEY=sk-yyy bash tests/e2e_ui.sh
#
# 依赖:
#   - playwright-cli + 浏览器: playwright-cli install-browser chrome-for-testing
#   - 系统库: sudo apt-get install -y libnspr4 libnss3
#   - uv, curl
#
# 设计说明:
#   - Excel 通过浏览器 file chooser 上传（真实 UI 路径）
#   - PDF 文件夹用 <input webkitdirectory>，headless 浏览器无法可靠注入目录，
#     故 PDF 改由后端 /api/pdf/upload 上传；其余全部走真实 UI 交互。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FIXTURES_DIR="$PROJECT_DIR/tests/fixtures/generated"

# ---------- 配置（密钥通过环境变量传入，切勿硬编码进仓库）----------
MINERU_TOKEN="${MINERU_TOKEN:-}"
DEEPSEEK_KEY="${DEEPSEEK_KEY:-}"
DEEPSEEK_URL="${DEEPSEEK_URL:-https://api.deepseek.com/v1}"
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-flash}"
PW_BROWSER="${PW_BROWSER:-chromium}"
SERVER_URL="http://127.0.0.1:8000"

if [ -z "$MINERU_TOKEN" ] || [ -z "$DEEPSEEK_KEY" ]; then
    echo "错误: 请设置 MINERU_TOKEN 和 DEEPSEEK_KEY 环境变量"
    echo "  MINERU_TOKEN=sk-xxx DEEPSEEK_KEY=sk-yyy bash tests/e2e_ui.sh"
    exit 1
fi

# ---------- 小工具 ----------
pw() { playwright-cli "$@" 2>&1; }
pweval() { playwright-cli --raw eval "$1" 2>/dev/null | tail -1; }

# 轮询进度元素直到出现"完成"或"出错"
wait_progress() {
    local sel="$1" max="${2:-150}"
    for _ in $(seq 1 "$max"); do
        local txt; txt=$(pweval "document.querySelector('$sel')?.textContent || ''")
        echo "  进度: $txt"
        case "$txt" in
            *完成*) return 0 ;;
            *出错*) echo "  失败: $txt"; return 1 ;;
        esac
        sleep 3
    done
    echo "  超时"
    return 1
}

# ---------- 夹具 ----------
echo "=== 生成夹具 ==="
uv run python "$PROJECT_DIR/tests/fixtures/generate_fixtures.py" --out "$FIXTURES_DIR"

# ---------- 服务 ----------
echo "=== 启动服务 ==="
pkill -f "web_main.py" 2>/dev/null || true
sleep 1
cd "$PROJECT_DIR"
uv run python web_main.py > /tmp/e2e_web.log 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 15); do
    curl -sf "$SERVER_URL/api/state" >/dev/null 2>&1 && break
    sleep 1
done
curl -sf "$SERVER_URL/api/state" >/dev/null 2>&1 || { echo "服务启动失败"; cat /tmp/e2e_web.log; exit 1; }
echo "服务已启动: $SERVER_URL (pid=$SERVER_PID)"

cleanup() {
    echo "=== 清理 ==="
    kill "$SERVER_PID" 2>/dev/null || true
    pw close >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------- 浏览器 ----------
pw close >/dev/null 2>&1 || true
pw open --browser="$PW_BROWSER" "$SERVER_URL" >/dev/null
sleep 2

echo "=== 步骤 1: Excel 模板 ==="
# 点击 file input 触发 file chooser，再上传
pw click "#excel-file" >/dev/null
sleep 1
pw upload "$FIXTURES_DIR/template.xlsx" >/dev/null
sleep 2
FIELDS=$(pweval "JSON.stringify([...document.querySelectorAll('#fields-table .f-name')].map(e=>e.textContent))")
echo "  已加载字段: $FIELDS"
echo "$FIELDS" | grep -q "年" || { echo "  Excel 加载失败"; exit 1; }
pw click "getByRole('button', { name: '保存字段配置' })" >/dev/null
sleep 2

echo "=== 步骤 2: 文件名匹配 ==="
# 选匹配字段 chips
for f in 年 月 号; do
    pw click ".chip:text-is('$f')" >/dev/null
    sleep 1
done
ON=$(pweval "JSON.stringify([...document.querySelectorAll('.chip.on')].map(c=>c.textContent))")
echo "  已选匹配字段: $ON"
# 填广播模板
pw fill "#pattern" '{年}-{月}-{号}#' >/dev/null
sleep 1
# PDF 经后端上传（webkitdirectory 在 headless 下不可靠）
curl -sf -X POST "$SERVER_URL/api/pdf/upload" \
    -F "files=@$FIXTURES_DIR/pdfs/2024-01-001#.pdf" \
    -F "files=@$FIXTURES_DIR/pdfs/2024-02-002#.pdf" \
    -F "files=@$FIXTURES_DIR/pdfs/2024-03-003#.pdf" \
    -F "files=@$FIXTURES_DIR/pdfs/noise.pdf" >/dev/null && echo "  PDF 已上传"
sleep 1
# 预览匹配
pw click "getByRole('button', { name: '预览匹配' })" >/dev/null
sleep 2
MATCHED=$(pweval "document.querySelectorAll('#match-table tbody tr').length")
echo "  匹配行数: $MATCHED"
# 全选 + 保存
pw click "getByRole('button', { name: '全选' })" >/dev/null
sleep 1
pw click "getByRole('button', { name: '保存选择' })" >/dev/null
sleep 2

echo "=== 步骤 3: OCR ==="
# 保存项目（OCR 需要 cache db 路径）；顶部"保存"是页面首个 button[name=保存]
pw fill "#project-path" "$FIXTURES_DIR/test_project.json" >/dev/null
sleep 1
pw click "getByRole('button', { name: '保存' }).first()" >/dev/null
sleep 2
[ -f "$FIXTURES_DIR/test_project.json" ] && echo "  项目已保存"
# MinerU 配置（精准模式）
pw fill "#mineru-token" "$MINERU_TOKEN" >/dev/null
sleep 1
pw check "#mineru-precision" >/dev/null
sleep 1
pw click "getByRole('button', { name: '保存设置' })" >/dev/null
sleep 1
# 启动 OCR 并等待
pw click "getByRole('button', { name: '开始 OCR' })" >/dev/null
sleep 2
echo "  等待 OCR (真实 MinerU API)..."
wait_progress "#ocr-progress" 150 || { echo "OCR 失败"; exit 1; }

echo "=== 步骤 4: LLM 提取 & 导出 ==="
# 导航到步骤 4
pw click "getByText('提取导出')" >/dev/null
sleep 2
# LLM 配置
pw fill "#llm-url" "$DEEPSEEK_URL" >/dev/null
sleep 1
pw fill "#llm-key" "$DEEPSEEK_KEY" >/dev/null
sleep 1
pw fill "#llm-model" "$DEEPSEEK_MODEL" >/dev/null
sleep 1
# 步骤 4 内的"保存"是页面第二个 button[name=保存]
pw click "getByRole('button', { name: '保存' }).nth(1)" >/dev/null
sleep 1
# 启动提取并等待
pw click "getByRole('button', { name: '开始提取' })" >/dev/null
sleep 2
echo "  等待提取 (真实 DeepSeek API)..."
wait_progress "#extract-progress" 60 || { echo "提取失败"; exit 1; }
# 导出
pw click "getByRole('button', { name: '导出 Excel' })" >/dev/null
sleep 3

echo "=== 验证结果 ==="
# 通过 API 拉取导出文件做断言（浏览器下载在 .playwright-cli/ 下）
curl -sf -X POST "$SERVER_URL/api/extract/export" \
    -H "Content-Type: application/json" -d '{"path": ""}' \
    -o "$FIXTURES_DIR/output.xlsx" && echo "  已导出: $FIXTURES_DIR/output.xlsx"
uv run python -c "
import openpyxl, sys
wb = openpyxl.load_workbook('$FIXTURES_DIR/output.xlsx')
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
assert len(rows) >= 4, '导出行数不足'
values = [str(c) for r in rows[1:] for c in r if c]
joined = ' '.join(values)
for expect in ['12800.00', '9600.50', '23450.00']:
    assert expect in joined, f'缺少金额 {expect}'
print('  ✓ 导出内容校验通过 (3 行金额齐全)')
"

echo ""
echo "=== ✅ E2E 全流程通过 (步骤 1-4) ==="
