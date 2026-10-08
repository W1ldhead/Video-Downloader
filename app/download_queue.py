"""Очередь загрузок: до MAX_PARALLEL видео одновременно в фоновых потоках."""

import threading
import urllib.request
from collections import deque
from itertools import count
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app import config, downloader


class _Bridge(QObject):
    """Сигналы из фоновых потоков в окно (Qt сам переносит их в главный поток)."""

    info = Signal(int, str)                  # job, автор
    thumbnail = Signal(int, bytes)           # job, картинка
    status = Signal(int, str, str, str)      # job, статус, сообщение, путь
    progress = Signal(int, int, int)         # job, скачано, всего (0 — неизвестно)
    finished = Signal(int)                   # job


class _Job(QRunnable):
    def __init__(self, job_id: int, url: str, folder: Path, bridge: _Bridge) -> None:
        super().__init__()
        self.job_id = job_id
        self.url = url
        self.folder = folder
        self.bridge = bridge
        self.cancel = threading.Event()

    def run(self) -> None:
        b, jid = self.bridge, self.job_id
        b.status.emit(jid, downloader.FETCHING, "", "")

        def on_info(video: downloader.VideoInfo) -> None:
            b.info.emit(jid, video.author)
            if video.thumbnail:
                data = _fetch_thumbnail(video.thumbnail)
                if data:
                    b.thumbnail.emit(jid, data)
            b.status.emit(jid, downloader.DOWNLOADING, "", "")

        def on_progress(done: int, total: int | None) -> None:
            b.progress.emit(jid, done, total or 0)

        def on_part(number: int, count: int) -> None:
            if count > 1:
                b.status.emit(jid, downloader.DOWNLOADING, f"видео {number} из {count}", "")

        result = downloader.download(
            self.url, self.folder, on_info, on_progress, self.cancel.is_set, on_part
        )
        b.status.emit(jid, result.status, result.message, str(result.path or ""))
        b.finished.emit(jid)


def _fetch_thumbnail(url: str) -> bytes | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=config.THUMBNAIL_TIMEOUT) as r:
            return r.read()
    except Exception:  # noqa: BLE001 — без обложки тоже можно скачать
        return None


class DownloadQueue(QObject):
    """Ключ задания — любой объект (у нас — строка списка); окно получает сигналы по нему."""

    info = Signal(object, str)
    thumbnail = Signal(object, bytes)
    status = Signal(object, str, str, str)
    progress = Signal(object, int, int)
    idle = Signal()  # очередь опустела

    def __init__(self) -> None:
        super().__init__()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(config.MAX_PARALLEL)
        self._bridge = _Bridge()
        self._ids = count(1)
        self._waiting: deque[tuple[object, str, Path]] = deque()
        self._running: dict[int, tuple[object, _Job]] = {}

        self._bridge.info.connect(lambda j, a: self._forward(self.info, j, a))
        self._bridge.thumbnail.connect(lambda j, d: self._forward(self.thumbnail, j, d))
        self._bridge.status.connect(lambda j, s, m, p: self._forward(self.status, j, s, m, p))
        self._bridge.progress.connect(lambda j, d, t: self._forward(self.progress, j, d, t))
        self._bridge.finished.connect(self._on_finished)

    def is_busy(self, key: object) -> bool:
        """Ждёт в очереди или уже качается."""
        return any(k is key for k, _, _ in self._waiting) or any(
            k is key for k, _ in self._running.values()
        )

    def add(self, key: object, url: str, folder: Path) -> None:
        if self.is_busy(key):
            return
        self._waiting.append((key, url, folder))
        self._start_more()

    def stop_all(self) -> list[object]:
        """Прерывает текущие загрузки и снимает ожидающие. Возвращает снятые из ожидания."""
        removed = [key for key, _, _ in self._waiting]
        self._waiting.clear()
        for _, job in self._running.values():
            job.cancel.set()
        return removed

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """При закрытии окна: прервать всё и дождаться, пока потоки уберут недокачанное."""
        self.stop_all()
        self._pool.waitForDone(timeout_ms)

    def forget(self, key: object) -> None:
        """Убирает задание (строку удалили из списка): сигналы по нему больше не приходят."""
        self._waiting = deque(w for w in self._waiting if w[0] is not key)
        for jid, (k, job) in list(self._running.items()):
            if k is key:
                job.cancel.set()
                self._running[jid] = (None, job)

    def _start_more(self) -> None:
        while self._waiting and len(self._running) < config.MAX_PARALLEL:
            key, url, folder = self._waiting.popleft()
            job = _Job(next(self._ids), url, folder, self._bridge)
            self._running[job.job_id] = (key, job)
            self._pool.start(job)

    def _forward(self, signal: Signal, job_id: int, *args: object) -> None:
        entry = self._running.get(job_id)
        if entry and entry[0] is not None:
            signal.emit(entry[0], *args)

    def _on_finished(self, job_id: int) -> None:
        self._running.pop(job_id, None)
        self._start_more()
        if not self._running and not self._waiting:
            self.idle.emit()
