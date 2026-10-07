"""Точка входа: запуск окна."""

import sys

from app import updater

# Свежий yt-dlp из папки обновлений — до того, как его кто-то импортирует
updater.activate()

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TikTok Downloader")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
