"""Создание CharacteristicGroup «на лету» (R3) — имя + g-позиции с геометрией.

Функциональный ввод, без визуального редактора: «шарики» и переиспользуемый UI
маппинга — это S3 (`docs/staging.md`).
"""

from __future__ import annotations

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
from sqlalchemy import Engine

from db.session import session_scope
from domain.errors import ValidationError
from domain.groups import GPositionSpec, create_group

from .common import directional, show_error, strip_iso

COLUMNS = ("g-position", "Nominal", "Tolerance +", "Tolerance −")


def parse_optional_number(text: str, field: str) -> float | None:
    """Пустое — None; запятая принимается как десятичный разделитель."""
    cleaned = strip_iso(text).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        raise ValidationError(f"{field}: “{cleaned}” is not a number.") from None


class CgDialog(QDialog):
    """Форма новой группы. После accept() имя группы — в `created_name`."""

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.created_name: str | None = None
        self.setWindowTitle("New characteristic group")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Implant_Con_375_C1")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Вся таблица числовая: индекс, номинал и оба допуска.
        directional(self.table, numeric_columns=(0, 1, 2, 3))

        add_row = QPushButton("Add position")
        drop_row = QPushButton("Remove position")
        add_row.clicked.connect(self.add_row)
        drop_row.clicked.connect(self.drop_row)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_row)
        row_buttons.addWidget(drop_row)
        row_buttons.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Group name:", self.name_edit)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Canonical positions (nominal and tolerance come from the drawing):"))
        layout.addWidget(self.table, 1)
        layout.addLayout(row_buttons)
        layout.addWidget(self.buttons)

        self.add_row()

    def add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        for column in range(1, len(COLUMNS)):
            self.table.setItem(row, column, QTableWidgetItem(""))

    def drop_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row >= 0:
            self.table.removeRow(row)

    def specs(self) -> list[GPositionSpec]:
        """Собрать g-позиции из таблицы; ошибки ввода — доменными сообщениями."""
        specs: list[GPositionSpec] = []
        for row in range(self.table.rowCount()):
            raw_index = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").strip()
            if not raw_index:
                raise ValidationError(f"Row {row + 1}: no g-position index given.")
            if not raw_index.isdigit():
                raise ValidationError(f"Row {row + 1}: index “{raw_index}” is not a whole number.")

            def cell(column: int) -> str:
                item = self.table.item(row, column)
                return item.text() if item else ""

            specs.append(
                GPositionSpec(
                    g_index=int(raw_index),
                    nominal=parse_optional_number(cell(1), f"Row {row + 1}, nominal"),
                    tol_plus=parse_optional_number(cell(2), f"Row {row + 1}, tolerance +"),
                    tol_minus=parse_optional_number(cell(3), f"Row {row + 1}, tolerance −"),
                )
            )
        return specs

    def save(self) -> None:
        try:
            specs = self.specs()
            with session_scope(self._engine) as session:
                group = create_group(session, self.name_edit.text(), specs)
                self.created_name = group.name
        except Exception as error:
            show_error(self, error, title="Group not created")
            return
        self.accept()
