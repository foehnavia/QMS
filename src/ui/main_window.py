"""Главное окно: навигация «Справочники» / «Детали».

Разделы карточки, ввода отклонения и поиска — S3+ и здесь отсутствуют
(`docs/staging.md`); навигация показывает их как недоступные, чтобы порядок
сборки был виден оператору.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QWidget,
)
from sqlalchemy import Engine

from .item_view import ItemView
from .reference_view import ReferenceView

#: Разделы будущих спринтов — видимы, но неактивны.
PLANNED_SECTIONS = (
    ("Отклонения", "S4"),
    ("Карточка отклонения", "S5"),
    ("Поиск", "S5"),
)


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.setWindowTitle("MIS-QMS — база отклонений")
        self.resize(1000, 640)

        self.sections = QListWidget()
        self.pages = QStackedWidget()

        self.reference_view = ReferenceView(engine)
        self.item_view = ItemView(engine)
        self._add_section("Справочники", self.reference_view)
        self._add_section("Детали", self.item_view)

        for title, sprint in PLANNED_SECTIONS:
            item = QListWidgetItem(f"{title}  ({sprint})")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sections.addItem(item)

        self.sections.currentRowChanged.connect(self._switch)
        self.sections.setCurrentRow(0)
        self.sections.setMaximumWidth(260)

        splitter = QSplitter()
        splitter.addWidget(self.sections)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.statusBar().addWidget(QLabel(f"База: {engine.url}"))

    def _add_section(self, title: str, page: QWidget) -> None:
        self.sections.addItem(QListWidgetItem(title))
        self.pages.addWidget(page)

    def _switch(self, row: int) -> None:
        if 0 <= row < self.pages.count():
            self.pages.setCurrentIndex(row)
            current = self.pages.currentWidget()
            # экран мог устареть, пока оператор был в соседнем разделе
            if hasattr(current, "reload"):
                current.reload()
