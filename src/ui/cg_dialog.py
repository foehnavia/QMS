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

from .common import russian_buttons, show_error, strip_iso

COLUMNS = ("g-позиция", "Номинал", "Допуск +", "Допуск −")


def parse_optional_number(text: str, field: str) -> float | None:
    """Пустое — None; запятая принимается как десятичный разделитель."""
    cleaned = strip_iso(text).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        raise ValidationError(f"{field}: «{cleaned}» — не число.") from None


class CgDialog(QDialog):
    """Форма новой группы. После accept() имя группы — в `created_name`."""

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.created_name: str | None = None
        self.setWindowTitle("Новая группа характеристик")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("например Implant_Con_375_C1")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        add_row = QPushButton("Добавить позицию")
        drop_row = QPushButton("Убрать позицию")
        add_row.clicked.connect(self.add_row)
        drop_row.clicked.connect(self.drop_row)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_row)
        row_buttons.addWidget(drop_row)
        row_buttons.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        russian_buttons(self.buttons)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Название группы:", self.name_edit)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Канонические позиции (номинал и допуск — с чертежа):"))
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
                raise ValidationError(f"Строка {row + 1}: не задан индекс g-позиции.")
            if not raw_index.isdigit():
                raise ValidationError(f"Строка {row + 1}: индекс «{raw_index}» — не целое число.")

            def cell(column: int) -> str:
                item = self.table.item(row, column)
                return item.text() if item else ""

            specs.append(
                GPositionSpec(
                    g_index=int(raw_index),
                    nominal=parse_optional_number(cell(1), f"Строка {row + 1}, номинал"),
                    tol_plus=parse_optional_number(cell(2), f"Строка {row + 1}, допуск +"),
                    tol_minus=parse_optional_number(cell(3), f"Строка {row + 1}, допуск −"),
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
            show_error(self, error, title="Группа не создана")
            return
        self.accept()
