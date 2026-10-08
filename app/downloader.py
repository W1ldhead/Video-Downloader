"""Скачивание видео по одной ссылке через yt-dlp (в посте может быть несколько видео)."""

import copy
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadError

from app import config, cookies, vendor
from app.links import INSTAGRAM, TIKTOK, X, YOUTUBE, platform_of

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
    "fixup": "never",  # исправления файлов не нужны, только склейка картинки и звука
    "color": {"stdout": "never", "stderr": "never"},  # без кодов цвета в тексте ошибок
    **vendor.ytdlp_options(),  # встроенные ffmpeg и Deno
}

# Если готового файла со звуком нет — пусть yt-dlp склеит лучшие картинку и звук (нужен ffmpeg)
_MERGE_FORMAT = "bv*+ba/b"


def _ydl(extra: dict | None = None, platform: str | None = None) -> yt_dlp.YoutubeDL:
    options = {**_BASE_OPTIONS, **(extra or {})}
    if platform == YOUTUBE:
        options["noplaylist"] = True  # ссылка вида watch?v=…&list=… — только само видео
    ydl = yt_dlp.YoutubeDL(options)
    # Только вход этой площадки. Грузим вручную, а не через "cookiefile":
    # тогда yt-dlp не перезаписывает файл
    if cookies.is_set(platform):
        ydl.cookiejar.load(str(cookies.stored_path(platform)))
    return ydl


def _platform(url: str) -> str | None:
    try:
        return platform_of(url)
    except ValueError:
        return None


def pick_format(formats: list[dict], platform: str | None = TIKTOK) -> dict | None:
    """Лучший готовый файл с картинкой и звуком (у TikTok — без водяного знака) или None."""
    def allowed(f: dict) -> bool:
        note = (f.get("format_note") or "").lower()
        if "unplayable" in note:
            return False
        return not (platform == TIKTOK and "watermark" in note)

    # «none» — точно нет; None — yt-dlp не знает (у X так подписаны обычные mp4)
    good = [f for f in formats if allowed(f) and f.get("vcodec") != "none" and f.get("acodec") != "none"]
    has_audio = any(
        f.get("acodec") not in (None, "none") or f.get("vcodec") == "none"  # поток «только звук»
        for f in formats
    )
    if not good and not has_audio:
        # Звука нет ни в одном формате — ролик немой, склеивать не с чем
        good = [f for f in formats if allowed(f) and f.get("vcodec") != "none"]
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


def youtube_pick(formats: list[dict], quality: int) -> tuple[str, str | None] | None:
    """Выбор для YouTube: (id картинки, id звука или None) или None, если видео нет.

    quality — высота кадра (0 — максимальная). Берём наибольшую высоту не выше
    quality, а если таких нет — наименьшую из имеющихся. До YOUTUBE_H264_UP_TO
    на этой высоте предпочитаем h264. Звук — лучше AAC (m4a): с mp4 дружит везде.
    """
    def is_hls(f: dict) -> bool:
        return "m3u8" in (f.get("protocol") or "")

    videos = [f for f in formats if f.get("vcodec") not in (None, "none") and f.get("height")]
    if not videos:
        return None
    heights = sorted({f["height"] for f in videos})
    fitting = [h for h in heights if not quality or h <= quality]
    height = max(fitting) if fitting else min(heights)

    def video_rank(f: dict) -> tuple:
        h264 = (f.get("vcodec") or "").startswith(("avc1", "h264"))
        return (
            h264 if height <= config.YOUTUBE_H264_UP_TO else True,
            not is_hls(f),
            f.get("acodec") in (None, "none"),  # чистая картинка: звук подберём лучший
            f.get("fps") or 0,
            f.get("tbr") or 0,
        )

    video = max((f for f in videos if f["height"] == height), key=video_rank)
    if video.get("acodec") not in (None, "none"):
        return video["format_id"], None  # уже со звуком

    audios = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    if not audios:
        return video["format_id"], None
    audio = max(
        audios,
        key=lambda f: (
            (f.get("acodec") or "").startswith("mp4a"),
            not is_hls(f),
            f.get("abr") or f.get("tbr") or 0,
        ),
    )
    return video["format_id"], audio["format_id"]


