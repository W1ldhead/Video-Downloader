"""Настройки, которые помнятся между запусками (реестр Windows, раздел текущего пользователя)."""

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

_ORG = "TikTokDownloader"
_APP = "TikTokDownloader"


def _store() -> QSettings:
    return QSettings(_ORG, _APP)


def default_folder() -> Path:
    """Загрузки\\Video Downloader (внутри — подпапки площадок)."""
    downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    base = Path(downloads) if downloads else Path.home() / "Downloads"
    return base / "Video Downloader"


def load_folder() -> Path:
    value = _store().value("folder", "", type=str)
    return Path(value) if value else default_folder()


def save_folder(folder: Path) -> None:
    _store().setValue("folder", str(folder))
