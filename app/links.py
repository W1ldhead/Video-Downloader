"""Поиск ссылок на видео (TikTok, YouTube, Instagram, X) в произвольном тексте."""

import re
from urllib.parse import parse_qs, urlsplit

# Площадки; имена же — названия подпапок
TIKTOK = "TikTok"
YOUTUBE = "YouTube"
INSTAGRAM = "Instagram"
X = "X"
PLATFORMS = (TIKTOK, YOUTUBE, INSTAGRAM, X)

# Кандидат: адрес на одном из доменов, до пробела или кавычки
_CANDIDATE = re.compile(
    r"(?<![a-z0-9.-])(?:https?://)?(?:[a-z0-9-]+\.)*"
    r"(?:tiktok\.com|youtube\.com|youtu\.be|instagram\.com|x\.com|twitter\.com)"
    r"/[^\s<>\"'«»]*",
    re.IGNORECASE,
)

# Знаки, которые часто прилипают к концу ссылки в переписке
_TRAILING = ".,;:!?)]}…"

_I = re.IGNORECASE

# TikTok
_TT_VIDEO = re.compile(r"^(?:www\.|m\.)?tiktok\.com/@([^/?#]+)/video/(\d+)", _I)
_TT_MOBILE = re.compile(r"^(?:www\.|m\.)?tiktok\.com/v/(\d+)", _I)
_TT_SHORT_HOST = re.compile(r"^(vm|vt)\.tiktok\.com/([A-Za-z0-9]+)", _I)
_TT_SHORT_T = re.compile(r"^(?:www\.|m\.)?tiktok\.com/t/([A-Za-z0-9]+)", _I)

# YouTube: id видео — 11 знаков
_YT_ID = r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
_YT_HOST = r"^(?:www\.|m\.)?youtube\.com"
_YT_WATCH = re.compile(_YT_HOST + r"/watch\b", _I)
_YT_SHORTS = re.compile(_YT_HOST + r"/shorts/" + _YT_ID, _I)
_YT_LIVE = re.compile(_YT_HOST + r"/live/" + _YT_ID, _I)
_YT_SHORT_LINK = re.compile(r"^youtu\.be/" + _YT_ID, _I)

# Instagram: /reel/КОД, /reels/КОД, /p/КОД, /tv/КОД, в том числе после имени автора
_IG = re.compile(
    r"^(?:www\.|m\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(reels?|p|tv)/([A-Za-z0-9_-]+)", _I
)

# X / Twitter: /автор/status/123 и /i/status/123
_X = re.compile(
    r"^(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+|i(?:/web)?)/status(?:es)?/(\d+)", _I
)


def _normalize(raw: str) -> tuple[tuple, str] | None:
    """Возвращает (ключ для поиска дублей, аккуратная ссылка) или None."""
    s = re.sub(r"^https?://", "", raw, flags=_I)

    # TikTok
    if m := _TT_VIDEO.match(s):
        author, vid = m.groups()
        return (TIKTOK, vid), f"https://www.tiktok.com/@{author}/video/{vid}"
    if m := _TT_MOBILE.match(s):
        vid = m.group(1)
        return (TIKTOK, vid), f"https://m.tiktok.com/v/{vid}.html"
    if m := _TT_SHORT_HOST.match(s):
        host, code = m.group(1).lower(), m.group(2)
        return (TIKTOK, "short", host, code), f"https://{host}.tiktok.com/{code}/"
    if m := _TT_SHORT_T.match(s):
        code = m.group(1)
        return (TIKTOK, "short", "t", code), f"https://www.tiktok.com/t/{code}/"

    # YouTube: Shorts оставляем Shorts, остальное приводим к /watch?v=
    if m := _YT_SHORTS.match(s):
        vid = m.group(1)
        return (YOUTUBE, vid), f"https://www.youtube.com/shorts/{vid}"
    if _YT_WATCH.match(s):
        values = parse_qs(urlsplit("https://" + s).query).get("v", [])
        if values and re.fullmatch(r"[A-Za-z0-9_-]{11}", values[0]):
            vid = values[0]
            return (YOUTUBE, vid), f"https://www.youtube.com/watch?v={vid}"
        return None
    if m := _YT_LIVE.match(s) or _YT_SHORT_LINK.match(s):
        vid = m.group(1)
        return (YOUTUBE, vid), f"https://www.youtube.com/watch?v={vid}"

    # Instagram
    if m := _IG.match(s):
        kind, code = m.group(1).lower(), m.group(2)
        kind = "reel" if kind.startswith("reel") else kind
        return (INSTAGRAM, code), f"https://www.instagram.com/{kind}/{code}/"

    # X / Twitter
    if m := _X.match(s):
        author, post_id = m.groups()
        if author.lower() in ("i", "i/web"):
            author = "i"
        return (X, post_id), f"https://x.com/{author}/status/{post_id}"

    # Профили, музыка, каналы, главные страницы — не видео, пропускаем
    return None


def find_links(text: str) -> list[str]:
    """Все ссылки на видео из текста, по порядку, без дублей."""
    result: list[str] = []
    seen: set[tuple] = set()
    for match in _CANDIDATE.finditer(text):
        raw = match.group(0).rstrip(_TRAILING)
        found = _normalize(raw)
        if found is None:
            continue
        key, url = found
        if key in seen:
            continue
        seen.add(key)
        result.append(url)
    return result


def platform_of(url: str) -> str:
    """Площадка по ссылке (ссылки — из find_links)."""
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("tiktok.com"):
        return TIKTOK
    if host.endswith(("youtube.com", "youtu.be")):
        return YOUTUBE
    if host.endswith("instagram.com"):
        return INSTAGRAM
    if host.endswith(("x.com", "twitter.com")):
        return X
    raise ValueError(f"Неизвестная площадка: {url}")
