"""动态生成 E2E 测试夹具：Excel 模板 + 匹配的 PDF 文件。

产物写入 tests/fixtures/generated/（已被 .gitignore 忽略），不入库。

用法:
    uv run python tests/fixtures/generate_fixtures.py
    uv run python tests/fixtures/generate_fixtures.py --out /tmp/my_fixtures

生成内容:
    template.xlsx          发票台账模板，列: 年/月/号/开票单位/金额
    pdfs/2024-01-001#.pdf   ...按 {年}-{月}-{号}# 广播模板命名的发票 PDF
    pdfs/2024-02-002#.pdf
    pdfs/noise.pdf          一个不匹配的干扰文件
"""

from __future__ import annotations

import argparse
import os

from fpdf import FPDF
from openpyxl import Workbook


ROWS = [
    {"年": "2024", "月": "01", "号": "001", "开票单位": "北京示例科技有限公司", "金额": "12800.00"},
    {"年": "2024", "月": "02", "号": "002", "开票单位": "上海样例贸易有限公司", "金额": "9600.50"},
    {"年": "2024", "月": "03", "号": "003", "开票单位": "深圳测试制造有限公司", "金额": "23450.00"},
]

HEADERS = ["年", "月", "号", "开票单位", "金额"]

_CJK_FONT_CANDIDATES = [
    os.path.expanduser("~/.fonts/NotoSansSC-VF.ttf"),
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _find_cjk_font() -> str | None:
    for p in _CJK_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def make_excel(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "发票台账"
    ws.append(HEADERS)
    for row in ROWS:
        ws.append([row["年"], row["月"], row["号"], "", ""])
    wb.save(path)


def make_pdf(path: str, lines: list[str]) -> None:
    """生成一个可被 OCR 读取的 PDF，使用系统 CJK 字体渲染中文。"""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False, margin=0)
    pdf.add_page()

    font_path = _find_cjk_font()
    if font_path:
        pdf.add_font("CJK", "", font_path)
        pdf.set_font("CJK", size=14)
    else:
        pdf.set_font("Helvetica", size=14)

    pdf.set_y(60)
    for line in lines:
        pdf.cell(0, 12, text=line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)


def generate(out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    pdf_dir = os.path.join(out_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)

    excel_path = os.path.join(out_dir, "template.xlsx")
    make_excel(excel_path)

    pdf_paths = []
    for row in ROWS:
        name = f"{row['年']}-{row['月']}-{row['号']}#.pdf"
        p = os.path.join(pdf_dir, name)
        make_pdf(
            p,
            [
                "INVOICE / FA PIAO",
                f"No: {row['年']}-{row['月']}-{row['号']}",
                f"Seller: {row['开票单位']}",
                f"Amount (RMB): {row['金额']}",
                f"Date: {row['年']}-{row['月']}",
            ],
        )
        pdf_paths.append(p)

    noise = os.path.join(pdf_dir, "noise.pdf")
    make_pdf(noise, ["Unrelated document", "This file should not match any row."])

    return {"excel": excel_path, "pdf_dir": pdf_dir, "pdfs": pdf_paths, "noise": noise}


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 E2E 测试夹具")
    default_out = os.path.join(os.path.dirname(__file__), "generated")
    parser.add_argument("--out", default=default_out, help="输出目录")
    args = parser.parse_args()
    info = generate(args.out)
    print("已生成夹具:")
    print(f"  Excel : {info['excel']}")
    print(f"  PDF   : {info['pdf_dir']} ({len(info['pdfs'])} 个匹配 + 1 个干扰)")


if __name__ == "__main__":
    main()
