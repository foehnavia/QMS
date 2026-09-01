"""Раздел «Группы характеристик» — список групп, редактор, привязка детали."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem, QWidget
from sqlalchemy import Engine

from db.session import session_scope
from domain.groups import list_groups
from domain.items import list_items

from . import kit
from .cg_dialog import CgDialog
from .cg_editor import CgEditor
from .mapping_dialog import MappingDialog
from .pickers import pick_item

COLUMNS = ("Group", "Positions", "Drawing")

#: Счётчик позиций — числовая колонка, но не величина: остаётся влево.
NUMERIC_COLUMNS = (1,)

NO_DRAWING = "—"
HAS_DRAWING = "yes"

EMPTY_TITLE = "No characteristic groups yet"
EMPTY_BODY = (
    "A group is the drawing shared by a family of items: canonical positions "
    "with nominal and tolerance. Items bind their own numbers to it."
)


class CgView(QWidget):
    statusChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""

        self.table = kit.data_table(COLUMNS, numeric_columns=NUMERIC_COLUMNS)
        self.table.doubleClicked.connect(self.open_editor)
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)

        self.create_button = kit.primary("Create…")
        self.editor_button = kit.secondary("Editor…")
        self.bind_button = kit.secondary("Bind item…")
        self.create_button.clicked.connect(self.create_group)
        self.editor_button.clicked.connect(self.open_editor)
        self.bind_button.clicked.connect(self.bind_item)

        layout = kit.screen_layout(self)
        layout.addWidget(
            kit.section_header(
                "Characteristic groups",
                "The canon a family of items shares — g-positions and their geometry",
            )
        )
        layout.addLayout(
            kit.button_row(self.create_button, self.editor_button, self.bind_button)
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)

        self.reload()

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            rows = [
                (group.cg_id, group.name, len(group.positions), bool(group.drawing))
                for group in list_groups(session)
            ]

        self.table.setRowCount(len(rows))
        for row, (cg_id, name, positions, has_drawing) in enumerate(rows):
            first = QTableWidgetItem(name)
            first.setData(Qt.ItemDataRole.UserRole, cg_id)
            self.table.setItem(row, 0, first)
            self.table.setItem(row, 1, QTableWidgetItem(str(positions)))
            self.table.setItem(
                row, 2, QTableWidgetItem(HAS_DRAWING if has_drawing else NO_DRAWING)
            )

        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

        self._summary = f"Groups in the database: {len(rows)}"
        self.statusChanged.emit(self._summary)

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран.

        Своей строки состояния у раздела нет намеренно: подвал уже несёт
        счётчики и путь базы, и вторая такая же строка над ним была бы одним и
        тем же числом дважды на одном экране.
        """
        return self._summary

    def _selected_cg_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Select a group in the list first.")
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def create_group(self) -> None:
        dialog = CgDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def open_editor(self) -> None:
        cg_id = self._selected_cg_id()
        if cg_id is None:
            return
        editor = CgEditor(self._engine, cg_id, self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def bind_item(self) -> None:
        cg_id = self._selected_cg_id()
        if cg_id is None:
            return
        with session_scope(self._engine) as session:
            items = [(item.item_id, item.item_number) for item in list_items(session)]
        if not items:
            QMessageBox.information(
                self, "No items", "Create an item first — section “Items”."
            )
            return

        item_id = pick_item(self, items)
        if item_id is not None:
            MappingDialog.run(self._engine, item_id, cg_id, self)
            self.reload()
