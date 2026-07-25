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
import zlib

from openpyxl import Workbook


ROWS = [
    {"年": "2024", "月": "01", "号": "001", "开票单位": "北京示例科技有限公司", "金额": "12800.00"},
    {"年": "2024", "月": "02", "号": "002", "开票单位": "上海样例贸易有限公司", "金额": "9600.50"},
    {"年": "2024", "月": "03", "号": "003", "开票单位": "深圳测试制造有限公司", "金额": "23450.00"},
]

HEADERS = ["年", "月", "号", "开票单位", "金额"]


def make_excel(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "发票台账"
    ws.append(HEADERS)
    for row in ROWS:
        ws.append([row["年"], row["月"], row["号"], "", ""])
    wb.save(path)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(path: str, lines: list[str]) -> None:
    """生成一个最小但合法的单页 PDF，含可被 OCR 读取的文本。

    使用 WinAnsi 标准字体，仅支持 ASCII 文本；中文以拼音/英文替代，
    确保生成的 PDF 结构合法且文本层可提取。
    """
    content_lines = ["BT", "/F1 14 Tf", "72 760 Td", "16 TL"]
    for line in lines:
        content_lines.append(f"({_pdf_escape(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "replace")
    compressed = zlib.compress(stream)

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    )
    objects.append(
        b"<< /Length "
        + str(len(compressed)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + compressed
        + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(buf)
    n = len(objects) + 1
    buf += f"xref\n0 {n}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (
        b"trailer\n<< /Size "
        + str(n).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )

    with open(path, "wb") as f:
        f.write(buf)


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
