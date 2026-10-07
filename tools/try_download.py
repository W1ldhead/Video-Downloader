"""Ручная проверка: скачивает одно видео по ссылке в папку Загрузки\\TikTok."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import downloader  # noqa: E402

if len(sys.argv) < 2:
    print("Использование: python tools/try_download.py <ссылка> [папка]")
    sys.exit(1)

url = sys.argv[1]
folder = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "Downloads" / "TikTok"
last = -1


def on_info(v: downloader.VideoInfo) -> None:
    print(f"Автор: {v.author}, id: {v.id}")


def on_progress(done: int, total: int | None) -> None:
    global last
    if total:
        percent = done * 100 // total
        if percent // 10 != last // 10:
            last = percent
            print(f"  скачано {percent}%")


print("Получаю данные...")
result = downloader.download(url, folder, on_info, on_progress)
print(f"Статус: {result.status}")
if result.path:
    print(f"Файл: {result.path}")
if result.message:
    print(f"Причина: {result.message}")
