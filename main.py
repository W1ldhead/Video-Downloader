"""Точка входа: запуск окна."""

import sys

from PySide6.QtWidgets import QApplication

from app.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TikTok Downloader")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
