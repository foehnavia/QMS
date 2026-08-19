"""Форма «Добавить деталь»: классификаторы + привязка к CG с сидом размеров.

`connection_type` и `size` предвыбраны как `General` — деталь заводится и когда
специфика ещё не важна (`Item.md`). При выборе группы её g-позиции показываются
таблицей: номер размера оператор проставляет сам на каждую позицию — он берётся
с чертежа детали и с индексом g-позиции совпадает редко (решение Cowork по
заметке Б наряда 0002), поэтому автоподстановки нет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select

from db.models import GENERAL, CharacteristicGroup, RefConnectionType, RefItemType, RefSize
from db.session import session_scope
from domain.groups import list_groups
from domain.items import create_item, seed_cg_characteristics
from domain.reference import list_values

from .cg_dialog import CgDialog
from .common import bind_direction, directional, iso, show_error

NO_GROUP = "— no group —"
NO_TYPE = "— not set —"
COLUMNS = ("g-position", "Local number", "Nominal", "Tolerance")


class ItemDialog(QDialog):
    """Форма новой детали. После accept() номер детали — в `created_number`."""

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.created_number: str | None = None
        self.setWindowTitle("Add item")

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText('e.g. C1-08375A (מק"ט)')
        bind_direction(self.number_edit)

        self.item_type = _combo()
        self.connection_type = _combo()
        self.size = _combo()
        self.group = _combo()
        self.group.currentIndexChanged.connect(self.reload_positions)

        new_group = QPushButton(iso("Create group…"))
        new_group.clicked.connect(self.create_group)

        group_row = QHBoxLayout()
        group_row.addWidget(self.group, 1)
        group_row.addWidget(new_group)

        self.positions = QTableWidget(0, len(COLUMNS))
        self.positions.setHorizontalHeaderLabels(COLUMNS)
        self.positions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        directional(self.positions, numeric_columns=(0,), magnitude_columns=(2, 3))

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Item number:", self.number_edit)
        form.addRow("Item type:", self.item_type)
        form.addRow("Connection type:", self.connection_type)
        form.addRow("Size class:", self.size)
        form.addRow("Characteristic group:", group_row)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(
            QLabel("Group positions — set the local number from the item drawing for each:")
        )
        layout.addWidget(self.positions, 1)
        layout.addWidget(self.buttons)

        self.reload_reference()

    # --- наполнение ------------------------------------------------------------

    def reload_reference(self, keep_group: str | None = None) -> None:
        """Перечитать справочники и список групп."""
        with session_scope(self._engine) as session:
            item_types = [value.name for value in list_values(session, RefItemType)]
            connections = [value.name for value in list_values(session, RefConnectionType)]
            sizes = [value.name for value in list_values(session, RefSize)]
            groups = [group.name for group in list_groups(session)]

        _fill(self.item_type, [NO_TYPE, *item_types], NO_TYPE)
        _fill(self.connection_type, connections, GENERAL)
        _fill(self.size, sizes, GENERAL)
        _fill(self.group, [NO_GROUP, *groups], keep_group or NO_GROUP)
        self.reload_positions()

    def reload_positions(self) -> None:
        """Показать g-позиции выбранной группы с предзаполненными номерами."""
        self.positions.setRowCount(0)
        name = self.group.currentText()
        if name == NO_GROUP:
            return

        with session_scope(self._engine) as session:
            group = session.scalar(
                select(CharacteristicGroup).where(CharacteristicGroup.name == name)
            )
            rows = [
                (
                    position.g_index,
                    _format_number(position.nominal),
                    _format_tolerance(position.tol_plus, position.tol_minus),
                )
                for position in sorted(group.positions, key=lambda p: p.g_index)
            ]

        self.positions.setRowCount(len(rows))
        for row, (g_index, nominal, tolerance) in enumerate(rows):
            self.positions.setItem(row, 0, _readonly(f"g{g_index}", g_index))
            # номер размера не подставляется: он с чертежа детали и с g_index
            # совпадает редко (решение Cowork по заметке Б наряда 0002)
            self.positions.setItem(row, 1, QTableWidgetItem(""))
            self.positions.setItem(row, 2, _readonly(nominal))
            self.positions.setItem(row, 3, _readonly(tolerance))

    def local_numbers(self) -> dict[int, str]:
        numbers: dict[int, str] = {}
        for row in range(self.positions.rowCount()):
            g_index = self.positions.item(row, 0).data(Qt.ItemDataRole.UserRole)
            cell = self.positions.item(row, 1)
            numbers[g_index] = cell.text() if cell else ""
        return numbers

    # --- действия --------------------------------------------------------------

    def create_group(self) -> None:
        """R3 — недостающую группу можно завести прямо отсюда."""
        dialog = CgDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_name:
            self.reload_reference(keep_group=dialog.created_name)

    def save(self) -> None:
        item_type_name = self.item_type.currentText()
        group_name = self.group.currentText()
        try:
            with session_scope(self._engine) as session:
                item = create_item(
                    session,
                    item_number=self.number_edit.text(),
                    item_type=(
                        None
                        if item_type_name == NO_TYPE
                        else _by_name(session, RefItemType, item_type_name)
                    ),
                    connection_type=_by_name(
                        session, RefConnectionType, self.connection_type.currentText()
                    ),
                    size=_by_name(session, RefSize, self.size.currentText()),
                )
                if group_name != NO_GROUP:
                    group = session.scalar(
                        select(CharacteristicGroup).where(CharacteristicGroup.name == group_name)
                    )
                    seed_cg_characteristics(session, item, group, self.local_numbers())
                self.created_number = item.item_number
        except Exception as error:
            show_error(self, error)
            return
        self.accept()


# --- мелкие помощники ------------------------------------------------------------


def _combo():
    from PySide6.QtWidgets import QComboBox

    return QComboBox()


def _fill(combo, names: list[str], preselect: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(names)
    index = combo.findText(preselect)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def _readonly(text: str, payload=None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if payload is not None:
        item.setData(Qt.ItemDataRole.UserRole, payload)
    return item


def _format_number(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _format_tolerance(plus: float | None, minus: float | None) -> str:
    if plus is None and minus is None:
        return ""
    # изолят: иначе ведущие знаки в RTL-контексте переставляются
    return iso(f"+{_format_number(plus) or '0'} / {_format_number(minus) or '0'}")


def _by_name(session, model: type, name: str):
    return session.scalar(select(model).where(model.name == name))
