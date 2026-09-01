"""Раздел «Отклонения»: список записей и четыре действия над ними.

Решение вынесено в **отдельное действие** (кнопка «Decision…»), а не в форму
регистрации: порядок канона — регистрация шаг 3, решение шаг 8, после изучения
прецедентов. В S5 то же действие переехало в карточку отклонения без переделки —
`DecisionDialog` ничего про этот раздел не знает.

Состав колонок доведён нарядом 0011 §4 до языка макета: `Quantity` → `Dev. qty`
(средний из трёх уровней количества), `Findings` встал **перед** `Decision`,
появилась колонка `Explanation`. Механик эталонного макета — поиска, срезов,
чипов фильтров, выбора колонок, экспорта и раскрытия строки в три уровня —
здесь **нет**: они остаются отдельной задачей после прогона (наряд 0011 §4).
Поэтому `Inspections` и осталась своей колонкой: в макете она уходит внутрь
раскрытия, а раскрытия в сборке нет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.models import Deviation
from db.session import session_scope
from domain.deviations import delete_deviation, list_deviations

from . import kit
from .card_dialog import CardDialog
from .common import decision_dev_label, iso
from .decision_dialog import DecisionDialog
from .deviation_dialog import DeviationDialog
from .kit.pills import DECISION_ROLE, DecisionPillDelegate

COLUMNS = (
    "Number",
    "Item",
    "WO",
    "Date",
    "Dev. qty",
    "Findings",
    "Decision",
    "Explanation",
    "Inspections",
)

#: Колонки, которым направление задаётся не по содержимому: дата, количество
#: и счётчики читаются слева направо в любой строке (наряд 0007 §4а, канон §6).
NUMERIC_COLUMNS = (3, 4, 5, 8)

#: Вправо — только `Dev. qty`: её и сравнивают по величине вниз по столбцу.
#: Счётчики находок и исследований остаются влево — сравнивать нечего, а левый
#: край держит их под подписью колонки (канон §6).
MAGNITUDE_COLUMNS = (4,)

DECISION_COLUMN = 6

EMPTY_TITLE = "No deviations registered yet"
EMPTY_BODY = (
    "Registration is step 3 of the process: an item, a WO and at least one "
    "finding. Precedents start working from the first decided deviation."
)


class DeviationView(QWidget):
    """Список отклонений — вход в регистрацию, правку, решение и удаление."""

    statusChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
        )
        # Двойной клик ведёт в карточку, а не в правку: карточка — рабочий
        # экран отклонения, правка из неё в одном нажатии (решение Cowork 1).
        self.table.doubleClicked.connect(self.open_card)
        # Исход рисуется пилюлей — поверх общего делегата направления: колонка
        # английская и всегда LTR, спорить им не о чем (канон §1).
        self.table.setItemDelegateForColumn(DECISION_COLUMN, DecisionPillDelegate(self.table))

        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)

        # Одно основное действие на экран (канон §4): регистрация. Всё, что
        # действует на выбранную строку, — вторичное.
        self.add_button = kit.primary("Add deviation…")
        self.card_button = kit.secondary("Card…")
        self.open_button = kit.secondary("Open…")
        self.decision_button = kit.secondary("Decision…")
        self.delete_button = kit.danger("Delete")
        self.add_button.clicked.connect(self.add_deviation)
        self.card_button.clicked.connect(self.open_card)
        self.open_button.clicked.connect(self.open_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.delete_button.clicked.connect(self.delete_deviation)

        layout = kit.screen_layout(self)
        layout.addWidget(
            kit.section_header(
                "Deviations",
                "Production non-conformances — registration, decision, precedents",
            )
        )
        layout.addLayout(
            kit.button_row(
                self.add_button,
                self.card_button,
                self.open_button,
                self.decision_button,
                self.delete_button,
            )
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)

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
                str(row.findings),
                decision_dev_label(row.decision_dev),
                _one_line(row.explanation),
                str(row.inspections),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
                if column == DECISION_COLUMN:
                    # Код исхода — рядом с подписью: пилюлю красит он, а не
                    # разбор человеческого текста.
                    cell.setData(DECISION_ROLE, row.decision_dev)
                if column == 7 and row.explanation:
                    # Обоснование в строке урезано, целиком — в подсказке: это
                    # главный текст прецедента, терять его нельзя.
                    cell.setToolTip(row.explanation)
                self.table.setItem(index, column, cell)

        # Пустая таблица без объяснения — то, как оператор заключает «записей
        # не было» из экрана, который просто ничего не показал (канон §8).
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

        undecided = sum(1 for row in rows if row.decision_dev is None)
        self._summary = (
            f"Deviations in the database: {len(rows)} · undecided: {undecided}"
        )
        self.statusChanged.emit(self._summary)

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран.

        Своей строки состояния у раздела нет намеренно: подвал уже несёт
        счётчики и путь базы, и вторая такая же строка над ним была бы одним и
        тем же числом дважды на одном экране.
        """
        return self._summary

    # --- действия ---------------------------------------------------------------

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Nothing selected", "Select a deviation in the list first."
            )
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def add_deviation(self) -> None:
        """Регистрация; карточка нового отклонения всплывает сама.

        Канон: «opens as soon as a deviation is entered» (`DeviationCard.md`) —
        именно тогда прецеденты и нужны. При правке существующего не открываем:
        оператор уже знает, что там.
        """
        dialog = DeviationDialog(self._engine, None, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.reload()
        if dialog.deviation_id is not None:
            CardDialog.run(self._engine, dialog.deviation_id, self)
            self.reload()

    def open_card(self) -> None:
        """Карточка выбранного отклонения — рабочий экран с прецедентами."""
        deviation_id = self._selected()
        if deviation_id is None:
            return
        CardDialog.run(self._engine, deviation_id, self)
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
                "Delete deviation?",
                f"Delete {number}? It takes with it findings: {findings}, "
                f"inspections: {inspections}.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            with session_scope(self._engine) as session:
                delete_deviation(session, session.get(Deviation, deviation_id))
        except Exception as error:
            kit.show_error(self, error, title="Deviation not deleted")
            return
        self.reload()


def _one_line(text: str | None) -> str:
    """Обоснование в одну строку — в таблице многострочный текст рвёт вёрстку."""
    return " ".join((text or "").split())
