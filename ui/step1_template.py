import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QLabel,
    QHeaderView, QMessageBox, QLineEdit, QCheckBox,
)
from PySide6.QtCore import Qt
from models.field import FieldDef
from core.excel.reader import ExcelReader


class TemplatePage(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)

        title = QLabel("Excel 模板配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 4px;")
        layout.addWidget(title)
        subtitle = QLabel("选择要提取的字段，填写字段说明和示例值（将作为 LLM 提示词）")
        subtitle.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        top = QHBoxLayout()
        self.open_btn = QPushButton("打开 Excel 文件")
        self.open_btn.clicked.connect(self._open_excel)
        self.file_label = QLabel("未选择文件")
        top.addWidget(self.open_btn)
        top.addWidget(self.file_label)
        top.addStretch()
        layout.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["使用", "字段名", "字段说明 (→ LLM)", "示例值", "注入上下文"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)

    def _open_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 模板", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            reader = ExcelReader(path)
            self.project.excel_path = path
            self.file_label.setText(os.path.basename(path))
            self._populate_table(reader.headers)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取 Excel 失败:\n{e}")

    def _populate_table(self, headers: list[str]):
        self.table.setRowCount(len(headers))
        for i, h in enumerate(headers):
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cb.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, cb)

            self.table.setItem(i, 1, QTableWidgetItem(h))

            annot = QTableWidgetItem("")
            self.table.setItem(i, 2, annot)

            examples = QTableWidgetItem("")
            self.table.setItem(i, 3, examples)

            ctx = QTableWidgetItem()
            ctx.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            ctx.setCheckState(Qt.Unchecked)
            self.table.setItem(i, 4, ctx)

    def collect_fields(self) -> list[FieldDef]:
        fields = []
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).checkState() != Qt.Checked:
                continue
            name = self.table.item(i, 1).text()
            annotation = self.table.item(i, 2).text()
            examples_raw = self.table.item(i, 3).text()
            examples = [e.strip() for e in examples_raw.split("、") if e.strip()]
            is_context = self.table.item(i, 4).checkState() == Qt.Checked
            fields.append(FieldDef(
                name=name,
                annotation=annotation,
                examples=examples,
                is_context=is_context,
                selected=True,
            ))
        return fields

    def validate(self) -> bool:
        if not self.project.excel_path:
            QMessageBox.warning(self, "提示", "请先打开一个 Excel 文件")
            return False
        self.project.fields = self.collect_fields()
        return True
