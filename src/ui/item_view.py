"""Экран «Детали»: список заведённых деталей + кнопка добавления.

Колонка «Группы» выводится из маппингов размеров (`domain.items.groups_of`) —
отдельной Item↔CG таблицы в схеме нет.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
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

from .common import iso
from .item_dialog import ItemDialog

COLUMNS = ("Номер детали", "Тип", "Соединение", "Размерный класс", "Размеров", "Группы")


class ItemView(QWidget):
    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.add_button = QPushButton(iso("Добавить деталь…"))
        self.add_button.clicked.connect(self.add_item)
        self.status = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
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
                    item.item_number,
                    item.item_type.name if item.item_type else "",
                    item.connection_type.name,
                    item.size.name,
                    str(len(item.characteristics)),
                    ", ".join(group.name for group in groups_of(item)),
                )
                for item in list_items(session)
            ]

        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        self.status.setText(f"Деталей в базе: {len(rows)}")

    def add_item(self) -> None:
        dialog = ItemDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
