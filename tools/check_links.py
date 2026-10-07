"""Ручная проверка: берёт текст из буфера обмена и печатает найденные ссылки."""

import sys
import tkinter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.links import find_links  # noqa: E402

root = tkinter.Tk()
root.withdraw()
try:
    text = root.clipboard_get()
except tkinter.TclError:
    text = ""
root.destroy()

links = find_links(text)
if links:
    print(f"Найдено ссылок: {len(links)}")
    for url in links:
        print("  " + url)
else:
    print("Ссылок на видео TikTok не найдено.")
