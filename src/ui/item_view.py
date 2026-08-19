"""Экран «Детали»: список заведённых деталей + кнопка добавления.

Колонка «Группы» выводится из маппингов размеров (`domain.items.groups_of`) —
отдельной Item↔CG таблицы в схеме нет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.session import session_scope
from domain.items import groups_of, list_items

from .common import directional, iso, joined
from .item_dialog import ItemDialog
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

COLUMNS = ("Item number", "Item type", "Connection", "Size class", "Characteristics", "Groups")


class ItemView(QWidget):
    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Число размеров — колонка счётчика: направление ей задаём явно.
        directional(self.table, numeric_columns=(4,))

        self.add_button = QPushButton(iso("Add item…"))
        self.add_button.clicked.connect(self.add_item)
        self.map_button = QPushButton(iso("Bind to canon…"))
        self.map_button.clicked.connect(self.map_item)
        self.status = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.map_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)

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

        self.status.setText(f"Items in the database: {len(rows)}")

    def add_item(self) -> None:
        dialog = ItemDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def map_item(self) -> None:
        """Привязка размеров выбранной детали к канону — тот же диалог, что и в CG."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Select an item in the list first.")
            return
        item_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        cg_id = choose_cg_for_item(self, self._engine, item_id)
        if cg_id is None:
            return

        MappingDialog.run(self._engine, item_id, cg_id, self)
        self.reload()
