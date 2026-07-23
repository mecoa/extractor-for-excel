import json
import threading
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView,
    QMessageBox, QTextEdit, QSplitter, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor
from models.field import Confidence, FieldDef
from models.extract_result import ExtractResult, FieldResult
from core.extract.llm_client import LlmClient
from core.extract.prompt_builder import PromptBuilder
from core.ocr.cache import OcrCache
from core.excel.writer import ExcelWriter
from core.excel.reader import ExcelReader
from ui.widgets.conf_label import ConfidenceLabel, CONF_COLORS


class ExtractWorker(QObject):
    progress = Signal(int, int)
    result_ready = Signal(int, dict)
    finished = Signal()

    def __init__(self, fields, context_fields, ocr_cache, llm_client, rows):
        super().__init__()
        self.fields = fields
        self.context_fields = context_fields
        self.ocr_cache = ocr_cache
        self.llm_client = llm_client
        self.rows = rows
        self.builder = PromptBuilder(fields, context_fields)

    def run(self):
        total = len(self.rows)
        for i, (row_idx, file_path, row_data) in enumerate(self.rows):
            try:
                entry = self.ocr_cache.get(file_path)
                ocr_text = entry.markdown if entry and entry.markdown else ""

                messages = self.builder.build_messages(ocr_text, row_data)
                result = self.llm_client.extract_json(messages)

                if result:
                    self.result_ready.emit(row_idx, result)
                else:
                    self.result_ready.emit(row_idx, {})
            except Exception as e:
                self.result_ready.emit(row_idx, {"_error": str(e)})
            self.progress.emit(i + 1, total)
        self.finished.emit()


