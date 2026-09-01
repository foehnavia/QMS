"""Экран справочников — все 6 словарей: добавить / переименовать / удалить.

Защиты (`domain.reference`) поднимаются сюда сообщением, а не отказом молча:
занятое по FK значение и структурный дефолт `General` остаются на месте.

Наряд 0007 закрыл здесь находки прогона В-1…В-4. Наряд 0011 перевёл экран на
`kit`. Наряд 0012 привёл состав к макету S2: **список списков — панелью слева**,
значения — таблицей справа. Комбобокс отвечал на «какой словарь открыт», но не
отвечал на «какие словари есть и сколько в них значений» — а это первое, что
спрашивает оператор, впервые открывший экран.

Списки из интерфейса не заводятся: состав словарей — это модель (`docs/model/`),
а не данные. Панель прямо это говорит вместо кнопки «New list», которая обещала
бы невозможное.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.models import REFERENCE_MODELS
from db.session import session_scope
from domain.reference import (
    PROTECTED_NAMES,
    REFERENCE_TITLES,
    add_value,
    delete_value,
    is_protected,
    list_values,
    rename_value,
    usage_count,
)

from . import kit
from .common import directional, iso, joined, strip_iso
from .kit import tokens

COLUMNS = ("Value", "Used by", "State")

#: Счётчик ссылок — числовая колонка, но не величина: остаётся влево (канон §6).
NUMERIC_COLUMNS = (1,)

#: Структурный дефолт виден строкой, а не догадкой по отключённой кнопке.
STATE_DEFAULT = "default"

#: Общая часть подсказки — верна для всех шести словарей.
IN_USE_HINT = "A value referenced by records cannot be deleted."

#: Про `General` говорим **только там, где он есть** (находка прогона В-3):
#: на «Item type» структурного дефолта нет, и текст был не про этот экран.
GENERAL_HINT = (
    "“General” is a structural default: it is neither renamed nor deleted. "
)

LISTS_CAPTION = "Lists"
LISTS_NOTE = (
    "The set of lists comes from the model: adding a list is a model change, "
    "not a data entry."
)

EMPTY_TITLE = "This list has no values yet"
EMPTY_BODY = (
    "Until it is filled, the forms that pick from it have nothing to offer. "
    "Values are added here, not in the form that uses them."
)


class ReferenceView(QWidget):
    """Панель списков слева, значения выбранного списка — таблицей справа."""

    statusChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""

        self.lists = QListWidget()
        self.lists.setFixedWidth(tokens.PANEL_WIDTH)
        for model in REFERENCE_MODELS:
            item = QListWidgetItem(REFERENCE_TITLES[model])
            item.setData(Qt.ItemDataRole.UserRole, model)
            self.lists.addItem(item)
        self.lists.currentRowChanged.connect(lambda *_args: self.reload())

        self.values = kit.data_table(COLUMNS, numeric_columns=NUMERIC_COLUMNS)
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)
        self.hint = kit.hint()

        self.add_button = kit.primary("New value")
        self.rename_button = kit.secondary("Edit")
        self.delete_button = kit.danger("Delete")
        self.add_button.clicked.connect(self.add)
        self.rename_button.clicked.connect(self.rename)
        self.delete_button.clicked.connect(self.delete)

        self.header = kit.section_header("Reference data", "")

        panel = kit.boxed(
            kit.column(kit.section_caption(LISTS_CAPTION), self.lists, kit.hint(LISTS_NOTE))
        )
        panel.setFixedWidth(tokens.PANEL_WIDTH)
        table_side = kit.boxed(
            kit.column(
                self.values,
                self.empty,
                self.hint,
                kit.button_row(self.add_button, self.rename_button, self.delete_button),
            )
        )

        layout = kit.screen_layout(self)
        layout.addWidget(self.header)
        layout.addLayout(kit.split_row(panel, table_side), 1)

        self.lists.setCurrentRow(0)

    # --- данные ---------------------------------------------------------------

    @property
    def model(self) -> type:
        item = self.lists.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else REFERENCE_MODELS[0]

    def reload(self) -> None:
        """Перечитать выбранный справочник из БД."""
        model = self.model
        with session_scope(self._engine) as session:
            rows = [
                (
                    value.name,
                    usage_count(session, model, value),
                    is_protected(model, value.name),
                )
                for value in list_values(session, model)
            ]

        self.values.setRowCount(len(rows))
        for index, (name, used, protected) in enumerate(rows):
            # Значение бывает ивритским, счётчик и пометка — английские: каждая
            # ячейка держит своё направление сама (делегат таблицы).
            self.values.setItem(index, 0, QTableWidgetItem(iso(name)))
            self.values.setItem(index, 1, QTableWidgetItem(_used_label(used)))
            self.values.setItem(
                index, 2, QTableWidgetItem(STATE_DEFAULT if protected else "")
            )

        self.values.setVisible(bool(rows))
        self.empty.setVisible(not rows)

        self.hint.setText(iso(self._hint_for(model)))
        unused = sum(1 for _name, used, _protected in rows if not used)
        self._summary = strip_iso(
            joined(
                REFERENCE_TITLES[model],
                f"{len(rows)} values",
                f"{unused} not in use" if unused else "",
            )
        )
        kit.set_section_caption(self.header, self._summary)
        self.statusChanged.emit(self._summary)

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран."""
        return self._summary

    @staticmethod
    def _hint_for(model: type) -> str:
        """Текст подсказки под выбранный словарь, а не «вообще»."""
        if PROTECTED_NAMES.get(model):
            return GENERAL_HINT + IN_USE_HINT
        return IN_USE_HINT

    def _selected_name(self) -> str | None:
        row = self.values.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Nothing selected", "Select a value in the list first."
            )
            return None
        return strip_iso(self.values.item(row, 0).text())

    # --- действия -------------------------------------------------------------

    def add(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "New value", f"{REFERENCE_TITLES[self.model]} — name:"
        )
        if not accepted:
            return
        try:
            with session_scope(self._engine) as session:
                add_value(session, self.model, name)
        except Exception as error:  # доменная ошибка показывается как есть
            kit.show_error(self, error)
            return
        self.reload()

    def rename(self) -> None:
        current = self._selected_name()
        if current is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Edit value", "New name:", text=current
        )
        if not accepted:
            return
        try:
            with session_scope(self._engine) as session:
                value = self._fetch(session, current)
                rename_value(session, self.model, value, name)
        except Exception as error:
            kit.show_error(self, error)
            return
        self.reload()

    def delete(self) -> None:
        current = self._selected_name()
        if current is None:
            return
        confirmed = QMessageBox.question(
            self, "Delete value", f"Delete “{current}” from this reference list?"
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            with session_scope(self._engine) as session:
                value = self._fetch(session, current)
                delete_value(session, self.model, value)
        except Exception as error:
            kit.show_error(self, error, title="Not deleted")
            return
        self.reload()

    def _fetch(self, session, name: str):
        from sqlalchemy import select

        return session.scalar(select(self.model).where(self.model.name == name))


def _used_label(used: int) -> str:
    """Сколько записей ссылается на значение; ноль — прочерк, а не «0 records»."""
    return iso(f"{used} records") if used else "—"


__all__ = ["COLUMNS", "GENERAL_HINT", "IN_USE_HINT", "ReferenceView", "directional"]
