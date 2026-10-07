"""Самопроверка собранного .exe без окна: `"TikTok Downloader.exe" --selftest отчёт.txt [ссылка]`.

У .exe без консоли нет вывода, поэтому отчёт пишется в файл.
"""

import traceback
from pathlib import Path


def run(report: Path, url: str | None) -> int:
    lines: list[str] = []
    ok = True

    def step(name: str, func) -> None:
        nonlocal ok
        try:
            lines.append(f"OK   {name}: {func()}")
        except Exception:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL {name}:\n{traceback.format_exc()}")

    from app import updater

    step("встроенный yt-dlp", updater.bundled_version)
    step("скачанный yt-dlp", lambda: updater.downloaded_wheel() or "нет")

    def ytdlp():
        import yt_dlp

        return f"{updater.running_version()} из {yt_dlp.__file__}"

    step("работает yt-dlp", ytdlp)

    def impersonate():
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            targets = ydl._get_available_impersonate_targets()
        if not targets:
            raise RuntimeError("нет целей impersonate — TikTok не будет работать")
        return f"curl_cffi {curl_cffi.__version__}, целей: {len(targets)}, {ImpersonateTarget.__name__}"

    step("curl_cffi", impersonate)

    if url:
        def fetch():
            from app.downloader import fetch_info

            video, info = fetch_info(url)
            return f"@{video.author} {video.id}, форматов: {len(info.get('formats') or [])}"

        step("данные видео", fetch)

    lines.append("ИТОГ: " + ("всё в порядке" if ok else "есть ошибки"))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
