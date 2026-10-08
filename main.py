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

        url = sys.argv[3] if len(sys.argv) > 3 else None
        folder = Path(sys.argv[4]) if len(sys.argv) > 4 else None
        return selftest.run(Path(sys.argv[2]), url, folder)

    app = QApplication(sys.argv)
    app.setApplicationName("Video Downloader")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
