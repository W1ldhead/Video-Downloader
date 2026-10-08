"""Главное окно приложения."""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config, cookies, downloader, settings, updater
from app.download_queue import DownloadQueue
from app.item_widget import ItemWidget
from app.links import PLATFORMS, find_links, platform_of

# Эти строки «Скачать всё» берёт в работу; ошибки — только через «Повторить»
_STARTABLE = ("queued", downloader.STOPPED)


class _UpdateSignals(QObject):
    done = Signal(str, bool, str)  # версия на сервере, скачано ли, текст ошибки


class _UpdateTask(QRunnable):
    """Проверка и скачивание обновления в фоне."""

    def __init__(self, signals: _UpdateSignals) -> None:
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        try:
            version, installed = updater.update()
            self.signals.done.emit(version, installed, "")
        except updater.UpdateError as e:
            self.signals.done.emit("", False, str(e))
        except Exception as e:  # noqa: BLE001
            self.signals.done.emit("", False, f"Неожиданная ошибка: {e}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Downloader")
        self.resize(720, 680)

        # Поле ссылок и «Добавить»
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Вставьте сюда ссылки на видео из TikTok, YouTube, Instagram или X — "
            "одну, несколько или кусок переписки"
        )
        self.input.setFixedHeight(110)
        self.add_button = QPushButton("Добавить")
        self.add_button.clicked.connect(self.add_links)

        # Папка
        self.folder = settings.load_folder()
        self.folder_edit = QLineEdit(str(self.folder))
        self.folder_edit.setReadOnly(True)
        choose = QPushButton("Выбрать…")
        choose.clicked.connect(self.choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Папка:"))
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(choose)

        # Качество YouTube (запоминается)
        self.quality_box = QComboBox()
        for caption, height in config.YOUTUBE_QUALITIES:
            self.quality_box.addItem(caption, height)
        self.quality_box.setCurrentIndex(max(0, self.quality_box.findData(settings.load_quality())))
        self.quality_box.currentIndexChanged.connect(
            lambda _: settings.save_quality(self.quality_box.currentData())
        )
        self.quality_box.setToolTip(
            "Если у видео нет такого качества, берётся ближайшее меньшее.\n"
            "До 1080p файлы открываются везде; 1440p и 4K — в форматах VP9/AV1, "
            "старые проигрыватели могут их не открыть."
        )
        folder_row.addSpacing(12)
        folder_row.addWidget(QLabel("Качество YouTube:"))
        folder_row.addWidget(self.quality_box)

        # Список загрузок
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setSpacing(2)
        self.empty_hint = QLabel("Список пуст. Вставьте ссылки и нажмите «Добавить».")
        self.empty_hint.setStyleSheet("color:#9e9e9e;")

        # Кнопки управления
        self.download_all = QPushButton("Скачать всё")
        self.download_all.clicked.connect(self.start_all)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_all)
        self.clear_button = QPushButton("Очистить список")
        self.clear_button.clicked.connect(self.clear_list)

        # Очередь загрузок
        self.queue = DownloadQueue()
        self.queue.info.connect(lambda w, author: w.set_author(author))
        self.queue.thumbnail.connect(lambda w, data: w.set_thumbnail(data))
        self.queue.status.connect(
            lambda w, status, message, path: w.set_status(status, message, Path(path) if path else None)
        )
        self.queue.progress.connect(lambda w, done, total: w.set_progress(done, total or None))
        self.queue.idle.connect(self._on_idle)
        controls = QHBoxLayout()
        controls.addWidget(self.download_all)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        controls.addWidget(self.clear_button)

        layout = QVBoxLayout()
        layout.addWidget(self.input)
        add_row = QHBoxLayout()
        add_row.addStretch()
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)
        layout.addLayout(folder_row)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.list, 1)
        layout.addLayout(controls)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self._update_empty_hint()
        self._build_menu()

    # --- меню и обновление загрузчика ---

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Загрузчик")
        self.update_action = menu.addAction("Обновить загрузчик")
        self.update_action.triggered.connect(self.update_loader)
        self.version_action = menu.addAction(f"Версия yt-dlp: {updater.running_version()}")
        self.version_action.setEnabled(False)

        # Аккаунты: свой файл cookies у каждой площадки
        accounts = self.menuBar().addMenu("Аккаунты")
        self._account_menus = {}
        for platform in PLATFORMS:
            sub = accounts.addMenu(platform)
            choose = sub.addAction("Указать файл cookies…")
            choose.triggered.connect(lambda _=False, p=platform: self.choose_cookies(p))
            remove = sub.addAction("Удалить вход")
            remove.triggered.connect(lambda _=False, p=platform: self.remove_cookies(p))
            self._account_menus[platform] = (sub, remove)
        accounts.addSeparator()
        accounts.addAction("Как сохранить файл cookies?").triggered.connect(self.show_cookies_help)
        self._refresh_cookies_menu()

        self._update_signals = _UpdateSignals()
        self._update_signals.done.connect(self._on_update_done)

    def update_loader(self) -> None:
        self.update_action.setEnabled(False)
        self.statusBar().showMessage("Проверяю обновления загрузчика…")
        QThreadPool.globalInstance().start(_UpdateTask(self._update_signals))

    def _on_update_done(self, version: str, installed: bool, error: str) -> None:
        self.update_action.setEnabled(True)
        self.statusBar().clearMessage()
        if error:
            QMessageBox.warning(self, "Обновление загрузчика", error)
            return
        if not installed:
            pending = updater.parse_version(version) > updater.parse_version(updater.running_version())
            QMessageBox.information(
                self, "Обновление загрузчика",
                f"Обновлений нет. Последняя версия {version} уже установлена"
                + (" (заработает после перезапуска)." if pending else "."),
            )
            return
        answer = QMessageBox.question(
            self, "Обновление загрузчика",
            f"Загрузчик обновлён до версии {version}.\n"
            "Новая версия заработает после перезапуска приложения.\n\n"
            "Перезапустить сейчас? Текущие загрузки будут остановлены.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._restart()

    # --- cookies ---

    def _refresh_cookies_menu(self) -> None:
        for platform, (sub, remove) in self._account_menus.items():
            on = cookies.is_set(platform)
            sub.setTitle(f"{platform} — {'вход указан ✓' if on else 'без входа'}")
            remove.setEnabled(on)

    def choose_cookies(self, platform: str) -> None:
        start = str(Path.home() / "Downloads")
        chosen, _ = QFileDialog.getOpenFileName(
            self, f"Файл cookies.txt с входом в {platform}", start, "Файлы cookies (*.txt);;Все файлы (*)"
        )
        if not chosen:
            return
        try:
            warning = cookies.install(Path(chosen), platform)
        except cookies.CookieError as e:
            QMessageBox.warning(self, f"Вход в {platform}", str(e))
            return
        self._refresh_cookies_menu()
        text = (
            f"Вход в {platform} принят, программа сохранила копию файла у себя.\n\n"
            f"Исходный файл лучше удалить из папки — в нём ваш вход в {platform}, как пароль.\n\n"
            "Видео, которые не скачались из-за входа, теперь можно скачать кнопкой «Повторить»."
        )
        if warning:
            text = warning + "\n\n" + text
        QMessageBox.information(self, f"Вход в {platform}", text)

    def remove_cookies(self, platform: str) -> None:
        cookies.remove(platform)
        self._refresh_cookies_menu()
        self.statusBar().showMessage(f"Вход в {platform} удалён.", 5000)

    def show_cookies_help(self) -> None:
        QMessageBox.information(
            self, "Как сохранить файл cookies",
            "Файл cookies — это «пропуск», по которому сайт узнаёт, что вы вошли в аккаунт.\n\n"
            "1. Установите в браузер расширение «Get cookies.txt LOCALLY» "
            "(в Firefox — «cookies.txt»). Важно: именно LOCALLY.\n"
            "2. Откройте сайт площадки (tiktok.com, youtube.com, instagram.com или x.com) "
            "и войдите в аккаунт.\n"
            "3. Нажмите на значок расширения → «Export». Файл сохранится в «Загрузки».\n"
            "4. Здесь: «Аккаунты» → площадка → «Указать файл cookies…» и выберите этот файл.\n"
            "5. Удалите исходный файл из «Загрузок».\n\n"
            "Для каждой площадки — свой файл. Лучше использовать не основной аккаунт: "
            "площадки иногда ограничивают аккаунты за частые скачивания.",
        )

    def _restart(self) -> None:
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:])
        self.close()

    # --- ссылки ---

    def items(self) -> list[ItemWidget]:
        return [self.list.itemWidget(self.list.item(i)) for i in range(self.list.count())]

    def add_links(self) -> None:
        found = find_links(self.input.toPlainText())
        if not found:
            QMessageBox.information(
                self, "Ссылки не найдены",
                "В тексте нет ссылок на видео.\n\n"
                "Подходят ссылки на видео из TikTok, YouTube (и Shorts), Instagram (Reels и посты) "
                "и X (Twitter) — например youtu.be/…, instagram.com/reel/…, x.com/…/status/…",
            )
            return
        known = {w.url for w in self.items()}
        new = [url for url in found if url not in known]
        for url in new:
            self._add_item(url)
        self.input.clear()
        self._update_empty_hint()
        skipped = len(found) - len(new)
        if skipped:
            self.statusBar().showMessage(
                f"Добавлено: {len(new)}. Уже были в списке: {skipped}.", 5000
            )
        else:
            self.statusBar().showMessage(f"Добавлено: {len(new)}.", 5000)

    def _add_item(self, url: str) -> ItemWidget:
        widget = ItemWidget(url)
        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, widget)
        widget.retry_clicked.connect(lambda w=widget: self._enqueue(w))
        widget.open_folder_clicked.connect(lambda w=widget: self._open_folder(w))
        return widget

    def clear_list(self) -> None:
        for widget in self.items():
            self.queue.forget(widget)
        self.list.clear()
        self._update_empty_hint()

    # --- загрузки ---

    def start_all(self) -> None:
        todo = [w for w in self.items() if w.status in _STARTABLE and not self.queue.is_busy(w)]
        if not todo:
            self.statusBar().showMessage("Нечего скачивать: добавьте ссылки.", 5000)
            return
        for widget in todo:
            self._enqueue(widget)
        self.statusBar().showMessage(f"В очереди: {len(todo)}.", 5000)

    def _enqueue(self, widget: ItemWidget) -> None:
        widget.set_status("queued")
        # Каждая площадка — в свою подпапку: …\YouTube, …\TikTok и т. д.
        self.queue.add(
            widget, widget.url, self.folder / platform_of(widget.url), self.quality_box.currentData()
        )

    def stop_all(self) -> None:
        for widget in self.queue.stop_all():
            widget.set_status("queued")
        self.statusBar().showMessage("Загрузки остановлены.", 5000)

    def _on_idle(self) -> None:
        done = sum(w.status in (downloader.DONE, downloader.ALREADY) for w in self.items())
        errors = sum(w.status == downloader.ERROR for w in self.items())
        text = f"Готово: {done}."
        if errors:
            text += f" С ошибкой: {errors}."
        self.statusBar().showMessage(text)

    def _open_folder(self, widget: ItemWidget) -> None:
        # Открывает Проводник и выделяет файл
        if widget.path and widget.path.exists():
            subprocess.Popen(["explorer", "/select,", str(widget.path)])
        else:
            folder = widget.path.parent if widget.path else self.folder
            os.startfile(folder)  # noqa: S606

    def _update_empty_hint(self) -> None:
        self.empty_hint.setVisible(self.list.count() == 0)

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задаёт Qt
        self.queue.shutdown()
        super().closeEvent(event)

    # --- папка ---

    def choose_folder(self) -> None:
        start = self.folder if self.folder.exists() else Path.home()
        chosen = QFileDialog.getExistingDirectory(self, "Куда сохранять видео", str(start))
        if chosen:
            self.folder = Path(chosen)
            self.folder_edit.setText(str(self.folder))
            settings.save_folder(self.folder)
