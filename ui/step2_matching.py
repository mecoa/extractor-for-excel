import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QLabel,
    QHeaderView, QMessageBox, QLineEdit, QListWidget,
    QListWidgetItem, QGroupBox, QAbstractItemView,
)
from PySide6.QtCore import Qt
from core.matcher import FilenameMatcher
from core.excel.reader import ExcelReader
from models.field import MatchRule


class MatchingPage(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._match_results = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)

        title = QLabel("文件名匹配规则")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 4px;")
        layout.addWidget(title)
        subtitle = QLabel("选择用于文件匹配的字段，用广播语法编写文件名模板，与 PDF 文件自动匹配")
        subtitle.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        hints = QLabel("提示：在 Step 1 中勾选「使用」且未标记为「已有值参考」的字段会出现在这里")
        hints.setStyleSheet("font-size: 11px; color: #999; margin-bottom: 8px;")
        layout.addWidget(hints)

        field_group = QGroupBox("匹配字段选择")
        fg_layout = QVBoxLayout(field_group)
        self.field_list = QListWidget()
        self.field_list.setSelectionMode(QAbstractItemView.MultiSelection)
        fg_layout.addWidget(self.field_list)
        layout.addWidget(field_group)

        pattern_group = QGroupBox("文件名模板")
        pg_layout = QHBoxLayout(pattern_group)
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText('例如: {年}-{月}-{号}#')
        self.preview_btn = QPushButton("预览匹配")
        self.preview_btn.clicked.connect(self._preview_match)
        pg_layout.addWidget(QLabel("模板:"))
        pg_layout.addWidget(self.pattern_input)
        pg_layout.addWidget(self.preview_btn)
        layout.addWidget(pattern_group)

        folder_layout = QHBoxLayout()
        self.folder_btn = QPushButton("选择 PDF 文件夹")
        self.folder_btn.clicked.connect(self._select_folder)
        self.folder_label = QLabel("未选择文件夹")
        folder_layout.addWidget(self.folder_btn)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addStretch()
        layout.addLayout(folder_layout)

        select_row = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        self.select_none_btn = QPushButton("反选")
        self.select_none_btn.clicked.connect(lambda: self._toggle_all(None))
        select_row.addWidget(QLabel("选择要处理的行:"))
        select_row.addWidget(self.select_all_btn)
        select_row.addWidget(self.select_none_btn)
        select_row.addStretch()
        layout.addLayout(select_row)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(["", "行号", "生成文件名", "匹配状态", "文件路径"])
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.result_table.setColumnWidth(0, 30)
        layout.addWidget(self.result_table)

        self.selected_indices: set = set()

    def initializePage(self):
        self.field_list.clear()
        for f in self.project.fields:
            if f.selected and not f.is_context:
                item = QListWidgetItem(f.name)
                item.setData(Qt.UserRole, f.name)
                self.field_list.addItem(item)

        if self.project.match_rule.pattern:
            self.pattern_input.setText(self.project.match_rule.pattern)
        if self.project.match_rule.pdf_folder:
            self.folder_label.setText(self.project.match_rule.pdf_folder)

        self.selected_indices = set(self.project.selected_rows)

    def _select_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择 PDF 文件夹")
        if path:
            self.project.pdf_folder = path
            self.project.match_rule.pdf_folder = path
            self.folder_label.setText(path)

    def _preview_match(self):
        if not self.project.excel_path:
            QMessageBox.warning(self, "提示", "请先在 Step 1 中打开 Excel")
            return
        if not os.path.isdir(self.project.pdf_folder):
            QMessageBox.warning(self, "提示", "请先选择有效的 PDF 文件夹")
            return

        pattern = self.pattern_input.text()
        if not pattern:
            QMessageBox.warning(self, "提示", "请填写文件名模板")
            return

        selected = [item.data(Qt.UserRole) for item in self.field_list.selectedItems()]
        if not selected:
            QMessageBox.warning(self, "提示", "请选择至少一个匹配字段")
            return

        self.project.match_rule.pattern = pattern
        self.project.match_rule.match_fields = selected

        reader = ExcelReader(self.project.excel_path)
        matcher = FilenameMatcher(self.project.match_rule)
        self._match_results = matcher.match(reader.get_data())
        self.project.match_results = self._match_results
        self._show_results()

    def _show_results(self):
        self.result_table.setRowCount(len(self._match_results))
        for i, r in enumerate(self._match_results):
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cb.setCheckState(Qt.Checked if i in self.selected_indices else Qt.Unchecked)
            self.result_table.setItem(i, 0, cb)

            self.result_table.setItem(i, 1, QTableWidgetItem(str(r["row_index"])))
            self.result_table.setItem(i, 2, QTableWidgetItem(r["generated"]))
            status = "✅ 已匹配" if r["matched"] else "❌ 未匹配"
            self.result_table.setItem(i, 3, QTableWidgetItem(status))
            self.result_table.setItem(i, 4, QTableWidgetItem(r["file_path"]))

    def _toggle_all(self, state: bool | None):
        for i in range(self.result_table.rowCount()):
            if state is None:
                cur = self.result_table.item(i, 0).checkState()
                new = Qt.Unchecked if cur == Qt.Checked else Qt.Checked
            else:
                new = Qt.Checked if state else Qt.Unchecked
            self.result_table.item(i, 0).setCheckState(new)

    def collect_selected(self) -> list[int]:
        rows = []
        for i in range(self.result_table.rowCount()):
            if self.result_table.item(i, 0) and self.result_table.item(i, 0).checkState() == Qt.Checked:
                try:
                    rows.append(int(self.result_table.item(i, 1).text()))
                except (ValueError, AttributeError):
                    pass
        self.project.selected_rows = rows
        return rows

    @property
    def match_results(self):
        return self.project.match_results
