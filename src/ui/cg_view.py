"""Раздел «Группы характеристик» — список групп, редактор, привязка детали."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.session import session_scope
from domain.groups import list_groups
from domain.items import list_items

from .cg_dialog import CgDialog
from .cg_editor import CgEditor
from .common import iso
from .mapping_dialog import MappingDialog
from .pickers import pick_item

COLUMNS = ("Группа", "Позиций", "Чертёж")


class CgView(QWidget):
    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_editor)

        self.create_button = QPushButton(iso("Создать…"))
        self.editor_button = QPushButton(iso("Редактор…"))
        self.bind_button = QPushButton(iso("Привязать деталь…"))
        self.create_button.clicked.connect(self.create_group)
        self.editor_button.clicked.connect(self.open_editor)
        self.bind_button.clicked.connect(self.bind_item)

        self.status = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.editor_button)
        buttons.addWidget(self.bind_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)

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
            self.table.setItem(row, 2, QTableWidgetItem("есть" if has_drawing else "—"))

        self.status.setText(f"Групп в базе: {len(rows)}")

    def _selected_cg_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите группу в списке.")
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
                self, "Нет деталей", "Сначала заведите деталь в разделе «Детали»."
            )
            return

        item_id = pick_item(self, items)
        if item_id is not None:
            MappingDialog.run(self._engine, item_id, cg_id, self)
            self.reload()
