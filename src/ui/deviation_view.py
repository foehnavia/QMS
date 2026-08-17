"""Раздел «Отклонения»: список записей и четыре действия над ними.

Решение вынесено в **отдельное действие** (кнопка «Решение…»), а не в форму
регистрации: порядок канона — регистрация шаг 3, решение шаг 8, после изучения
прецедентов. В S5 то же действие переедет в карточку отклонения без переделки —
`DecisionDialog` ничего про этот раздел не знает.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from db.models import Deviation
from db.session import session_scope
from domain.deviations import delete_deviation, list_deviations

from .common import decision_dev_label, iso, show_error
from .decision_dialog import DecisionDialog
from .deviation_dialog import DeviationDialog

COLUMNS = (
    "Номер",
    "Деталь",
    "WO",
    "Дата",
    "Кол-во",
    "Решение",
    "Находок",
    "Исследований",
)


class DeviationView(QWidget):
    """Список отклонений — вход в регистрацию, правку, решение и удаление."""

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.open_deviation)

        self.add_button = QPushButton(iso("Добавить отклонение…"))
        self.open_button = QPushButton(iso("Открыть…"))
        self.decision_button = QPushButton(iso("Решение…"))
        self.delete_button = QPushButton("Удалить")
        self.add_button.clicked.connect(self.add_deviation)
        self.open_button.clicked.connect(self.open_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.delete_button.clicked.connect(self.delete_deviation)

        self.status = QLabel()

        buttons = QHBoxLayout()
        for button in (
            self.add_button,
            self.open_button,
            self.decision_button,
            self.delete_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)

        self.reload()

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            rows = list_deviations(session)

        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                iso(row.dev_number),
                iso(row.item_number),
                iso(row.wo),
                iso(f"{row.date:%d.%m.%Y}"),
                iso(str(row.quantity)),
                decision_dev_label(row.decision_dev),
                str(row.findings),
                str(row.inspections),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
                self.table.setItem(index, column, cell)

        undecided = sum(1 for row in rows if row.decision_dev is None)
        self.status.setText(
            f"Отклонений в базе: {len(rows)} · без решения: {undecided}"
        )

    # --- действия ---------------------------------------------------------------

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Не выбрано", "Сначала выберите отклонение в списке."
            )
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def add_deviation(self) -> None:
        if DeviationDialog.run(self._engine, None, self):
            self.reload()

    def open_deviation(self) -> None:
        deviation_id = self._selected()
        if deviation_id is None:
            return
        DeviationDialog.run(self._engine, deviation_id, self)
        # Перечитываем всегда: исследования пишутся по действию, поэтому
        # счётчики меняются и когда форму закрыли «Отменой».
        self.reload()

    def set_decision(self) -> None:
        """Шаг 8 — отдельным действием, как требует порядок процесса."""
        deviation_id = self._selected()
        if deviation_id is None:
            return
        if DecisionDialog.run(self._engine, deviation_id, self):
            self.reload()

    def delete_deviation(self) -> None:
        deviation_id = self._selected()
        if deviation_id is None:
            return

        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, deviation_id)
            number = deviation.dev_number
            findings = len(deviation.findings)
            inspections = len(deviation.inspections)

        # Единица целостности — отклонение целиком, поэтому и удаляется целиком;
        # цену показываем до удаления, а не после.
        if (
            QMessageBox.question(
                self,
                "Удалить отклонение?",
                f"Удалить {number}? Вместе с ним исчезнут находок: {findings}, "
                f"исследований: {inspections}.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            with session_scope(self._engine) as session:
                delete_deviation(session, session.get(Deviation, deviation_id))
        except Exception as error:
            show_error(self, error, title="Отклонение не удалено")
            return
        self.reload()