class ReviewPage(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.results: dict[int, dict] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)

        title = QLabel("LLM 提取 && 导出")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 4px;")
        layout.addWidget(title)
        subtitle = QLabel("使用 AI 提取结构化数据，置信度着色展示，人工复核后导出到 Excel")
        subtitle.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #888; margin: 4px 0;")
        layout.addWidget(self.status_label)

        # LLM settings
        llm_layout = QHBoxLayout()
        self.llm_btn = QPushButton("LLM 设置")
        self.llm_btn.clicked.connect(self._llm_settings)
        self.extract_btn = QPushButton("开始提取")
        self.extract_btn.clicked.connect(self._start_extract)
        self.extract_btn.setStyleSheet("background-color: #0078D4; color: white; padding: 8px; font-weight: bold;")
        self.export_btn = QPushButton("导出到 Excel")
        self.export_btn.clicked.connect(self._export)
        self.export_btn.setEnabled(False)
        self.llm_config_label = QLabel("未配置 LLM")
        llm_layout.addWidget(self.llm_btn)
        llm_layout.addWidget(self.extract_btn)
        llm_layout.addWidget(self.export_btn)
        llm_layout.addWidget(self.llm_config_label)
        llm_layout.addStretch()
        layout.addLayout(llm_layout)

        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["行号", "文件名", "状态"])
        self.table.itemClicked.connect(self._show_row_detail)
        splitter.addWidget(self.table)

        detail_widget = QVBoxLayout()
        self.detail_label = QLabel("选中行详情（点击行查看提取结果）")
        detail_widget.addWidget(self.detail_label)
        self.detail_table = QTableWidget(0, 4)
        self.detail_table.setHorizontalHeaderLabels(["字段", "提取值", "置信度", "操作"])
        self.detail_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        detail_widget.addWidget(self.detail_table)

        detail_container = QVBoxLayout()
        detail_container.addLayout(detail_widget)
        detail_widget_inner = QWidget()
        detail_widget_inner.setLayout(detail_container)
        splitter.addWidget(detail_widget_inner)

        layout.addWidget(splitter)

    def initializePage(self):
        matched = [r for r in self.project.match_results if r["matched"]]
        self.table.setRowCount(len(matched))
        for i, r in enumerate(matched):
            self.table.setItem(i, 0, QTableWidgetItem(str(r["row_index"])))
            self.table.setItem(i, 1, QTableWidgetItem(os.path.basename(r["file_path"])))
            status_item = QTableWidgetItem("待提取")
            self.table.setItem(i, 2, status_item)

    def _llm_settings(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("LLM 设置")
        layout = QFormLayout(dialog)

        url_input = QLineEdit(self.project.llm_config.get("base_url", "http://localhost:11434/v1"))
        url_input.setPlaceholderText("例如: https://api.openai.com/v1")
        layout.addRow("API 地址:", url_input)

        key_input = QLineEdit(self.project.llm_config.get("api_key", ""))
        key_input.setPlaceholderText("API Key（本地 Ollama 可不填）")
        layout.addRow("API Key:", key_input)

        model_input = QLineEdit(self.project.llm_config.get("model", "qwen2.5:7b"))
        model_input.setPlaceholderText("模型名称")
        layout.addRow("模型:", model_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            self.project.update_llm_config(url_input.text(), key_input.text(), model_input.text())
            self.llm_config_label.setText(f"✓ {model_input.text()}")

    def _start_extract(self):
        if not self.project.llm_config.get("base_url"):
            QMessageBox.warning(self, "提示", "请先配置 LLM")
            return

        matched = [r for r in self.project.match_results if r["matched"]]
        db_path = self.project.cache_db_path()
        ocr_cache = OcrCache(db_path)
        reader = ExcelReader(self.project.excel_path)
        df = reader.get_data()
        llm_client = LlmClient.from_config(self.project.llm_config)

        rows = []
        for r in matched:
            row_idx = r["row_index"]
            row_data = {str(k): str(v) for k, v in df.iloc[row_idx].items()}
            rows.append((row_idx, r["file_path"], row_data))

        extract_fields = [f for f in self.project.fields if f.selected and not f.is_context]
        context_names = [f.name for f in self.project.fields if f.is_context]

        self.worker = ExtractWorker(extract_fields, context_names, ocr_cache, llm_client, rows)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)

        self.extract_btn.setEnabled(False)
        self.worker.progress.connect(lambda c, t: self.status_label.setText(f"提取中: {c}/{t}"))
        self.worker.result_ready.connect(self._on_result)
        self.worker.finished.connect(self._on_extract_finished)

        self.thread.start()

    def _on_result(self, row_idx: int, data: dict):
        self.results[row_idx] = data
        # update table status
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).text() == str(row_idx):
                if "_error" in data:
                    self.table.setItem(i, 2, QTableWidgetItem(f"❌ {data.get('_error', '')}"))
                else:
                    self.table.setItem(i, 2, QTableWidgetItem("✅ 已提取"))
                break

    def _on_extract_finished(self):
        self.status_label.setText("提取完成")
        self.extract_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        QMessageBox.information(self, "完成", f"提取完成，共处理 {len(self.results)} 行")

    def _show_row_detail(self, item):
        row = item.row()
        row_idx_str = self.table.item(row, 0).text()
        if row_idx_str not in self.results:
            return

        data = self.results[row_idx_str]
        self.detail_table.setRowCount(0)

        for f in self.project.fields:
            if f.is_context or not f.selected:
                continue
            field_data = data.get(f.name, {})
            value = field_data.get("value", "")
            conf_str = field_data.get("confidence", "missing")
            try:
                conf = Confidence(conf_str)
            except ValueError:
                conf = Confidence.MISSING

            row_pos = self.detail_table.rowCount()
            self.detail_table.insertRow(row_pos)
            self.detail_table.setItem(row_pos, 0, QTableWidgetItem(f.name))
            self.detail_table.setItem(row_pos, 1, QTableWidgetItem(value))

            conf_widget = ConfidenceLabel(conf)
            self.detail_table.setCellWidget(row_pos, 2, conf_widget)

            edit_btn = QPushButton("修正")
            edit_btn.clicked.connect(lambda checked, r=row_pos, fn=f.name: self._edit_field(r, fn))
            self.detail_table.setCellWidget(row_pos, 3, edit_btn)

    def _edit_field(self, detail_row: int, field_name: str):
        from PySide6.QtWidgets import QInputDialog
        current = self.detail_table.item(detail_row, 1)
        value, ok = QInputDialog.getText(self, "修正值", f"修改 {field_name}:", text=current.text() if current else "")
        if ok:
            current.setText(value)
            for row_idx_str, data in self.results.items():
                if field_name in data:
                    data[field_name]["value"] = value

    def _export(self):
        if not self.results:
            QMessageBox.warning(self, "提示", "没有可导出的数据")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存 Excel", "output.xlsx", "Excel (*.xlsx)"
        )
        if not output_path:
            return

        extract_fields = [f for f in self.project.fields if f.selected and not f.is_context]
        field_names = [f.name for f in extract_fields]

        results_list = []
        for row_idx_str, data in self.results.items():
            row_idx = int(row_idx_str)
            frs = {}
            for fname in field_names:
                fd = data.get(fname, {})
                conf_str = fd.get("confidence", "missing")
                try:
                    conf = Confidence(conf_str)
                except ValueError:
                    conf = Confidence.MISSING
                frs[fname] = FieldResult(
                    value=fd.get("value", ""),
                    confidence=conf,
                )
            results_list.append(ExtractResult(
                row_index=row_idx,
                file_path="",
                fields=frs,
            ))

        try:
            writer = ExcelWriter(self.project.excel_path, output_path)
            start_col = len(field_names) + 1
            writer.write_results(results_list, field_names, start_col=start_col)
            QMessageBox.information(self, "成功", f"导出到: {output_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
