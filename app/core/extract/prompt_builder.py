from typing import List, Dict
from app.models.field import FieldDef, Confidence


class PromptBuilder:
    def __init__(self, fields: List[FieldDef], context_field_names: List[str]):
        self.fields = [f for f in fields if f.selected]
        self.extract_fields = [f for f in self.fields if not f.is_context]
        self.context_field_names = context_field_names

    def build_messages(
        self,
        ocr_markdown: str,
        row_context: Dict[str, str],
    ) -> list[dict]:
        system = self._build_system_prompt()
        user = self._build_user_prompt(ocr_markdown, row_context)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _build_system_prompt(self) -> str:
        lines = ["你是一个文档结构化提取助手。", "从 OCR 文本中提取信息，按字段填入 JSON。"]

        if self.extract_fields:
            lines.append("")
            lines.append("## 待提取字段")
            for f in self.extract_fields:
                desc = f.name
                if f.annotation:
                    desc += f"：{f.annotation}"
                if f.examples:
                    desc += f" 可能值示例：[{'、'.join(f.examples)}]"
                lines.append(f"- {desc}")

        lines.extend([
            "",
            "## 输出规则",
            "- 每个字段必须输出",
            "- confidence 取值：high（确认无误）、medium（基本正确）、low（不确定）、missing（原文无此信息）",
            "- 原文明确出现的才填 high，部分模糊的填 medium 或 low",
            "- 原文完全未出现的字段，confidence 必须填 missing，禁止编造",
            "- 输出格式：JSON，key 为字段名，value 为 {value, confidence}",
        ])
        return "\n".join(lines)

    def _build_user_prompt(self, ocr_markdown: str, row_context: Dict[str, str]) -> str:
        parts = []

        context_available = {k: v for k, v in row_context.items() if k in self.context_field_names and v}
        if context_available:
            parts.append("<call_context>")
            parts.append("当前已知信息（已有的行数据）：")
            for k, v in context_available.items():
                parts.append(f"- {k}：{v}")
            parts.append("</call_context>")

        if ocr_markdown:
            parts.append("")
            parts.append("<ocr_text>")
            parts.append(ocr_markdown)
            parts.append("</ocr_text>")

        parts.append("")
        parts.append("请输出 JSON：")

        return "\n".join(parts)
