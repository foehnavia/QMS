"""Создание CharacteristicGroup «на лету» (R3) — имя + g-позиции с геометрией.

**Число позиций задаётся здесь** (наряд 0014): оператор смотрит на чертёж,
видит на нём метки `G1…GN` и называет `N` — таблица разворачивается сразу на
`g1…gN` пустыми значениями, и остаётся вписать в неё номинал и допуски с
выносок. Добавление и удаление строки по одной никуда не делись: чертёж бывает
дочитан не сразу.

**Индекс g-позиции руками не вводится** (ратификация В-8, наряд 0010 §10): он
выдаётся как `max + 1` и больше не меняется никогда. Основание — не ссылочная
целостность (её держит суррогатный ключ), а общий словарь чертежа и базы: `g5`
написан на чертеже, в протоколе контроля и в записке оператора, и ярлык, молча
поменявший смысл между ревизиями, ломает ровно ту функцию, ради которой
инструмент существует, — сравнение через время.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QSpinBox,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.session import session_scope
from domain.errors import ValidationError
from domain.groups import GPositionSpec, create_group

from . import kit
from .common import numeric_field, position_index, position_label, strip_iso
from .kit import tokens

#: Подписи по ISO 286 (решение 2026-09-02): `Tolerance +` / `Tolerance −`
#: обещали знак, которого не гарантируют — у посадки с натягом оба
#: отклонения плюсовые. Имена полей базы (`tol_plus`/`tol_minus`) не тронуты.
COLUMNS = ("g-position", "Nominal", "Upper deviation", "Lower deviation")

#: Индекс позиции — идентификатор, влево; вправо выравниваются величины.
NUMERIC_COLUMNS = (0,)
MAGNITUDE_COLUMNS = (1, 2, 3)

#: Сколько позиций форма готова развернуть разом. Не значение оформления, а
#: предел ввода: чертежей с сотнями выносок не бывает, а опечатка «1000» иначе
#: развернула бы таблицу, которую оператор будет удалять строку за строкой.
MAX_POSITIONS = 200


#: Знаки, которые приложение **показывает** и обязано принять обратно.
#:
#: Минус канона `−` (U+2212) стоит в ячейке предельных отклонений
#: `+0.05 / −0.05` и на переключателе направления. Оператор копирует значение из
#: показанной ячейки в редактируемую — и без этой нормализации получает
#: «`−0.05` is not a number»: сообщение про текст, который выглядит совершенно
#: нормальным числом (ревью 0011, Р-1). Тире `–` (U+2013) добавлено по той же
#: причине: его подставляют текстовые редакторы, из которых значение приходит.
_ASCII_EQUIVALENTS = {
    ",": ".",
    "−": "-",  # U+2212 minus sign
    "–": "-",  # U+2013 en dash
}


def normalise_number(text: str) -> str:
    """Привести введённое к тому, что понимает `float`.

    Единственная точка нормализации: её зовут все формы, которые принимают
    число, — новая группа, редактор группы, находка.
    """
    cleaned = strip_iso(text).strip()
    for shown, ascii_form in _ASCII_EQUIVALENTS.items():
        cleaned = cleaned.replace(shown, ascii_form)
    return cleaned


def parse_optional_number(text: str, field: str) -> float | None:
    """Пустое — None; запятая и знаки минуса приводятся к ASCII."""
    cleaned = normalise_number(text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        raise ValidationError(f"{field}: “{cleaned}” is not a number.") from None


class CgDialog(QDialog):
    """Форма новой группы. После accept() имя группы — в `created_name`."""

    def __init__(self, engine: Engine, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self.created_name: str | None = None
        self.setWindowTitle("New characteristic group")
        self.resize(tokens.DIALOG_MEDIUM, tokens.DIALOG_HEIGHT_MEDIUM)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Implant_Con_375_C1")

        #: Сколько выносок на чертеже — столько строк в таблице.
        #: `numeric_field`: текст внутри редактора рисует Qt, обернуть его
        #: изолятом нечем, и в RTL-окружении число переставилось бы (§9).
        self.count = numeric_field(QSpinBox())
        self.count.setRange(1, MAX_POSITIONS)
        self.count.setValue(1)
        self.count.valueChanged.connect(self.set_position_count)

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
            read_only=False,
        )

        add_row = kit.secondary("Add position")
        drop_row = kit.secondary("Remove position")
        add_row.clicked.connect(self.add_row)
        drop_row.clicked.connect(self.drop_row)

        self.buttons = kit.dialog_buttons(accept="Create group")
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = kit.stretching_form()
        form.addRow("Group name:", self.name_edit)
        form.addRow("Positions on the drawing:", self.count)

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        layout.addWidget(
            kit.hint(
                "State how many positions the drawing carries — the table is laid "
                "out at once for g1…gN. Nominal and the limit deviations come from "
                "the drawing and may stay empty; each deviation carries its own "
                "sign, and the index is issued automatically and never reused."
            )
        )
        layout.addWidget(self.table, 1)
        layout.addLayout(kit.button_row(add_row, drop_row))
        layout.addWidget(self.buttons)

        self.set_position_count(self.count.value())

    def set_position_count(self, count: int) -> None:
        """Развернуть таблицу на `g1…gN` — по числу выносок на чертеже.

        Уже введённые строки не пересобираются: оператор мог назвать число
        после того, как начал вписывать номиналы, и стирать их значило бы
        наказывать за порядок действий. Лишние снимаются с хвоста — там стоят
        самые молодые индексы.
        """
        while self.table.rowCount() < count:
            self._append_row()
        while self.table.rowCount() > count:
            self.table.removeRow(self.table.rowCount() - 1)

    def add_row(self) -> None:
        self._append_row()
        self._sync_count()

    def _append_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, _issued_index(self._next_index()))
        for column in range(1, len(COLUMNS)):
            self.table.setItem(row, column, QTableWidgetItem(""))

    def _sync_count(self) -> None:
        """Счётчик и таблица — одно и то же число, кто бы его ни менял.

        Иначе поле показывало бы «3» над таблицей из четырёх строк, и оператор
        читал бы его как ответ на вопрос «сколько позиций», а это неправда.
        """
        with kit.filling(self.count):
            self.count.setValue(max(self.table.rowCount(), 1))

    def _next_index(self) -> int:
        """Следующий индекс — `max + 1`. Дыра в середине не заполняется."""
        taken = []
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            index = position_index(cell.text()) if cell else None
            if index is not None:
                taken.append(index)
        return max(taken, default=0) + 1

    def drop_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row >= 0:
            self.table.removeRow(row)
            self._sync_count()

    def specs(self) -> list[GPositionSpec]:
        """Собрать g-позиции из таблицы; ошибки ввода — доменными сообщениями."""
        specs: list[GPositionSpec] = []
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            raw_index = position_index(cell.text() if cell else "")
            # Индекс выдаём мы сами и правке он не подлежит; проверка осталась
            # страховкой на случай, если ячейку когда-нибудь снова откроют.
            if raw_index is None:
                raise ValidationError(
                    f"Row {row + 1}: the g-position index is issued by the form "
                    "and must be a whole number."
                )

            def cell(column: int) -> str:
                item = self.table.item(row, column)
                return item.text() if item else ""

            specs.append(
                GPositionSpec(
                    g_index=raw_index,
                    nominal=parse_optional_number(cell(1), f"Row {row + 1}, nominal"),
                    tol_plus=parse_optional_number(cell(2), f"Row {row + 1}, upper deviation"),
                    tol_minus=parse_optional_number(cell(3), f"Row {row + 1}, lower deviation"),
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
            kit.show_error(self, error, title="Group not created")
            return
        self.accept()


def _issued_index(g_index: int) -> QTableWidgetItem:
    """Ячейка выданного индекса: только чтение (ратификация В-8)."""
    cell = QTableWidgetItem(position_label(g_index))
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    cell.setToolTip(
        "The g-position index is issued as max + 1 and never reused: it is the "
        "shared label of the drawing and the database."
    )
    return cell
