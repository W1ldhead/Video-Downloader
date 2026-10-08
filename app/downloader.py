"""Скачивание видео по одной ссылке через yt-dlp (в посте может быть несколько видео)."""

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadError

from app import cookies
from app.links import TIKTOK, X, platform_of

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
    count: int = 1  # сколько видео в посте


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
    "fixup": "never",  # ffmpeg не нужен: выбираем файлы, где видео и звук вместе
    "color": {"stdout": "never", "stderr": "never"},  # без кодов цвета в тексте ошибок
}

# Если готового файла со звуком нет — пусть yt-dlp склеит лучшие картинку и звук (нужен ffmpeg)
_MERGE_FORMAT = "bv*+ba/b"


def _ydl(extra: dict | None = None) -> yt_dlp.YoutubeDL:
    ydl = yt_dlp.YoutubeDL({**_BASE_OPTIONS, **(extra or {})})
    # Cookies грузим вручную, а не через "cookiefile": тогда yt-dlp не перезаписывает файл
    if cookies.is_set():
        ydl.cookiejar.load(str(cookies.stored_path()))
    return ydl


def _platform(url: str) -> str | None:
    try:
        return platform_of(url)
    except ValueError:
        return None


def pick_format(formats: list[dict], platform: str | None = TIKTOK) -> dict | None:
    """Лучший готовый файл с картинкой и звуком (у TikTok — без водяного знака) или None."""
    good = []
    for f in formats:
        note = (f.get("format_note") or "").lower()
        if "unplayable" in note:
            continue
        if platform == TIKTOK and "watermark" in note:
            continue
        # «none» — точно нет; None — yt-dlp не знает (у X так подписаны обычные mp4)
        if f.get("vcodec") == "none" or f.get("acodec") == "none":
            continue
        good.append(f)
    if not good:
        return None
    return max(
        good,
        key=lambda f: (
            "m3u8" not in (f.get("protocol") or ""),  # поток кусками хуже цельного файла
            (f.get("vcodec") or "avc").startswith(("h264", "avc")),  # h264 открывается везде
            f.get("height") or 0,
            f.get("tbr") or 0,
            f.get("filesize") or 0,
        ),
    )


