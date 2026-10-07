"""Файл cookies.txt — вход в аккаунт TikTok для видео с ограничением по возрасту.

Программа хранит копию файла в своей папке данных и только читает её.
"""

import os
import shutil
import time
from pathlib import Path

from yt_dlp.cookies import YoutubeDLCookieJar


class CookieError(Exception):
    pass


def data_dir() -> Path:
    # Переменная окружения — только для проверок
    override = os.environ.get("TIKTOKDL_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "TikTokDownloader"


def stored_path() -> Path:
    return data_dir() / "cookies.txt"


def is_set() -> bool:
    return stored_path().is_file()


def check(path: Path) -> str:
    """Проверяет файл. Возвращает предупреждение (или ""), при негодном файле — CookieError."""
    jar = YoutubeDLCookieJar()
    try:
        jar.load(str(path))
    except Exception as e:  # noqa: BLE001
        raise CookieError(
            "Это не файл cookies.txt (формат Netscape). "
            "Сохраните его расширением «Get cookies.txt LOCALLY»."
        ) from e
    tiktok = [c for c in jar if c.domain.lstrip(".").endswith("tiktok.com")]
    if not tiktok:
        raise CookieError(
            "В файле нет cookies TikTok. Откройте tiktok.com в браузере и сохраните файл на этой странице."
        )
    session = [c for c in tiktok if c.name == "sessionid"]
    if not session:
        raise CookieError(
            "В файле нет входа в аккаунт. Войдите в TikTok в браузере и сохраните файл заново."
        )
    if all(c.expires and c.expires < time.time() for c in session):
        return "Вход в этом файле уже истёк — скорее всего, TikTok его не примет. Сохраните файл заново."
    return ""


def install(path: Path) -> str:
    """Проверяет и сохраняет копию. Возвращает предупреждение (или "")."""
    warning = check(path)
    target = stored_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    return warning


def remove() -> None:
    stored_path().unlink(missing_ok=True)
