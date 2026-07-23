from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from models.field import Confidence


CONF_COLORS = {
    Confidence.HIGH: QColor("#C6EFCE"),
    Confidence.MEDIUM: QColor("#FFEB9C"),
    Confidence.LOW: QColor("#FFC7CE"),
    Confidence.MISSING: QColor("#D9D9D9"),
}

CONF_TEXT = {
    Confidence.HIGH: "✓ 高",
    Confidence.MEDIUM: "~ 中",
    Confidence.LOW: "⚠ 低",
    Confidence.MISSING: "— 缺失",
}


class ConfidenceLabel(QLabel):
    def __init__(self, confidence: Confidence = Confidence.MISSING, parent=None):
        super().__init__(parent)
        self.set_conf(confidence)

    def set_conf(self, confidence: Confidence):
        self.setText(CONF_TEXT.get(confidence, "?"))
        color = CONF_COLORS.get(confidence, QColor("white"))
        self.setStyleSheet(
            f"background-color: {color.name()}; padding: 2px 6px; border-radius: 3px; font-weight: bold;"
        )
        self.setAlignment(Qt.AlignCenter)