def safe_name(text: str) -> str:
    """Убирает знаки, запрещённые в именах файлов Windows."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip().rstrip(". ")
    return text or "unknown"


def file_path(folder: Path, author: str, video_id: str, number: int | None = None) -> Path:
    suffix = f"_{number}" if number else ""
    return folder / f"{safe_name(author)}_{safe_name(video_id)}{suffix}.mp4"


def explain(error: Exception) -> str:
    """Короткая понятная причина ошибки."""
    # yt-dlp раскрашивает текст для терминала — убираем коды цвета
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    if "log in for access" in text.lower():
        if cookies.is_set():
            return ("Видео 18+: TikTok не принял вход. Файл cookies устарел или в аккаунте "
                    "не подтверждён возраст — сохраните файл заново")
        return "Видео 18+: нужен вход в аккаунт. Укажите файл cookies в меню «Загрузчик»"
    rules = [
        # X (Twitter)
        ("NSFW tweet requires authentication", "Пост с деликатным содержимым: X показывает его только после входа в аккаунт"),
        ("protected tweet", "Аккаунт закрыт: пост видят только подписчики"),
        ("No video could be found in this tweet", "В посте нет видео"),
        ("tweet is unavailable", "Пост удалён или недоступен"),
        ("suspended", "Аккаунт заблокирован"),
        # Общие
        ("ffmpeg", "Для этого видео нужен ffmpeg"),
        ("IP address is blocked", "Видео недоступно в вашем регионе"),
        ("private", "Видео закрыто автором"),
        ("not available", "Видео удалено или недоступно"),
        ("status code 10204", "Видео удалено или недоступно"),
        ("Unsupported URL", "Ссылка не ведёт на видео (возможно, оно удалено)"),
        ("Unexpected response", "Сайт ответил не так, как ожидалось. Попробуйте «Обновить загрузчик»"),
        ("Unable to extract", "Сайт ответил не так, как ожидалось. Попробуйте «Обновить загрузчик»"),
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


def _entries(info: dict) -> list[dict]:
    """Видео поста: у плейлиста — его элементы, иначе само видео."""
    if info.get("_type") == "playlist" or info.get("entries") is not None:
        return [e for e in (info.get("entries") or []) if e]
    return [info]


def _author(info: dict, platform: str | None) -> str:
    if platform == X:
        # У X uploader — отображаемое имя с пробелами и эмодзи, ник надёжнее
        return info.get("uploader_id") or info.get("uploader") or "unknown"
    return info.get("uploader") or info.get("uploader_id") or info.get("channel") or "unknown"


def _post_id(url: str, info: dict, platform: str | None) -> str:
    if platform == X:
        # У видео в X свой номер, а пользователь видит номер поста — берём его из ссылки
        m = re.search(r"/status/(\d+)", url)
        if m:
            return m.group(1)
    return str(info.get("id") or "")


def _thumbnail(info: dict) -> str | None:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = [t.get("url") for t in info.get("thumbnails") or [] if t.get("url")]
    return thumbs[-1] if thumbs else None  # последняя обычно самая крупная


def fetch_info(url: str) -> tuple[VideoInfo, dict]:
    """Данные о видео без скачивания: (кратко для интерфейса, «сырой» ответ yt-dlp).

    process=False: yt-dlp не выбирает формат сам. Иначе в ответе остаются ссылки
    его выбора, и при скачивании другого формата он берёт их (у X это давало 404).
    """
    platform = _platform(url)
    with _ydl() as ydl:
        info = ydl.extract_info(url, download=False, process=False)
    if info.get("entries") is not None:
        info["entries"] = [e for e in info["entries"] if e]  # бывает «ленивым» списком
    entries = _entries(info)
    first = entries[0] if entries else info
    video = VideoInfo(
        id=_post_id(url, info, platform),
        author=_author(info, platform),
        thumbnail=_thumbnail(info) or _thumbnail(first),
        count=len(entries),
    )
    return video, info


def _format_selector(platform: str | None):
    """Функция выбора формата для yt-dlp: наш выбор, а если готового файла нет — склейка."""
    with _ydl() as ydl:
        merge = ydl.build_format_selector(_MERGE_FORMAT)

    def select(ctx: dict):
        fmt = pick_format(ctx["formats"], platform)
        if fmt is not None:
            yield fmt
        elif platform != TIKTOK:
            yield from merge(ctx)
        # у TikTok без чистой версии не выбираем ничего — yt-dlp сообщит об ошибке

    return select


def download(
    url: str,
    folder: Path,
    on_info: Callable[[VideoInfo], None] = lambda v: None,
    on_progress: Callable[[int, int | None], None] = lambda done, total: None,
    should_stop: Callable[[], bool] = lambda: False,
    on_part: Callable[[int, int], None] = lambda number, count: None,
) -> Result:
    """Скачивает все видео по ссылке. Исключений наружу не бросает — всё в Result."""
    target: Path | None = None
    platform = _platform(url)
    try:
        video, info = fetch_info(url)
        on_info(video)
        if should_stop():
            return Result(STOPPED)

        entries = _entries(info)
        if not entries:
            return Result(ERROR, message="По ссылке нет видео")
        many = len(entries) > 1
        targets = [
            file_path(folder, video.author, video.id, n if many else None)
            for n in range(1, len(entries) + 1)
        ]
        if all(t.exists() for t in targets):
            return Result(ALREADY, targets[0])
        folder.mkdir(parents=True, exist_ok=True)

        def hook(d: dict) -> None:
            if should_stop():
                raise _Stopped()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                on_progress(int(d.get("downloaded_bytes") or 0), int(total) if total else None)

        selector = _format_selector(platform)
        for number, (entry, target) in enumerate(zip(entries, targets), start=1):
            if target.exists():
                continue  # скачан в прошлый раз
            on_part(number, len(entries))
            if platform == TIKTOK and entry.get("formats") and pick_format(entry["formats"], platform) is None:
                return Result(ERROR, message="Нет версии без водяного знака")
            options = {
                "format": selector,
                "merge_output_format": "mp4",
                # % в пути yt-dlp понимает как шаблон — экранируем
                "outtmpl": {"default": str(target).replace("%", "%%")},
                "progress_hooks": [hook],
                "overwrites": False,
            }
            if many:
                options["playlist_items"] = str(number)
            with _ydl(options) as ydl:
                # Копия: yt-dlp дописывает в словарь свои поля
                ydl.process_ie_result(copy.deepcopy(info), download=True)
            if not target.exists():
                return Result(ERROR, message="Файл не появился после скачивания")

        return Result(DONE, targets[0])

    except _Stopped:
        _cleanup(target)
        return Result(STOPPED)
    except DownloadError as e:
        # yt-dlp заворачивает исключения из хука в DownloadError
        _cleanup(target)
        if isinstance(getattr(e, "exc_info", (None, None))[1], _Stopped):
            return Result(STOPPED)
        return Result(ERROR, message=explain(e))
    except Exception as e:  # noqa: BLE001 — ошибка одной ссылки не должна ронять остальные
        _cleanup(target)
        return Result(ERROR, message=explain(e))


def _cleanup(target: Path | None) -> None:
    """Удаляет недокачанные куски файла."""
    if target is None:
        return
    for leftover in target.parent.glob(glob_escape(target.stem) + "*.part*"):
        leftover.unlink(missing_ok=True)
    target.with_name(target.name + ".part").unlink(missing_ok=True)


def glob_escape(text: str) -> str:
    """Экранирует [ ] * ? для glob (в нике могут встретиться)."""
    return re.sub(r"([\[\]*?])", r"[\1]", text)
