"""Очередь: проверка ссылок сразу после «Добавить» и скачивание (всё — в фоновых потоках).

Проверка — до PREFETCH_PARALLEL ссылок одновременно: автор, обложка, ожидаемый размер.
Скачивание — до MAX_PARALLEL видео одновременно.
"""

import threading
import time
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
    probed = Signal(int, object, object, bool, float)  # job, данные, размер (или None), точный ли, когда
    probe_failed = Signal(int, str)          # job, понятная причина


def _send_author_and_thumbnail(bridge: _Bridge, jid: int, video: downloader.VideoInfo) -> None:
    bridge.info.emit(jid, video.author)
    if video.thumbnail:
        data = _fetch_thumbnail(video.thumbnail)
        if data:
            bridge.thumbnail.emit(jid, data)


class _ProbeJob(QRunnable):
    """Проверка ссылки до скачивания."""

    def __init__(self, job_id: int, url: str, quality: int, bridge: _Bridge) -> None:
        super().__init__()
        self.job_id, self.url, self.quality, self.bridge = job_id, url, quality, bridge

    def run(self) -> None:
        b, jid = self.bridge, self.job_id
        try:
            video, info = downloader.fetch_info(self.url)
            when = time.time()
            _send_author_and_thumbnail(b, jid, video)
            size, exact = downloader.estimate_size(self.url, info, self.quality, ask_server=True)
            b.probed.emit(jid, info, size, exact, when)
        except Exception as e:  # noqa: BLE001 — ошибка одной ссылки не должна ронять остальные
            b.probe_failed.emit(jid, downloader.explain(e, downloader._platform(self.url)))


class _Job(QRunnable):
    """Скачивание."""

    def __init__(self, job_id: int, url: str, folder: Path, quality: int,
                 prefetched: dict | None, bridge: _Bridge) -> None:
        super().__init__()
        self.job_id = job_id
        self.url = url
        self.folder = folder
        self.quality = quality  # для YouTube
        self.prefetched = prefetched  # данные проверки, если ещё свежие
        self.bridge = bridge
        self.cancel = threading.Event()

    def run(self) -> None:
        b, jid = self.bridge, self.job_id
        b.status.emit(jid, downloader.FETCHING, "", "")

        def on_info(video: downloader.VideoInfo) -> None:
            if self.prefetched is None:  # иначе автор и обложка уже показаны
                _send_author_and_thumbnail(b, jid, video)
            b.status.emit(jid, downloader.DOWNLOADING, "", "")

        def on_progress(done: int, total: int | None) -> None:
            b.progress.emit(jid, done, total or 0)

        def on_part(number: int, count: int) -> None:
            if count > 1:
                b.status.emit(jid, downloader.DOWNLOADING, f"видео {number} из {count}", "")

        result = downloader.download(
            self.url, self.folder, on_info, on_progress, self.cancel.is_set, on_part,
            self.quality, self.prefetched,
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
    probed = Signal(object, object, object, bool, float)  # ключ, данные, размер, точный ли, когда
    probe_failed = Signal(object, str)
    idle = Signal()  # скачивать больше нечего

    def __init__(self) -> None:
        super().__init__()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(config.MAX_PARALLEL)
        self._probe_pool = QThreadPool()
        self._probe_pool.setMaxThreadCount(config.PREFETCH_PARALLEL)
        self._bridge = _Bridge()
        self._ids = count(1)
        self._waiting: deque[tuple[object, str, Path, int, dict | None]] = deque()
        self._running: dict[int, tuple[object, _Job]] = {}
        self._probing: dict[int, object] = {}  # job → ключ (None — строку уже удалили)

        b = self._bridge
        b.info.connect(lambda j, a: self._forward(self.info, j, a))
        b.thumbnail.connect(lambda j, d: self._forward(self.thumbnail, j, d))
        b.status.connect(lambda j, s, m, p: self._forward(self.status, j, s, m, p))
        b.progress.connect(lambda j, d, t: self._forward(self.progress, j, d, t))
        b.finished.connect(self._on_finished)
        b.probed.connect(self._on_probed)
        b.probe_failed.connect(self._on_probe_failed)

    # --- проверка ---

    def probe(self, key: object, url: str, quality: int) -> None:
        job = _ProbeJob(next(self._ids), url, quality, self._bridge)
        self._probing[job.job_id] = key
        self._probe_pool.start(job)

    def _on_probed(self, job_id: int, info: object, size: object, exact: bool, when: float) -> None:
        key = self._probing.pop(job_id, None)
        if key is not None:
            self.probed.emit(key, info, size, exact, when)

    def _on_probe_failed(self, job_id: int, message: str) -> None:
        key = self._probing.pop(job_id, None)
        if key is not None:
            self.probe_failed.emit(key, message)

    # --- скачивание ---

    def is_busy(self, key: object) -> bool:
        """Ждёт в очереди или уже качается."""
        return any(w[0] is key for w in self._waiting) or any(
            k is key for k, _ in self._running.values()
        )

    def add(self, key: object, url: str, folder: Path, quality: int, prefetched: dict | None = None) -> None:
        if self.is_busy(key):
            return
        self._waiting.append((key, url, folder, quality, prefetched))
        self._start_more()

    def stop_all(self) -> list[object]:
        """Прерывает текущие загрузки и снимает ожидающие. Возвращает снятые из ожидания."""
        removed = [w[0] for w in self._waiting]
        self._waiting.clear()
        for _, job in self._running.values():
            job.cancel.set()
        return removed

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """При закрытии окна: прервать всё и дождаться, пока потоки уберут недокачанное."""
        self.stop_all()
        self._probe_pool.clear()  # ещё не начатые проверки не нужны
        self._pool.waitForDone(timeout_ms)

    def forget(self, key: object) -> None:
        """Убирает задание (строку удалили из списка): сигналы по нему больше не приходят."""
        self._waiting = deque(w for w in self._waiting if w[0] is not key)
        for jid, (k, job) in list(self._running.items()):
            if k is key:
                job.cancel.set()
                self._running[jid] = (None, job)
        for jid, k in list(self._probing.items()):
            if k is key:
                self._probing[jid] = None

    def _start_more(self) -> None:
        while self._waiting and len(self._running) < config.MAX_PARALLEL:
            key, url, folder, quality, prefetched = self._waiting.popleft()
            job = _Job(next(self._ids), url, folder, quality, prefetched, self._bridge)
            self._running[job.job_id] = (key, job)
            self._pool.start(job)

    def _forward(self, signal: Signal, job_id: int, *args: object) -> None:
        # Автор и обложка приходят и от проверки, и от скачивания
        key = self._running[job_id][0] if job_id in self._running else self._probing.get(job_id)
        if key is not None:
            signal.emit(key, *args)

    def _on_finished(self, job_id: int) -> None:
        self._running.pop(job_id, None)
        self._start_more()
        if not self._running and not self._waiting:
            self.idle.emit()
