"""Шасси окна: лента навигации сверху, разделы под ней, подвал со сводкой.

Бокового меню **нет** (решение С-4 наряда 0010, канон §1): оно съедало ширину,
а таблица отклонений широкая — горизонтальный скролл в ней дороже вертикального.
Навигация — лента 44 px поверх экрана, слева бренд, справа строка состояния
станции.

Самостоятельный экран поиска — Этап 1.5 (S8) и здесь отсутствует; лента
показывает его выключенным, чтобы порядок сборки был виден оператору.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from . import kit
from .cg_view import CgView
from .deviation_view import DeviationView
from .item_view import ItemView
from .kit import tokens
from .reference_view import ReferenceView

#: Разделы будущих спринтов — видимы, но неактивны.
#:
#: Карточки здесь нет намеренно: она открывается **от конкретного отклонения**
#: (кнопка и двойной клик в списке, автооткрытие после регистрации), а не как
#: самостоятельный раздел — показывать её пустой не от чего.
#: «Поиск» — это конструктор произвольных запросов, Этап 1.5 (`Search.md` →
#: deep search); S5 ищет только от отклонения, которое на руках.
PLANNED_SECTIONS = (("Search", "not built yet"),)

BRAND = "MIS-QMS"

#: Подвал при пустом выборе говорит это, а не пустоту: пустая строка читается
#: как «подвал сломался», а не как «ничего не выбрано» (макет S1).
NO_SELECTION = "No selection"

#: Правая строка ленты: чем эта станция является. Не украшение — инструмент
#: автономен по решению об изоляции рабочих данных, и это должно быть видно.
STATION = "Offline · single station"


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.setWindowTitle("MIS-QMS — deviation database")
        self.setMinimumSize(tokens.WINDOW_MIN_WIDTH, tokens.WINDOW_MIN_HEIGHT)

        self.ribbon = kit.NavigationRibbon(
            BRAND, f"{STATION} · DB rev. {_db_revision(engine)}"
        )
        self.pages = QStackedWidget()

        self.reference_view = ReferenceView(engine)
        self.cg_view = CgView(engine)
        self.item_view = ItemView(engine)
        self.deviation_view = DeviationView(engine)
        self._add_section("Reference data", self.reference_view, icon="reference")
        self._add_section("Characteristic groups", self.cg_view, icon="groups")
        self._add_section("Items", self.item_view, icon="items")
        self._add_section("Deviations", self.deviation_view, icon="deviations")

        for title, note in PLANNED_SECTIONS:
            self.ribbon.add_section(title, enabled=False, note=note, icon="search")

        self.ribbon.sectionSelected.connect(self._switch)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        # Подвал: **выбранная запись** слева, путь к базе справа. Счётчик выдачи
        # живёт в подзаголовке экрана (макет S1…S6): одно и то же число дважды
        # на одном экране — то, ради чего его из подвала и убирали.
        self.summary = kit.status_label(NO_SELECTION)
        self.database = kit.status_label(f"Database: {engine.url}")
        self.statusBar().addWidget(self.summary, 1)
        self.statusBar().addPermanentWidget(self.database)

        self.ribbon.select(0)

    def _add_section(self, title: str, page: QWidget, *, icon: str = "") -> None:
        index = self.pages.count()
        self.ribbon.add_section(title, icon=icon)
        self.pages.addWidget(page)
        if hasattr(page, "statusChanged"):
            page.statusChanged.connect(self._on_status)
        if hasattr(page, "countChanged"):
            page.countChanged.connect(lambda count, row=index: self.ribbon.set_count(row, count))
        if hasattr(page, "selectionChanged"):
            page.selectionChanged.connect(self._on_selection)
        # Первое число берём сразу: экран уже прочитал базу в конструкторе, и
        # ждать переключения раздела, чтобы показать счётчик, незачем.
        if hasattr(page, "row_count"):
            self.ribbon.set_count(index, page.row_count())

    def _switch(self, row: int) -> None:
        if 0 <= row < self.pages.count():
            self.pages.setCurrentIndex(row)
            current = self.pages.currentWidget()
            # экран мог устареть, пока оператор был в соседнем разделе
            if hasattr(current, "reload"):
                current.reload()
            self._on_selection(getattr(current, "selection_text", lambda: "")())

    def _on_status(self, text: str) -> None:
        """Сводка экрана — она же подзаголовок; подвал её не показывает.

        Метод оставлен точкой подключения: экраны шлют сигнал, а окно решает,
        что с ним делать. Сегодня — ничего: счётчик уже виден в заголовке.
        """

    def _on_selection(self, text: str) -> None:
        """Выбранную запись в подвал пишет только **активный** экран.

        Соседний раздел перечитывается по переключению и тоже шлёт сигнал; без
        этой проверки подвал показывал бы выбор экрана, которого не видно.
        """
        if self.sender() in (None, self.pages.currentWidget()):
            self.summary.setText(text or NO_SELECTION)

    def select_section(self, row: int) -> None:
        """Публичный вход для тестов и снимков: выбрать раздел по порядку."""
        self.ribbon.select(row)


def _db_revision(engine: Engine) -> str:
    """Ревизия схемы для строки состояния — короткая, как её пишет Alembic."""
    from alembic.runtime.migration import MigrationContext

    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision() or "empty"
    except SQLAlchemyError:
        # Строка состояния не имеет права уронить окно: база может быть занята.
        return "unknown"


__all__ = ["BRAND", "PLANNED_SECTIONS", "STATION", "MainWindow"]
