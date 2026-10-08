"""Скачивает ffmpeg и Deno в vendor/bin (для разработки и сборки .exe).

Источники — официальные выпуски на GitHub, контрольные суммы сверяются:
- ffmpeg: сборка команды yt-dlp (github.com/yt-dlp/FFmpeg-Builds), лицензия GPL;
- Deno: github.com/denoland/deno, лицензия MIT.
Запуск из папки проекта: .venv\\Scripts\\python.exe tools/get_vendor.py
"""

import hashlib
import io
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "vendor" / "bin"
LICENSES = ROOT / "vendor" / "licenses"

FFMPEG_BASE = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
FFMPEG_ZIP = "ffmpeg-master-latest-win64-gpl.zip"
DENO_BASE = "https://github.com/denoland/deno/releases/latest/download/"
DENO_ZIP = "deno-x86_64-pc-windows-msvc.zip"


def fetch(url: str) -> bytes:
    print("  скачиваю", url)
    request = urllib.request.Request(url, headers={"User-Agent": "video-downloader-build"})
    with urllib.request.urlopen(request, timeout=120) as r:
        return r.read()


def expected_sha256(listing: str, name: str) -> str:
    """Сумма файла из списка «<sha256>  <имя>» или из вывода PowerShell «Hash : <sha256>» (так у Deno)."""
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            return parts[0].lower()
    found = re.search(r"\bHash\s*:\s*([0-9A-Fa-f]{64})\b", listing)
    if found:
        return found.group(1).lower()
    raise SystemExit(f"Не нашёл контрольную сумму для {name}")


def verified(data: bytes, sha: str, name: str) -> bytes:
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha:
        raise SystemExit(f"{name}: контрольная сумма не совпала ({actual} != {sha})")
    print(f"  {name}: контрольная сумма совпала, {len(data) / 1e6:.1f} МБ")
    return data


def extract(data: bytes, wanted: dict[str, Path]) -> None:
    """Достаёт из zip файлы по имени (в любой вложенной папке)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename.rsplit("/", 1)[-1]
            if name in wanted:
                target = wanted.pop(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  → {target.relative_to(ROOT)}")
    if wanted:
        raise SystemExit(f"В архиве нет: {', '.join(wanted)}")


def main() -> None:
    print("ffmpeg:")
    sums = fetch(FFMPEG_BASE + "checksums.sha256").decode()
    data = verified(fetch(FFMPEG_BASE + FFMPEG_ZIP), expected_sha256(sums, FFMPEG_ZIP), FFMPEG_ZIP)
    # ffprobe не берём: для склейки картинки и звука он не нужен, а весит 160 МБ
    extract(data, {
        "ffmpeg.exe": BIN / "ffmpeg.exe",
        "LICENSE.txt": LICENSES / "ffmpeg-LICENSE.txt",
    })

    print("Deno:")
    sums = fetch(DENO_BASE + DENO_ZIP + ".sha256sum").decode()
    data = verified(fetch(DENO_BASE + DENO_ZIP), expected_sha256(sums, DENO_ZIP), DENO_ZIP)
    extract(data, {"deno.exe": BIN / "deno.exe"})
    deno_license = fetch("https://raw.githubusercontent.com/denoland/deno/main/LICENSE.md")
    (LICENSES / "deno-LICENSE.md").write_bytes(deno_license)
    print("Готово.")


if __name__ == "__main__":
    sys.exit(main())
