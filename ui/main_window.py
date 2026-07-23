import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFileDialog,
    QMessageBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from core.project import Project
from .step1_template import TemplatePage
from .step2_matching import MatchingPage
from .step3_import import ImportPage
from .step4_review import ReviewPage


STEP_LABELS = ["Excel 配置", "文件匹配", "导入 OCR", "提取导出"]


class StepIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self.setFixedHeight(80)

    def set_step(self, step: int):
        self._current = step
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        n = len(STEP_LABELS)
        spacing = w // (n + 1)
        circle_r = 14

        for i, label in enumerate(STEP_LABELS):
            cx = spacing * (i + 1)

            # connector line
            if i > 0:
                prev_x = spacing * i
                color = QColor("#4A90D9") if i <= self._current else QColor("#D0D0D0")
                p.setPen(QPen(color, 3))
                p.drawLine(prev_x + circle_r, 40, cx - circle_r, 40)

            # circle
            if i < self._current:
                color = QColor("#4A90D9")
                p.setBrush(color)
                p.setPen(Qt.NoPen)
                p.drawEllipse(cx - circle_r, 40 - circle_r, circle_r * 2, circle_r * 2)
                p.setPen(QPen(Qt.white, 2))
                p.drawText(cx - 5, 40 + 5, str(i + 1))
            elif i == self._current:
                color = QColor("#4A90D9")
                p.setBrush(Qt.white)
                p.setPen(QPen(color, 3))
                p.drawEllipse(cx - circle_r, 40 - circle_r, circle_r * 2, circle_r * 2)
                p.setPen(color)
                p.drawText(cx - 5, 40 + 5, str(i + 1))
            else:
                p.setBrush(QColor("#E0E0E0"))
                p.setPen(QPen(QColor("#B0B0B0"), 2))
                p.drawEllipse(cx - circle_r, 40 - circle_r, circle_r * 2, circle_r * 2)
                p.setPen(QColor("#B0B0B0"))
                p.drawText(cx - 5, 40 + 5, str(i + 1))

            # label
            p.setPen(QColor("#333333") if i <= self._current else QColor("#999999"))
            label_font = QFont("Segoe UI", 10)
            p.setFont(label_font)
            p.drawText(cx - 50, 70, 100, 20, Qt.AlignCenter, label)

        p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.setWindowTitle("Extractor for Excel")
        self.resize(1100, 750)

        self._setup_ui()
        self._setup_menus()

    def _setup_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("新建项目", self._new_project)
        file_menu.addAction("打开项目", self._open_project)
        file_menu.addAction("保存项目", self._save_project)
        file_menu.addAction("另存为...", self._save_as_project)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        help_menu = menubar.addMenu("帮助")
        help_menu.addAction("关于", lambda: QMessageBox.about(self, "关于", "Extractor for Excel v0.1\nAI 驱动的文档 → Excel 提取工具"))

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.step_indicator = StepIndicator()
        self.step_indicator.setStyleSheet("background: #FAFAFA; border-bottom: 1px solid #E0E0E0;")
        root.addWidget(self.step_indicator)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: white;")
        root.addWidget(self.stack, 1)

        self.pages = [
            TemplatePage(self.project),
            MatchingPage(self.project),
            ImportPage(self.project),
            ReviewPage(self.project),
        ]
        for p in self.pages:
            self.stack.addWidget(p)

        nav_bar = QFrame()
        nav_bar.setStyleSheet("background: #FAFAFA; border-top: 1px solid #E0E0E0; padding: 8px;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(16, 8, 16, 8)

        self.back_btn = QPushButton("← 上一步")
        self.back_btn.setObjectName("nav_back")
        self.back_btn.clicked.connect(self._go_back)
        self.next_btn = QPushButton("下一步 →")
        self.next_btn.setObjectName("nav_next")
        self.next_btn.clicked.connect(self._go_next)

        nav_layout.addWidget(self.back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)
        root.addWidget(nav_bar)

        self._update_nav()
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #F5F5F5; }
            QPushButton#nav_back {
                padding: 8px 24px; border: 1px solid #CCCCCC;
                border-radius: 6px; background: white; color: #333;
                font-size: 13px; min-width: 100px;
            }
            QPushButton#nav_back:hover { background: #F0F0F0; }
            QPushButton#nav_next {
                padding: 8px 24px; border: none;
                border-radius: 6px; background: #4A90D9; color: white;
                font-size: 13px; font-weight: bold; min-width: 100px;
            }
            QPushButton#nav_next:hover { background: #357ABD; }
            QPushButton#nav_next:disabled { background: #B0C4DE; }
            QPushButton { font-size: 13px; }
            QLabel { font-size: 13px; }
            QTableWidget {
                border: 1px solid #E0E0E0; border-radius: 4px;
                gridline-color: #F0F0F0; font-size: 13px;
            }
            QTableWidget::item { padding: 4px 8px; }
            QHeaderView::section {
                background: #FAFAFA; border: none;
                border-bottom: 2px solid #E0E0E0;
                padding: 8px; font-weight: bold; font-size: 13px;
            }
            QLineEdit {
                border: 1px solid #D0D0D0; border-radius: 4px;
                padding: 6px 10px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #4A90D9; }
            QPushButton { border-radius: 4px; padding: 6px 16px; }
            QGroupBox {
                font-weight: bold; border: 1px solid #E0E0E0;
                border-radius: 6px; margin-top: 12px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 8px; color: #555;
            }
        """)

    def _update_nav(self):
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        if idx == len(self.pages) - 1:
            self.next_btn.setText("完成")
        else:
            self.next_btn.setText("下一步 →")
        self.step_indicator.set_step(idx)

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_nav()

    def _go_next(self):
        idx = self.stack.currentIndex()

        if idx == 0:
            if not self.project.excel_path:
                QMessageBox.warning(self, "提示", "请先打开一个 Excel 文件")
                return
            self.project.fields = self.pages[0].collect_fields()
        elif idx == 1:
            if not self.project.match_results:
                QMessageBox.warning(self, "提示", "请先在「文件匹配」页面执行预览匹配")
                return
            if not self.project.match_rule.pattern:
                QMessageBox.warning(self, "提示", "请填写文件名模板")
                return

        if idx == len(self.pages) - 1:
            self._save_project()
            return

        self.stack.setCurrentIndex(idx + 1)
        next_page = self.pages[idx + 1]
        if hasattr(next_page, 'initializePage'):
            next_page.initializePage()
        self._update_nav()

    def _new_project(self):
        self.project = Project()
        for p in self.pages:
            p.project = self.project
        self.stack.setCurrentIndex(0)
        self._update_nav()
        self.setWindowTitle("Extractor for Excel - 新建项目")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "Project (*.json)")
        if not path:
            return
        try:
            self.project = Project.from_path(path)
            for p in self.pages:
                p.project = self.project
            self.stack.setCurrentIndex(0)
            self._update_nav()
            self.setWindowTitle(f"Extractor for Excel - {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开项目失败:\n{e}")

    def _save_project(self):
        if self.project.path:
            self._sync_project()
            self.project.save()
        else:
            self._save_as_project()

    def _save_as_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", "", "Project (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self.project.path = path
        self._sync_project()
        self.project.save()
        self.setWindowTitle(f"Extractor for Excel - {os.path.basename(path)}")

    def _sync_project(self):
        self.project.fields = self.pages[0].collect_fields()
