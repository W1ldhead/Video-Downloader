"""Встроенные программы: ffmpeg (склейка картинки и звука) и Deno (защита YouTube).

При разработке они лежат в vendor/bin (скачивает tools/get_vendor.py),
в собранном .exe — во временной папке распаковки (sys._MEIPASS/vendor/bin).
"""

import sys
from pathlib import Path


def bin_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / "vendor" / "bin"


def ffmpeg() -> Path | None:
    path = bin_dir() / "ffmpeg.exe"
    return path if path.is_file() else None


def deno() -> Path | None:
    path = bin_dir() / "deno.exe"
    return path if path.is_file() else None


def ytdlp_options() -> dict:
    """Параметры yt-dlp, указывающие на встроенные программы (если они есть)."""
    options: dict = {}
    if ffmpeg():
        options["ffmpeg_location"] = str(ffmpeg())
    if deno():
        options["js_runtimes"] = {"deno": {"path": str(deno())}}
    return options
