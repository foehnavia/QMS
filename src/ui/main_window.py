"""Главное окно: навигация по разделам приложения.

Самостоятельный экран поиска — Этап 1.5 (S8) и здесь отсутствует; навигация
показывает его недоступным, чтобы порядок сборки был виден оператору.
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

from .cg_view import CgView
from .deviation_view import DeviationView
from .item_view import ItemView
from .reference_view import ReferenceView

#: Разделы будущих спринтов — видимы, но неактивны.
#:
#: Карточки здесь нет намеренно: она открывается **от конкретного отклонения**
#: (кнопка и двойной клик в списке, автооткрытие после регистрации), а не как
#: самостоятельный раздел — показывать её пустой не от чего.
#: «Поиск» — это конструктор произвольных запросов, Этап 1.5 (`Search.md` →
#: deep search); S5 ищет только от отклонения, которое на руках.
PLANNED_SECTIONS = (("Поиск", "S8"),)


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.setWindowTitle("MIS-QMS — база отклонений")
        self.resize(1000, 640)

        self.sections = QListWidget()
        self.pages = QStackedWidget()

        self.reference_view = ReferenceView(engine)
        self.cg_view = CgView(engine)
        self.item_view = ItemView(engine)
        self.deviation_view = DeviationView(engine)
        self._add_section("Справочники", self.reference_view)
        self._add_section("Группы характеристик", self.cg_view)
        self._add_section("Детали", self.item_view)
        self._add_section("Отклонения", self.deviation_view)

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