def safe_name(text: str) -> str:
    """Убирает знаки, запрещённые в именах файлов Windows."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip().rstrip(". ")
    return text or "unknown"


def file_path(folder: Path, author: str, video_id: str, number: int | None = None) -> Path:
    suffix = f"_{number}" if number else ""
    return folder / f"{safe_name(author)}_{safe_name(video_id)}{suffix}.mp4"


# Ошибки, которые лечатся входом в аккаунт: (фрагмент текста yt-dlp, понятное объяснение)
_LOGIN_RULES = [
    # TikTok
    ("Log in for access", "Видео 18+: нужен вход в аккаунт с подтверждённым возрастом"),
    # X (Twitter)
    ("NSFW tweet requires authentication", "Пост с деликатным содержимым: X показывает его только после входа"),
    ("protected tweet", "Аккаунт закрыт: пост видят только подписчики"),
    # Instagram
    ("registered users who follow this account", "Закрытый аккаунт: видео видят только подписчики"),
    ("exceeded the rate-limit", "Instagram временно ограничил скачивание без входа"),
    ("Restricted Video", "Видео с ограничением по возрасту или стране"),
    ("empty media response", "Instagram не отдал видео без входа в аккаунт"),
    ("This content is unreachable", "Instagram не отдал видео без входа в аккаунт"),
    # YouTube
    ("Sign in to confirm your age", "Видео 18+: нужен вход в аккаунт с подтверждённым возрастом"),
    ("Sign in to confirm you", "YouTube просит подтвердить, что вы не робот: нужен вход в аккаунт"),
    ("members-only", "Видео только для спонсоров канала"),
    # Общие
    ("You need to log in", "Нужен вход в аккаунт"),
    ("--cookies", "Нужен вход в аккаунт"),  # так yt-dlp заканчивает любые «нужен вход»
]


def _login_hint(platform: str | None) -> str:
    if cookies.is_set(platform):
        return ". Указанный вход не подошёл: файл cookies устарел или у аккаунта нет доступа — сохраните файл заново"
    return ". Укажите вход: меню «Аккаунты»"


def explain(error: Exception, platform: str | None = None) -> str:
    """Короткая понятная причина ошибки (platform — чтобы подсказать про вход)."""
    # yt-dlp раскрашивает текст для терминала — убираем коды цвета
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    low = text.lower()
    for needle, message in _LOGIN_RULES:
        if needle.lower() in low:
            return message + _login_hint(platform)
    rules = [
        # X (Twitter)
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
    # uploader у X и Instagram — отображаемое имя с пробелами и эмодзи, ник надёжнее
    if platform == X:
        return info.get("uploader_id") or info.get("uploader") or "unknown"
    if platform == INSTAGRAM:
        # у Instagram ник лежит в channel, а uploader_id — число
        return info.get("channel") or info.get("uploader") or "unknown"
    if platform == YOUTUBE:
        # uploader_id — «@ник» канала; у старых каналов его нет — тогда название
        handle = (info.get("uploader_id") or "").lstrip("@")
        return handle or info.get("channel") or info.get("uploader") or "unknown"
    return info.get("uploader") or info.get("uploader_id") or info.get("channel") or "unknown"


def _post_id(url: str, info: dict, platform: str | None) -> str:
    if platform == X:
        # У видео в X свой номер, а пользователь видит номер поста — берём его из ссылки
        m = re.search(r"/status/(\d+)", url)
        if m:
            return m.group(1)
    return str(info.get("id") or "")


def _resolve(ydl: yt_dlp.YoutubeDL, info: dict, depth: int = 5) -> dict:
    """Проходит переадресации (короткие ссылки vm.tiktok.com и т. п.) до самого видео.

    Без process=False это делал бы сам yt-dlp; с ним приходит «ссылка на ссылку».
    """
    for _ in range(depth):
        kind = info.get("_type")
        if kind not in ("url", "url_transparent"):
            return info
        target = ydl.extract_info(info["url"], download=False, process=False, ie_key=info.get("ie_key"))
        if kind == "url_transparent":
            # Поля обёртки дополняют найденное (так делает и yt-dlp)
            extra = {k: v for k, v in info.items() if v is not None and k not in ("_type", "url", "ie_key", "id")}
            target = {**target, **extra}
        info = target
    return info


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
    with _ydl(platform=platform) as ydl:
        info = _resolve(ydl, ydl.extract_info(url, download=False, process=False))
    if info.get("entries") is not None:
        info["entries"] = [e for e in info["entries"] if e]  # бывает «ленивым» списком
    return summarize(url, info), info


def summarize(url: str, info: dict) -> VideoInfo:
    """Кратко о видео для интерфейса — из «сырого» ответа fetch_info."""
    platform = _platform(url)
    entries = _entries(info)
    first = entries[0] if entries else info
    return VideoInfo(
        id=_post_id(url, info, platform),
        author=_author(info, platform),
        thumbnail=_thumbnail(info) or _thumbnail(first),
        count=len(entries),
    )


def _format_size(fmt: dict, duration: float | None, ask_server: bool) -> tuple[int | None, bool]:
    """Размер одного формата: (байты или None, точный ли)."""
    if fmt.get("filesize"):
        return int(fmt["filesize"]), True
    if fmt.get("filesize_approx"):
        return int(fmt["filesize_approx"]), False
    if ask_server and fmt.get("url") and "m3u8" not in (fmt.get("protocol") or ""):
        size = _content_length(fmt["url"], fmt.get("http_headers") or {})
        if size:
            return size, True
    if fmt.get("tbr") and duration:
        # Битрейт (кбит/с) × длительность. Грубо: у X битрейт в описании — «потолок», файл меньше
        return int(fmt["tbr"] * 1000 / 8 * duration), False
    return None, False


def _content_length(url: str, headers: dict) -> int | None:
    """Размер файла по ответу сервера на короткий запрос, без скачивания."""
    try:
        request = urllib.request.Request(url, method="HEAD", headers=headers)
        with urllib.request.urlopen(request, timeout=config.SIZE_REQUEST_TIMEOUT) as r:
            length = r.headers.get("Content-Length")
            return int(length) if length and int(length) > 0 else None
    except Exception:  # noqa: BLE001 — без размера тоже можно скачать
        return None


def estimate_size(url: str, info: dict, quality: int, ask_server: bool = False) -> tuple[int | None, bool]:
    """Ожидаемый размер всех видео по ссылке: (байты или None, точный ли).

    Формат выбирается так же, как при скачивании. ask_server — можно ли спросить
    размер у сервера (сетевой запрос; у Instagram других данных нет).
    """
    platform = _platform(url)
    total, exact = 0, True
    for entry in _entries(info):
        size, is_exact = _entry_size(entry, info, platform, quality, ask_server)
        if size is None:
            return None, False
        total += size
        exact = exact and is_exact
    return (total, exact) if total else (None, False)


def _entry_size(entry: dict, info: dict, platform: str | None, quality: int,
                ask_server: bool) -> tuple[int | None, bool]:
    """Размер одного видео поста (картинка + звук, если их качают отдельно)."""
    formats = entry.get("formats") or []
    if platform == YOUTUBE:
        picked = youtube_pick(formats, quality)
        by_id = {f.get("format_id"): f for f in formats}
        chosen = [by_id[p] for p in picked if p and p in by_id] if picked else []
    else:
        fmt = pick_format(formats, platform)
        chosen = [fmt] if fmt else []
    if not chosen:
        return None, False
    total, exact = 0, True
    for fmt in chosen:
        size, is_exact = _format_size(fmt, entry.get("duration") or info.get("duration"), ask_server)
        if size is None:
            return None, False
        total += size
        exact = exact and is_exact
    return total, exact


def _format_selector(platform: str | None, quality: int):
    """Функция выбора формата для yt-dlp: наш выбор, а если готового файла нет — склейка."""
    # merge_output_format здесь обязателен: расширение склейки решает этот экземпляр,
    # без него для VP9/AV1 (1440p, 4K) выходит .mkv
    ydl = _ydl({"merge_output_format": "mp4"})
    merge = ydl.build_format_selector(_MERGE_FORMAT)

    def select(ctx: dict):
        if platform == YOUTUBE:
            picked = youtube_pick(ctx["formats"], quality)
            spec = "+".join(p for p in picked if p) if picked else _MERGE_FORMAT
            # Сборку «картинка+звук» по номерам форматов делает сам yt-dlp
            yield from ydl.build_format_selector(spec)(ctx)
            return
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
    quality: int = config.YOUTUBE_DEFAULT_QUALITY,
    prefetched: dict | None = None,
) -> Result:
    """Скачивает все видео по ссылке. Исключений наружу не бросает — всё в Result.

    prefetched — данные, полученные заранее (fetch_info); если их нет — получаем сейчас.
    """
    target: Path | None = None
    platform = _platform(url)
    try:
        if prefetched is not None:
            info = prefetched
            video = summarize(url, info)
        else:
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

        # Картинка и звук YouTube качаются по очереди — считаем общий прогресс по обоим.
        # Общий размер видео — из нашей же оценки (без сети), иначе — по ходу скачивания
        state = {"finished": 0, "expected": None}

        def hook(d: dict) -> None:
            if should_stop():
                raise _Stopped()
            this_total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if d.get("status") == "finished":
                state["finished"] += int(this_total or d.get("downloaded_bytes") or 0)
            elif d.get("status") == "downloading":
                done = state["finished"] + int(d.get("downloaded_bytes") or 0)
                total = state["expected"] or (state["finished"] + this_total if this_total else None)
                if total:
                    total = max(total, done)  # оценка бывает чуть меньше настоящего
                on_progress(done, int(total) if total else None)

        selector = _format_selector(platform, quality)
        for number, (entry, target) in enumerate(zip(entries, targets), start=1):
            if target.exists():
                continue  # скачан в прошлый раз
            on_part(number, len(entries))
            # У каждого видео поста — свой счёт
            state["finished"] = 0
            state["expected"] = _entry_size(entry, info, platform, quality, ask_server=False)[0]
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
            with _ydl(options, platform) as ydl:
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
        return Result(ERROR, message=explain(e, platform))
    except Exception as e:  # noqa: BLE001 — ошибка одной ссылки не должна ронять остальные
        _cleanup(target)
        return Result(ERROR, message=explain(e, platform))


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
