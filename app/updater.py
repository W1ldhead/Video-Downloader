"""Обновление yt-dlp без переустановки приложения.

Свежий yt-dlp скачивается с PyPI как .whl (это zip с чистым Python) в папку данных
приложения. При запуске, до первого import yt_dlp, activate() ставит этот файл
в начало sys.path, если он новее встроенной версии.
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
TIMEOUT = 30
_WHEEL = re.compile(r"^yt_dlp-([0-9.]+)-py3-none-any\.whl$")


def update_dir() -> Path:
    # Переменная окружения — только для проверок, чтобы не трогать настоящую папку
    override = os.environ.get("TIKTOKDL_UPDATE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "TikTokDownloader" / "yt-dlp"


def parse_version(text: str) -> tuple[int, ...]:
    """'2026.08.19' и '2026.8.19.1' → кортеж чисел для сравнения."""
    return tuple(int(p) for p in re.findall(r"\d+", text))


def bundled_version() -> str:
    """Версия yt-dlp, встроенная в приложение (без импорта самого yt_dlp)."""
    try:
        return metadata.version("yt-dlp")
    except metadata.PackageNotFoundError:
        return "0"


def downloaded_wheel() -> tuple[str, Path] | None:
    """Самый новый скачанный ранее yt-dlp: (версия, путь)."""
    folder = update_dir()
    if not folder.is_dir():
        return None
    best: tuple[str, Path] | None = None
    for path in folder.iterdir():
        m = _WHEEL.match(path.name)
        if m and (best is None or parse_version(m.group(1)) > parse_version(best[0])):
            best = (m.group(1), path)
    return best


def activate() -> None:
    """Вызывать до первого import yt_dlp."""
    if "yt_dlp" in sys.modules:
        return
    found = downloaded_wheel()
    if found and parse_version(found[0]) > parse_version(bundled_version()):
        sys.path.insert(0, str(found[1]))


def running_version() -> str:
    """Версия yt-dlp, которая работает сейчас."""
    from yt_dlp.version import __version__

    return __version__


class UpdateError(Exception):
    pass


def check_latest() -> tuple[str, str, str]:
    """Последняя версия на PyPI: (версия, ссылка на .whl, sha256)."""
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=TIMEOUT) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        raise UpdateError("Не удалось связаться с сервером обновлений. Проверьте интернет.") from e
    version = data["info"]["version"]
    for file in data.get("urls", []):
        if _WHEEL.match(file.get("filename", "")):
            return version, file["url"], file["digests"]["sha256"]
    raise UpdateError("На сервере не нашлось файла обновления.")


def install(version: str, url: str, sha256: str) -> Path:
    """Скачивает .whl, сверяет контрольную сумму, удаляет старые скачанные версии."""
    folder = update_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"yt_dlp-{version}-py3-none-any.whl"
    tmp = target.with_suffix(".tmp")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        raise UpdateError("Не удалось скачать обновление. Проверьте интернет.") from e
    if hashlib.sha256(data).hexdigest() != sha256:
        raise UpdateError("Файл обновления повреждён (не сошлась контрольная сумма).")
    tmp.write_bytes(data)
    tmp.replace(target)
    for old in folder.iterdir():
        if old != target and _WHEEL.match(old.name):
            try:
                old.unlink()
            except OSError:
                pass  # старый файл может быть занят текущим запуском — уберём в следующий раз
    return target


def update() -> tuple[str, bool]:
    """Проверить и при необходимости скачать. Возвращает (версия на PyPI, скачано ли новое)."""
    version, url, sha256 = check_latest()
    current = running_version()
    found = downloaded_wheel()
    newest_local = max(
        [current] + ([found[0]] if found else []), key=parse_version
    )
    if parse_version(version) <= parse_version(newest_local):
        return version, False
    install(version, url, sha256)
    return version, True
