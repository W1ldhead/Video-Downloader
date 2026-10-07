"""Поиск ссылок на видео TikTok в произвольном тексте."""

import re

# Кандидат: всё, что похоже на адрес на домене tiktok.com, до пробела или кавычки
_CANDIDATE = re.compile(
    r"(?<![a-z0-9.-])(?:https?://)?(?:[a-z0-9-]+\.)*tiktok\.com/[^\s<>\"'«»]*",
    re.IGNORECASE,
)

# Знаки, которые часто прилипают к концу ссылки в переписке
_TRAILING = ".,;:!?)]}…"

# Полная ссылка на видео: /@автор/video/123 (поддомен www., m. или без него)
_VIDEO = re.compile(
    r"^(?:www\.|m\.)?tiktok\.com/@([^/?#]+)/video/(\d+)",
    re.IGNORECASE,
)
# Старая мобильная форма: m.tiktok.com/v/123.html
_MOBILE = re.compile(r"^(?:www\.|m\.)?tiktok\.com/v/(\d+)", re.IGNORECASE)
# Короткие ссылки: vm.tiktok.com/КОД, vt.tiktok.com/КОД, tiktok.com/t/КОД
_SHORT_HOST = re.compile(r"^(vm|vt)\.tiktok\.com/([A-Za-z0-9]+)", re.IGNORECASE)
_SHORT_T = re.compile(r"^(?:www\.|m\.)?tiktok\.com/t/([A-Za-z0-9]+)", re.IGNORECASE)


def _normalize(raw: str) -> tuple[tuple, str] | None:
    """Возвращает (ключ для поиска дублей, аккуратная ссылка) или None."""
    s = re.sub(r"^https?://", "", raw, flags=re.IGNORECASE)

    m = _VIDEO.match(s)
    if m:
        author, video_id = m.group(1), m.group(2)
        return ("video", video_id), f"https://www.tiktok.com/@{author}/video/{video_id}"

    m = _MOBILE.match(s)
    if m:
        video_id = m.group(1)
        return ("video", video_id), f"https://m.tiktok.com/v/{video_id}.html"

    m = _SHORT_HOST.match(s)
    if m:
        host, code = m.group(1).lower(), m.group(2)
        return ("short", host, code), f"https://{host}.tiktok.com/{code}/"

    m = _SHORT_T.match(s)
    if m:
        code = m.group(1)
        return ("short", "t", code), f"https://www.tiktok.com/t/{code}/"

    # Профили, музыка, главная страница и т. п. — не видео, пропускаем
    return None


def find_links(text: str) -> list[str]:
    """Все ссылки на видео TikTok из текста, по порядку, без дублей."""
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
