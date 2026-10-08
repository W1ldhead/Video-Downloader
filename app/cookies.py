"""Файлы cookies.txt — вход в аккаунт, отдельно для каждой площадки.

Программа хранит копии файлов в своей папке данных и только читает их.
"""

import os
import shutil
import time
from pathlib import Path

from yt_dlp.cookies import YoutubeDLCookieJar

from app.links import INSTAGRAM, TIKTOK, X, YOUTUBE

# Домены площадки и cookies, по которым видно, что вход выполнен (хватит любого из них)
_SITES = {
    TIKTOK: (("tiktok.com",), ("sessionid",)),
    INSTAGRAM: (("instagram.com",), ("sessionid",)),
    X: (("x.com", "twitter.com"), ("auth_token",)),
    YOUTUBE: (("youtube.com", "google.com"), ("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID", "__Secure-1PSID")),
}


class CookieError(Exception):
    pass


def data_dir() -> Path:
    # Переменная окружения — только для проверок
    override = os.environ.get("TIKTOKDL_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "TikTokDownloader"


def stored_path(platform: str) -> Path:
    _migrate()
    return data_dir() / "cookies" / f"{platform}.txt"


def _migrate() -> None:
    """До шага 10 был один файл cookies.txt — он от TikTok."""
    old = data_dir() / "cookies.txt"
    if old.is_file():
        new = data_dir() / "cookies" / f"{TIKTOK}.txt"
        new.parent.mkdir(parents=True, exist_ok=True)
        if not new.exists():
            old.replace(new)
        else:
            old.unlink()


def is_set(platform: str | None) -> bool:
    return platform in _SITES and stored_path(platform).is_file()


def _on_site(domain: str, domains: tuple[str, ...]) -> bool:
    domain = domain.lstrip(".").lower()
    return any(domain == d or domain.endswith("." + d) for d in domains)


def check(path: Path, platform: str) -> str:
    """Проверяет файл. Возвращает предупреждение (или ""), при негодном файле — CookieError."""
    domains, login_names = _SITES[platform]
    jar = YoutubeDLCookieJar()
    try:
        jar.load(str(path))
    except Exception as e:  # noqa: BLE001
        raise CookieError(
            "Это не файл cookies.txt (формат Netscape). "
            "Сохраните его расширением «Get cookies.txt LOCALLY»."
        ) from e
    site = [c for c in jar if _on_site(c.domain, domains)]
    if not site:
        raise CookieError(
            f"В файле нет cookies {platform}. Откройте {domains[0]} в браузере "
            "и сохраните файл, находясь на этой странице."
        )
    login = [c for c in site if c.name in login_names]
    if not login:
        raise CookieError(
            f"В файле нет входа в аккаунт {platform}. Войдите в аккаунт в браузере и сохраните файл заново."
        )
    if all(c.expires and c.expires < time.time() for c in login):
        return "Вход в этом файле уже истёк — скорее всего, площадка его не примет. Сохраните файл заново."
    return ""


def install(path: Path, platform: str) -> str:
    """Проверяет и сохраняет копию. Возвращает предупреждение (или "")."""
    warning = check(path, platform)
    target = stored_path(platform)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    return warning


def remove(platform: str) -> None:
    stored_path(platform).unlink(missing_ok=True)
