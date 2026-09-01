"""Экран «Детали»: список заведённых деталей, привязка к канону, позиции.

Колонка «Groups» выводится из маппингов размеров (`domain.items.groups_of`) —
отдельной Item↔CG таблицы в схеме нет.

Колонка `Characteristics` до наряда 0011 показывала **число без единого способа
его раскрыть** — тупик, который прогон вскрыл бы на шаге 5. Теперь это вход в
диалог позиций детали (решение В-7): отдельное окно, только чтение, а не
сплиттер — самый богатый детальный вид приложения (карточка отклонения) сделан
отдельным окном, и второго образца показа вложенного здесь не заводится.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem, QWidget
from sqlalchemy import Engine

from db.session import session_scope
from domain.items import groups_of, list_items

from . import kit
from .common import iso, joined, strip_iso
from .item_dialog import ItemDialog
from .item_positions_dialog import ItemPositionsDialog
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

COLUMNS = ("Item number", "Item type", "Connection", "Size class", "Characteristics", "Groups")

#: Число размеров — колонка счётчика: направление ей задаём явно, а выравнивание
#: остаётся левым — счётчик не сравнивают по величине (канон §6).
NUMERIC_COLUMNS = (4,)

EMPTY_TITLE = "No items yet"
EMPTY_BODY = (
    "An item is the catalogue number a deviation is addressed to. Add one here, "
    "or create it on the fly from the deviation form."
)


class ItemView(QWidget):
    statusChanged = Signal(str)

    #: Счётчик раздела для ленты. Справочники его не имеют намеренно: их шесть
    #: списков, и одно число рядом с разделом ни на что не отвечало бы.
    countChanged = Signal(int)

    #: Что сейчас выбрано — это и показывает подвал окна (макет S1…S6).
    #: Счётчик выдачи переехал в подзаголовок экрана: одно и то же число дважды
    #: на одном экране — то, ради чего его оттуда и убирали.
    selectionChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""
        self._rows_shown = 0

        self.table = kit.data_table(COLUMNS, numeric_columns=NUMERIC_COLUMNS)
        self.table.doubleClicked.connect(self.open_positions)
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)

        self.add_button = kit.primary("New item")
        self.positions_button = kit.secondary("Positions…")
        self.edit_button = kit.secondary("Edit item")
        self.map_button = kit.secondary("Mapping…")
        self.add_button.clicked.connect(self.add_item)
        self.positions_button.clicked.connect(self.open_positions)
        self.edit_button.clicked.connect(self.edit_item)
        self.map_button.clicked.connect(self.map_item)

        layout = kit.screen_layout(self)
        self.header = kit.section_header(
            "Items", "Catalogue numbers and their characteristics"
        )
        layout.addWidget(self.header)
        layout.addLayout(
            kit.button_row(
                self.add_button,
                self.positions_button,
                self.edit_button,
                self.map_button,
            )
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)

        self.table.itemSelectionChanged.connect(self._announce_selection)
        self.reload()

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            rows = [
                (
                    item.item_id,
                    item.item_number,
                    item.item_type.name if item.item_type else "",
                    item.connection_type.name,
                    item.size.name,
                    str(len(item.characteristics)),
                    # Составная ячейка: имена групп — самостоятельные токены
                    # (ревью Р-1). Обычный join оставлял запятые нейтральными,
                    # и при ивритском имени порядок групп читался неверно.
                    joined(*(group.name for group in groups_of(item)), sep=", "),
                )
                for item in list_items(session)
            ]

        self.table.setRowCount(len(rows))
        for row, (item_id, *values) in enumerate(rows):
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item_id)
                self.table.setItem(row, column, cell)

        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

        without_group = sum(1 for row in rows if not row[6])
        self._summary = strip_iso(
            joined(
                f"{len(rows)} items",
                f"{without_group} without a group" if without_group else "",
            )
        )
        kit.set_section_caption(self.header, self._summary)
        self.statusChanged.emit(self._summary)
        self._rows_shown = len(rows)
        self.countChanged.emit(self._rows_shown)

    def selection_text(self) -> str:
        """Подпись выбранной строки для подвала; пусто — «ничего не выбрано»."""
        row = self.table.currentRow()
        if row < 0:
            return ""
        return f"Selected {strip_iso(self.table.item(row, 0).text())}"

    def _announce_selection(self) -> None:
        self.selectionChanged.emit(self.selection_text())

    def row_count(self) -> int:
        """Сколько строк в списке — то же число, что уходит в ленту."""
        return self._rows_shown

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран.

        Своей строки состояния у раздела нет намеренно: подвал уже несёт
        счётчики и путь базы, и вторая такая же строка над ним была бы одним и
        тем же числом дважды на одном экране.
        """
        return self._summary

    # --- действия -------------------------------------------------------------

    def _selected_item_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Select an item in the list first.")
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def add_item(self) -> None:
        dialog = ItemDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def open_positions(self) -> None:
        """Раскрыть число в колонке `Characteristics` (решение В-7)."""
        item_id = self._selected_item_id()
        if item_id is None:
            return
        ItemPositionsDialog.run(self._engine, item_id, self)

    def edit_item(self) -> None:
        """Правка номера и классификаторов (ревью 0012, В-2).

        Размеры не трогаются: номер детали — её имя, а не идентичность, и
        характеристики ссылаются на `item_id`.
        """
        item_id = self._selected_item_id()
        if item_id is None:
            return
        if ItemDialog.run(self._engine, item_id, self):
            self.reload()

    def map_item(self) -> None:
        """Привязка размеров выбранной детали к канону — тот же диалог, что и в CG."""
        item_id = self._selected_item_id()
        if item_id is None:
            return

        cg_id = choose_cg_for_item(self, self._engine, item_id)
        if cg_id is None:
            return

        MappingDialog.run(self._engine, item_id, cg_id, self)
        self.reload()
