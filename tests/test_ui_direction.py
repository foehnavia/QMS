"""Направление на уровне ячейки и поля — критерий 5 наряда 0007.

До S6 направление было одно на всё приложение (окно RTL), и ивритские данные
держались только этим. Здесь проверяется механизм, который его заменил:
делегат таблицы считает базу и выравнивание **по значению ячейки**, редакторы
свободного текста следуют за набранным, числовые поля жёстко LTR.

Прогон offscreen: направление и выравнивание — состояние `QStyleOptionViewItem`,
дисплея для них не нужно.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QLineEdit,
    QPlainTextEdit,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from ui.common import (
    LTR,
    RTL,
    base_direction,
    bind_direction,
    directional,
    first_strong,
    iso,
    joined,
    numeric_field,
    strip_iso,
)

pytestmark = pytest.mark.usefixtures("qt_app")

#: Три вида значения из критерия 5 — ивритское, латинское, числовое.
HEBREW = "אזור הברגה"
LATIN = "thread burr"
NUMBER = "19.08.2026"


def _option(table: QTableWidget, row: int, column: int) -> QStyleOptionViewItem:
    """Как Qt увидит ячейку: даём делегату собрать `QStyleOptionViewItem`."""
    option = QStyleOptionViewItem()
    table.itemDelegate().initStyleOption(option, table.model().index(row, column))
    return option


def _drawn_alignment(option: QStyleOptionViewItem) -> Qt.AlignmentFlag:
    """К какому краю ячейка ляжет **на экране**.

    Сверять `option.displayAlignment` напрямую нельзя: поверх него Qt при
    отрисовке накладывает `visualAlignment`, которая под RTL меняет левое на
    правое. Дефект, найденный снимком ивритского справочника, был ровно здесь —
    делегат просил `AlignRight`, а строка ложилась влево.
    """
    return QApplication.style().visualAlignment(option.direction, option.displayAlignment)


def _table(values: list[str], numeric_columns: tuple[int, ...] = ()) -> QTableWidget:
    table = QTableWidget(1, len(values))
    for column, value in enumerate(values):
        table.setItem(0, column, QTableWidgetItem(value))
    directional(table, numeric_columns)
    return table


# --- база направления --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (HEBREW, RTL),
        (LATIN, LTR),
        (f"{HEBREW} {LATIN}", RTL),   # первый сильный символ — иврит
        (f"{LATIN} {HEBREW}", LTR),   # и наоборот
        (NUMBER, LTR),                # сильных символов нет — остаётся LTR
        ("− 0.05", LTR),
        ("", LTR),
    ],
)
def test_base_direction_follows_the_first_strong_character(text, expected) -> None:
    assert base_direction(text) == expected


def test_a_string_without_strong_characters_has_no_direction_of_its_own() -> None:
    """`first_strong` честно отвечает «сильных нет» — база берётся по умолчанию."""
    assert first_strong("19.08.2026 ± 0.05") is None
    assert first_strong(iso(NUMBER)) is None  # изоляты сильными не считаются


# --- делегат таблицы ---------------------------------------------------------------


def test_hebrew_cell_gets_rtl_base_and_right_alignment() -> None:
    option = _option(_table([HEBREW]), 0, 0)

    assert option.direction == RTL
    assert _drawn_alignment(option) & Qt.AlignmentFlag.AlignRight


def test_latin_cell_gets_ltr_base_and_left_alignment() -> None:
    option = _option(_table([LATIN]), 0, 0)

    assert option.direction == LTR
    assert _drawn_alignment(option) & Qt.AlignmentFlag.AlignLeft


def test_alignment_is_logical_so_qt_does_not_flip_it_twice() -> None:
    """Делегат просит «к началу строки», а сторону выбирает `visualAlignment`.

    Если бы делегат просил `AlignRight` для ивритской ячейки, Qt превратил бы
    это в выравнивание влево — порядок слов был бы RTL, а строка липла бы к
    левому краю (дефект, найденный снимком экрана).
    """
    hebrew = _option(_table([HEBREW]), 0, 0)
    latin = _option(_table([LATIN]), 0, 0)

    assert hebrew.displayAlignment == latin.displayAlignment
    assert hebrew.displayAlignment & Qt.AlignmentFlag.AlignLeft


def test_numeric_column_stays_ltr_whatever_the_neighbours_are() -> None:
    """Дата и величина читаются слева направо и в ивритской строке.

    Колонка объявлена числовой списком, а не угадывается по содержимому: у
    `19.08.2026` сильных символов нет, и без объявления база досталась бы ей от
    первого сильного символа — то есть от соседа.
    """
    table = _table([HEBREW, NUMBER], numeric_columns=(1,))

    assert _option(table, 0, 0).direction == RTL
    assert _option(table, 0, 1).direction == LTR
    assert _drawn_alignment(_option(table, 0, 1)) & Qt.AlignmentFlag.AlignLeft


def test_a_numeric_column_wins_over_hebrew_content() -> None:
    """Объявление сильнее содержимого: иначе колонка «прыгала» бы по строкам."""
    table = _table([HEBREW], numeric_columns=(0,))

    assert _option(table, 0, 0).direction == LTR


def test_the_delegate_is_wired_into_the_deviation_list(seeded_session) -> None:
    """Механизм должен стоять на боевом экране, а не только в этом тесте."""
    from ui.common import DirectionalDelegate
    from ui.deviation_view import NUMERIC_COLUMNS, DeviationView

    seeded_session.commit()
    view = DeviationView(seeded_session.get_bind())

    assert isinstance(view.table.itemDelegate(), DirectionalDelegate)
    assert NUMERIC_COLUMNS == (3, 4, 6, 7)


# --- изоляты: один вокруг токена, не два подряд ------------------------------------


def test_joined_isolates_every_token_separately() -> None:
    """Составная ячейка: каждый токен держит своё направление сам."""
    cell = joined("12", "g5")

    assert strip_iso(cell) == "12 · g5"
    assert cell == f"{iso('12')} · {iso('g5')}"


def test_joined_drops_empty_tokens() -> None:
    """Пустой токен не должен оставлять висящий разделитель."""
    assert joined("12", "") == iso("12")


def test_a_signed_value_stays_one_isolate() -> None:
    """Ратификация S5: два изолята подряд в RTL раскладываются справа налево."""
    from ui.card_dialog import _signed
    from db.models import Direction

    cell = _signed(Direction.MINUS, 0.05)

    assert strip_iso(cell) == "− 0.05"
    assert cell.count("⁨") == 1


# --- поля и редакторы ---------------------------------------------------------------


def test_numeric_field_forces_ltr() -> None:
    assert numeric_field(QDateEdit()).layoutDirection() == LTR


@pytest.mark.parametrize("factory", [QLineEdit, QPlainTextEdit])
def test_free_text_editor_follows_what_is_typed(factory) -> None:
    """Ни LTR, ни RTL не форсируется — направление за содержимым (§4а)."""
    editor = bind_direction(factory())
    write = editor.setPlainText if hasattr(editor, "setPlainText") else editor.setText

    write(HEBREW)
    assert editor.layoutDirection() == RTL

    write(LATIN)
    assert editor.layoutDirection() == LTR

    write("")
    assert editor.layoutDirection() == LTR
