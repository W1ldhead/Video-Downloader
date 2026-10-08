"""Самопроверка собранного .exe без окна:
`"Video Downloader.exe" --selftest отчёт.txt [ссылка [папка для скачивания]]`.

У .exe без консоли нет вывода, поэтому отчёт пишется в файл.
"""

import traceback
from pathlib import Path


def run(report: Path, url: str | None, download_to: Path | None = None) -> int:
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

    def bundled_tools():
        import subprocess

        from app import vendor

        ffmpeg, deno = vendor.ffmpeg(), vendor.deno()
        if not ffmpeg or not deno:
            raise RuntimeError(f"нет встроенных программ: ffmpeg={ffmpeg}, deno={deno}")
        flags = subprocess.CREATE_NO_WINDOW
        ff = subprocess.run([str(ffmpeg), "-version"], capture_output=True, text=True, creationflags=flags)
        dn = subprocess.run([str(deno), "--version"], capture_output=True, text=True, creationflags=flags)
        return f"{ff.stdout.splitlines()[0][:40]} | {dn.stdout.splitlines()[0]}"

    step("ffmpeg и Deno", bundled_tools)

    def js_runtime():
        import yt_dlp

        from app import downloader

        with yt_dlp.YoutubeDL(downloader._BASE_OPTIONS) as ydl:
            runtimes = [r for r in ydl._js_runtimes.values() if r.info]
        if not runtimes:
            raise RuntimeError("yt-dlp не видит Deno — YouTube не будет работать")
        import yt_dlp_ejs  # noqa: F401 — скрипты разбора защиты YouTube

        return ", ".join(f"{r.info.name} {r.info.version}" for r in runtimes) + ", yt_dlp_ejs есть"

    step("JS для YouTube", js_runtime)

    if url:
        def fetch():
            from app.downloader import fetch_info

            video, info = fetch_info(url)
            return f"@{video.author} {video.id}, форматов: {len(info.get('formats') or [])}"

        step("данные видео", fetch)

    if url and download_to:
        def download():
            from app import downloader

            result = downloader.download(url, download_to, quality=1080)
            if result.status not in (downloader.DONE, downloader.ALREADY):
                raise RuntimeError(f"{result.status}: {result.message}")
            return f"{result.path.name}, {result.path.stat().st_size // 1024} КБ"

        step("скачивание", download)

    lines.append("ИТОГ: " + ("всё в порядке" if ok else "есть ошибки"))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
