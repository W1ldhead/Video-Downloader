"""Скачивание одного видео TikTok через yt-dlp."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadError

# Статусы для интерфейса
FETCHING = "fetching"        # получение данных
DOWNLOADING = "downloading"  # скачивается
DONE = "done"                # готово
ALREADY = "already"          # уже скачано
ERROR = "error"              # ошибка
STOPPED = "stopped"          # остановлено пользователем


@dataclass
class VideoInfo:
    id: str
    author: str
    thumbnail: str | None


@dataclass
class Result:
    status: str
    path: Path | None = None
    message: str = ""


class _Stopped(Exception):
    """Загрузка прервана кнопкой «Остановить»."""


class _SilentLogger:
    """yt-dlp пишет ошибки в консоль сам; нам они нужны только в Result."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


_BASE_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "logger": _SilentLogger(),
    "fixup": "never",  # ffmpeg не нужен: у TikTok видео и звук в одном файле
}


def _ydl(extra: dict | None = None) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({**_BASE_OPTIONS, **(extra or {})})


def pick_format(formats: list[dict]) -> dict | None:
    """Лучшая версия без водяного знака или None, если такой нет."""
    good = []
    for f in formats:
        note = (f.get("format_note") or "").lower()
        if "watermark" in note or "unplayable" in note:
            continue
        if f.get("vcodec") in (None, "none") or f.get("acodec") == "none":
            continue  # только звук или только картинка
        good.append(f)
    if not good:
        return None
    # h264 открывается везде; среди одинаковых — выше качество и битрейт
    return max(
        good,
        key=lambda f: (
            (f.get("vcodec") or "").startswith(("h264", "avc")),
            f.get("height") or 0,
            f.get("tbr") or 0,
            f.get("filesize") or 0,
        ),
    )


def safe_name(text: str) -> str:
    """Убирает знаки, запрещённые в именах файлов Windows."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip().rstrip(". ")
    return text or "unknown"


def file_path(folder: Path, author: str, video_id: str) -> Path:
    return folder / f"{safe_name(author)}_{safe_name(video_id)}.mp4"


def explain(error: Exception) -> str:
    """Короткая понятная причина ошибки."""
    text = str(error)
    rules = [
        ("IP address is blocked", "Видео недоступно в вашем регионе"),
        ("private", "Видео закрыто автором"),
        ("not available", "Видео удалено или недоступно"),
        ("status code 10204", "Видео удалено или недоступно"),
        ("Unsupported URL", "Ссылка не ведёт на видео (возможно, оно удалено)"),
        ("Unexpected response", "TikTok ответил не так, как ожидалось. Попробуйте «Обновить загрузчик»"),
        ("Unable to extract", "TikTok ответил не так, как ожидалось. Попробуйте «Обновить загрузчик»"),
        ("getaddrinfo", "Нет подключения к интернету"),
        ("timed out", "Сервер не отвечает, попробуйте ещё раз"),
        ("No space left", "На диске не хватает места"),
        ("Permission denied", "Нет доступа к папке"),
    ]
    low = text.lower()
    for needle, message in rules:
        if needle.lower() in low:
            return message
    # Неизвестная ошибка — первая строка без служебного префикса
    first = text.splitlines()[0] if text else type(error).__name__
    first = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?(\S+:\s*)?", "", first)
    return first[:150]


def fetch_info(url: str) -> tuple[VideoInfo, dict]:
    """Данные о видео без скачивания: (кратко для интерфейса, полный ответ yt-dlp)."""
    with _ydl() as ydl:
        info = ydl.extract_info(url, download=False)
    video = VideoInfo(
        id=str(info.get("id") or ""),
        author=info.get("uploader") or info.get("channel") or "unknown",
        thumbnail=info.get("thumbnail"),
    )
    return video, info


def download(
    url: str,
    folder: Path,
    on_info: Callable[[VideoInfo], None] = lambda v: None,
    on_progress: Callable[[int, int | None], None] = lambda done, total: None,
    should_stop: Callable[[], bool] = lambda: False,
) -> Result:
    """Скачивает одно видео. Исключений наружу не бросает — всё в Result."""
    target: Path | None = None
    try:
        video, info = fetch_info(url)
        on_info(video)
        if should_stop():
            return Result(STOPPED)

        fmt = pick_format(info.get("formats") or [])
        if fmt is None:
            return Result(ERROR, message="Нет версии без водяного знака")

        target = file_path(folder, video.author, video.id)
        if target.exists():
            return Result(ALREADY, target)
        folder.mkdir(parents=True, exist_ok=True)

        def hook(d: dict) -> None:
            if should_stop():
                raise _Stopped()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                on_progress(int(d.get("downloaded_bytes") or 0), int(total) if total else None)

        options = {
            "format": fmt["format_id"],
            # % в пути yt-dlp понимает как шаблон — экранируем
            "outtmpl": {"default": str(target).replace("%", "%%")},
            "progress_hooks": [hook],
            "overwrites": False,
        }
        with _ydl(options) as ydl:
            ydl.process_ie_result(info, download=True)

        if not target.exists():
            return Result(ERROR, message="Файл не появился после скачивания")
        return Result(DONE, target)

    except _Stopped:
        _cleanup(target)
        return Result(STOPPED)
    except DownloadError as e:
        # yt-dlp заворачивает исключения из хука в DownloadError
        if isinstance(getattr(e, "exc_info", (None, None))[1], _Stopped):
            _cleanup(target)
            return Result(STOPPED)
        _cleanup(target)
        return Result(ERROR, message=explain(e))
    except Exception as e:  # noqa: BLE001 — ошибка одной ссылки не должна ронять остальные
        _cleanup(target)
        return Result(ERROR, message=explain(e))


def _cleanup(target: Path | None) -> None:
    """Удаляет недокачанные куски файла."""
    if target is None:
        return
    for leftover in target.parent.glob(target.name + "*.part*"):
        leftover.unlink(missing_ok=True)
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
