import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("Extractor for Excel")
    app.setOrganizationName("extractor-for-excel")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
