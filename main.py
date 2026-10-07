"""Точка входа: запуск окна."""

import sys

from app import updater

# Свежий yt-dlp из папки обновлений — до того, как его кто-то импортирует
updater.activate()

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.window import MainWindow  # noqa: E402


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        from pathlib import Path

        from app import selftest

        return selftest.run(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)

    app = QApplication(sys.argv)
    app.setApplicationName("TikTok Downloader")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
