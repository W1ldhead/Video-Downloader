"""Главное окно приложения."""

from pathlib import Path

from PySide6.QtWidgets import (
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

from app import settings
from app.item_widget import ItemWidget
from app.links import find_links


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TikTok Downloader")
        self.resize(720, 680)

        # Поле ссылок и «Добавить»
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Вставьте сюда ссылки на видео TikTok — одну, несколько или кусок переписки"
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

        # Список загрузок
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setSpacing(2)
        self.empty_hint = QLabel("Список пуст. Вставьте ссылки и нажмите «Добавить».")
        self.empty_hint.setStyleSheet("color:#9e9e9e;")

        # Кнопки управления
        self.download_all = QPushButton("Скачать всё")
        self.stop_button = QPushButton("Остановить")
        self.clear_button = QPushButton("Очистить список")
        self.clear_button.clicked.connect(self.clear_list)
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

    # --- ссылки ---

    def items(self) -> list[ItemWidget]:
        return [self.list.itemWidget(self.list.item(i)) for i in range(self.list.count())]

    def add_links(self) -> None:
        found = find_links(self.input.toPlainText())
        if not found:
            QMessageBox.information(
                self, "Ссылки не найдены",
                "В тексте нет ссылок на видео TikTok.\n\n"
                "Подходят ссылки вида tiktok.com/@автор/video/…, vm.tiktok.com/… и vt.tiktok.com/…",
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
        return widget

    def clear_list(self) -> None:
        self.list.clear()
        self._update_empty_hint()

    def _update_empty_hint(self) -> None:
        self.empty_hint.setVisible(self.list.count() == 0)

    # --- папка ---

    def choose_folder(self) -> None:
        start = self.folder if self.folder.exists() else Path.home()
        chosen = QFileDialog.getExistingDirectory(self, "Куда сохранять видео", str(start))
        if chosen:
            self.folder = Path(chosen)
            self.folder_edit.setText(str(self.folder))
            settings.save_folder(self.folder)
