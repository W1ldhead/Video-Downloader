"""Строка списка загрузок: обложка, автор, статус, прогресс, кнопка действия."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import downloader, sizes

THUMB_W, THUMB_H = 54, 96  # вертикальная обложка 9:16

# Статусы до скачивания: данные получаются сразу после «Добавить»
PROBING = "probing"
READY = "ready"

_STATUS_TEXT = {
    "queued": "В очереди",
    PROBING: "Получение данных…",
    READY: "Можно скачивать",
    downloader.FETCHING: "Получение данных…",
    downloader.DOWNLOADING: "Скачивается",
    downloader.DONE: "Готово",
    downloader.ALREADY: "Уже скачано",
    downloader.ERROR: "Ошибка",
    downloader.STOPPED: "Остановлено",
}
_STATUS_COLOR = {
    downloader.DONE: "#2e7d32",
    downloader.ALREADY: "#2e7d32",
    downloader.ERROR: "#c62828",
}


class ItemWidget(QWidget):
    retry_clicked = Signal()
    open_folder_clicked = Signal()

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.status = "queued"
        self.path: Path | None = None
        self._message = ""
        # Данные, полученные заранее: «сырой» ответ yt-dlp, когда получен, ожидаемый размер
        self.info: dict | None = None
        self.info_time = 0.0
        self.size: int | None = None
        self.size_exact = False

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("background:#e0e0e0; border-radius:4px; color:#9e9e9e;")
        self.thumb.setText("♪")

        self.author = QLabel(url)
        self.author.setStyleSheet("font-weight:600;")
        self.author.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.size_label = QLabel()
        self.size_label.setStyleSheet("color:#616161;")
        title_row = QHBoxLayout()
        title_row.addWidget(self.author, 1)
        title_row.addWidget(self.size_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(10)
        self.progress.setTextVisible(False)
        self.progress.hide()

        self.action = QPushButton()
        self.action.setMinimumWidth(130)
        self.action.hide()
        self.action.clicked.connect(self._on_action)

        text = QVBoxLayout()
        text.setSpacing(4)
        text.addLayout(title_row)
        text.addWidget(self.status_label)
        text.addWidget(self.progress)
        text.addStretch()

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.addWidget(self.thumb)
        row.addLayout(text, 1)
        row.addWidget(self.action, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_status("queued")

    def set_author(self, author: str) -> None:
        self.author.setText("@" + author)
        self.author.setToolTip(self.url)

    def set_thumbnail(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.thumb.setPixmap(
                pixmap.scaled(
                    THUMB_W, THUMB_H,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ).copy(0, 0, THUMB_W, THUMB_H)
            )

    def set_size(self, size: int | None, exact: bool) -> None:
        self.size, self.size_exact = size, exact
        self.size_label.setText(sizes.estimate_text(size, exact))

    def set_info(self, info: dict, when: float) -> None:
        self.info, self.info_time = info, when

    def _status_text(self, extra: str = "") -> str:
        text = _STATUS_TEXT.get(self.status, self.status)
        if self._message:
            text += ": " + self._message
        return text + extra

    def set_status(self, status: str, message: str = "", path: Path | None = None) -> None:
        self.status = status
        self._message = message
        if path is not None:
            self.path = path
        self.status_label.setText(self._status_text())
        color = _STATUS_COLOR.get(status, "#616161")
        self.status_label.setStyleSheet(f"color:{color};")

        self.progress.setVisible(status == downloader.DOWNLOADING)
        if status == downloader.DOWNLOADING:
            self.progress.setRange(0, 0)  # пока размер неизвестен — бегущая полоса

        if status == downloader.ERROR:
            self.action.setText("Повторить")
            self.action.show()
        elif status in (downloader.DONE, downloader.ALREADY):
            self.action.setText("Открыть папку")
            self.action.show()
        else:
            self.action.hide()

    def set_progress(self, done: int, total: int | None) -> None:
        if total:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, done * 1000 // total))
            amount = f"{sizes.human(done)} из {sizes.human(total)}"
        else:
            amount = sizes.human(done)
        # «Скачивается · 12,3 из 45,6 МБ» (у поста из нескольких видео — по текущему)
        self.status_label.setText(self._status_text(" · " + amount))

    def _on_action(self) -> None:
        if self.status == downloader.ERROR:
            self.retry_clicked.emit()
        else:
            self.open_folder_clicked.emit()
