"""Все отклонения одной детали — по всем её ревизиям (QMS-017, наряд 0025 §5).

Открывается из карточки детали. Отвечает на вопрос «что вообще случалось с этой
деталью», а не «что случалось с этим чертежом»: выпуск чертежа меняется чаще, чем
деталь, и история детали не должна дробиться вместе с ним.

**Фильтров здесь нет и не должно быть в этом наряде.** Они часть общей фильтровой
машинерии экрана списка (часть 2 `Q-14`, после S6); собранные наспех отдельно, они
разошлись бы с ней в поведении, а сходить их пришлось бы вручную.

Строки прежних ревизий несут ту же пометку, что и прецеденты, и по тому же правилу
(`Search.md` v1.04): знак `!` означает одно и то же на всех экранах, поэтому и берётся
из одного места — `ui.common`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QTableWidgetItem, QWidget
from sqlalchemy import Engine

from db.models import Item
from db.session import session_scope
from domain.deviations import list_deviations
from domain.revisions import current_revision

from . import kit
from .common import decision_dev_label, iso, mark_other_revision
from .kit import tokens
from .kit.pills import DECISION_ROLE, DecisionPillDelegate

COLUMNS = (
    "Deviation",
    "Revision",
    "Date",
    "WO",
    "Dev. qty",
    "Decision",
    "Findings",
    "Insp.",
)

#: Дата и счётчики — числовые; ревизия **не** числовая: обозначение это
#: идентификатор, а не величина (`CLAUDE.md` §9).
NUMERIC_COLUMNS = (2, 4, 6, 7)
MAGNITUDE_COLUMNS = ()

DECISION_COLUMN = 5
REVISION_COLUMN = 1

EMPTY_TITLE = "No deviations on this item yet"
EMPTY_BODY = (
    "Deviations are registered from the Deviations section. Every one of them "
    "records the drawing revision it was raised against."
)


class ItemDeviationsDialog(QDialog):
    """Список отклонений детали. Только чтение — правка через карточку отклонения."""

    def __init__(
        self, engine: Engine, item_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_MEDIUM)

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
        )
        self.table.setItemDelegateForColumn(DECISION_COLUMN, DecisionPillDelegate(self.table))
        self.table.doubleClicked.connect(lambda *_: self.open_card())

        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)
        self.status = kit.status_label()

        self.card_button = kit.secondary("Open deviation…")
        self.card_button.clicked.connect(self.open_card)

        self.buttons = kit.dialog_buttons(accept="Close", reject="Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(self.buttons.StandardButton.Cancel).setVisible(False)

        layout = kit.dialog_layout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)
        layout.addLayout(kit.button_row(self.card_button))
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, item_id: int, parent: QWidget | None = None) -> None:
        cls(engine, item_id, parent=parent).exec()

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            self.setWindowTitle(f"Deviations — {item.item_number}")
            current = current_revision(item)
            current_designation = current.designation if current else None
            rows = list_deviations(session, item=item)

        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                iso(row.dev_number),
                iso(row.revision),
                iso(f"{row.date:%d.%m.%Y}"),
                iso(row.wo),
                str(row.quantity),
                decision_dev_label(row.decision_dev, short=True),
                str(row.findings),
                str(row.inspections),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
                if column == DECISION_COLUMN:
                    cell.setData(DECISION_ROLE, row.decision_dev)
                if column == REVISION_COLUMN and row.revision != current_designation:
                    # Та же функция, что в прецедентах: один и тот же факт не имеет
                    # права выглядеть на двух экранах по-разному. Только начертание —
                    # цвет означает «нет канона» и на колонку ревизии не попадает.
                    mark_other_revision(cell, row.revision, current_designation)
                self.table.setItem(index, column, cell)

        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        past = sum(1 for row in rows if row.revision != current_designation)
        self.status.setText(
            f"{len(rows)} deviations, all revisions of this item"
            + (f" · {past} on an earlier issue" if past else "")
        )

    def selected_deviation(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        cell = self.table.item(row, 0)
        return cell.data(Qt.ItemDataRole.UserRole) if cell is not None else None

    def open_card(self) -> None:
        from .card_dialog import CardDialog  # noqa: PLC0415

        deviation_id = self.selected_deviation()
        if deviation_id is None:
            return
        CardDialog.run(self._engine, deviation_id, parent=self)
        self.reload()
