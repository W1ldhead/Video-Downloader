"""Настройки, которые помнятся между запусками (реестр Windows, раздел текущего пользователя)."""

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from app import config

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


def load_quality() -> int:
    """Качество YouTube — высота кадра (0 — максимальное)."""
    value = _store().value("youtube_quality", config.YOUTUBE_DEFAULT_QUALITY, type=int)
    allowed = {height for _, height in config.YOUTUBE_QUALITIES}
    return value if value in allowed else config.YOUTUBE_DEFAULT_QUALITY


def save_quality(height: int) -> None:
    _store().setValue("youtube_quality", height)
