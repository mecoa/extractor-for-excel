import os
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView,
    QMessageBox, QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QObject
from core.ocr.mineru_engine import create_engine
from core.ocr.cache import OcrCache
from models.ocr_cache import OcrCacheEntry, OcrStatus


class OcrWorker(QObject):
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, ocr_cache, engine, file_paths):
        super().__init__()
        self.ocr_cache = ocr_cache
        self.engine = engine
        self.file_paths = file_paths

    def run(self):
        total = len(self.file_paths)
        for i, fp in enumerate(self.file_paths):
            try:
                entry = self.ocr_cache.get(fp)
                if entry and entry.status == OcrStatus.DONE:
                    self.progress.emit(i + 1, total)
                    continue

                self.ocr_cache.update_status(fp, OcrStatus.PROCESSING)
                result = self.engine.parse(fp)
                if result.error:
                    entry = OcrCacheEntry(fp, os.path.basename(fp), OcrStatus.FAILED, error=result.error)
                else:
                    entry = OcrCacheEntry(
                        fp, os.path.basename(fp), OcrStatus.DONE,
                        markdown=result.markdown, raw_data=result.raw_data,
                        page_count=result.page_count,
                    )
                self.ocr_cache.put(entry)
            except Exception as e:
                self.ocr_cache.put(OcrCacheEntry(fp, os.path.basename(fp), OcrStatus.FAILED, error=str(e)))
            self.progress.emit(i + 1, total)
        self.finished.emit()


class ImportPage(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)

        title = QLabel("导入 & OCR")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 4px;")
        layout.addWidget(title)
        subtitle = QLabel("批量导入 PDF，通过 MinerU 云端解析并缓存结果，支持离线查看")
        subtitle.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("开始导入并 OCR")
        self.import_btn.clicked.connect(self._start_ocr)
        self.import_btn.setStyleSheet("background-color: #0078D4; color: white; padding: 8px; font-weight: bold;")
        self.settings_btn = QPushButton("MinerU 设置")
        self.settings_btn.clicked.connect(self._mineru_settings)
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.settings_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #888; margin: 4px 0;")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["行号", "文件名", "状态", "页数", "错误信息"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.preview_label = QLabel("OCR 文本预览（点击行查看）")
        layout.addWidget(self.preview_label)
        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setMaximumHeight(150)
        layout.addWidget(self.preview_box)

        self.table.itemClicked.connect(self._show_preview)

    def initializePage(self):
        self._refresh_table()

    def _refresh_table(self):
        matched = [r for r in self.project.match_results if r["matched"]]
        self.table.setRowCount(len(matched))
        for i, r in enumerate(matched):
            self.table.setItem(i, 0, QTableWidgetItem(str(r["row_index"])))
            self.table.setItem(i, 1, QTableWidgetItem(os.path.basename(r["file_path"])))

            db_path = self.project.cache_db_path()
            if db_path and os.path.exists(db_path):
                cache = OcrCache(db_path)
                entry = cache.get(r["file_path"])
                if entry:
                    self.table.setItem(i, 2, QTableWidgetItem(entry.status.value))
                    self.table.setItem(i, 3, QTableWidgetItem(str(entry.page_count)))
                    self.table.setItem(i, 4, QTableWidgetItem(entry.error or ""))
                else:
                    self.table.setItem(i, 2, QTableWidgetItem("pending"))
                cache.close()
            else:
                self.table.setItem(i, 2, QTableWidgetItem("pending"))

    def _start_ocr(self):
        matched = [r for r in self.project.match_results if r["matched"]]
        file_paths = [r["file_path"] for r in matched]

        if not file_paths:
            QMessageBox.warning(self, "提示", "没有匹配的 PDF 文件")
            return

        db_path = self.project.cache_db_path()
        if not db_path:
            QMessageBox.warning(self, "提示", "请先保存项目")
            return

        ocr_cache = OcrCache(db_path)
        engine = create_engine(
            token=self.project.mineru_token,
            use_precision=self.project.mineru_precision,
        )

        self.worker = OcrWorker(ocr_cache, engine, file_paths)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)

        self.import_btn.setEnabled(False)
        self.worker.progress.connect(lambda c, t: self.progress.setValue(int(c / t * 100)))
        self.worker.finished.connect(lambda: self.import_btn.setEnabled(True))
        self.worker.finished.connect(self._refresh_table)

        self.thread.start()

    def _on_progress(self, current, total):
        self.progress.setValue(int(current / total * 100))
        self.status_label.setText(f"正在 OCR: {current}/{total}")

    def _on_finished(self):
        self.status_label.setText("OCR 完成")
        self.import_btn.setEnabled(True)

    def _show_preview(self, item):
        row = item.row()
        file_path_item = self.table.item(row, 1)
        if not file_path_item:
            return
        db_path = self.project.cache_db_path()
        if not db_path:
            return
        cache = OcrCache(db_path)
        matched = [r for r in self.project.match_results if r["matched"]]
        if row < len(matched):
            entry = cache.get(matched[row]["file_path"])
            if entry and entry.markdown:
                self.preview_box.setText(entry.markdown[:2000])
            elif entry and entry.error:
                self.preview_box.setText(f"错误: {entry.error}")
            else:
                self.preview_box.setText("等待处理")
        cache.close()

    def _mineru_settings(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("MinerU 设置")
        layout = QFormLayout(dialog)

        token_input = QLineEdit(self.project.mineru_token)
        token_input.setPlaceholderText("留空使用 Agent 模式（免 Token，限 20 页）")
        layout.addRow("API Token:", token_input)

        precision_cb = QCheckBox("使用精准模式（需 Token）")
        precision_cb.setChecked(self.project.mineru_precision)
        layout.addRow(precision_cb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            self.project.mineru_token = token_input.text()
            self.project.mineru_precision = precision_cb.isChecked()
