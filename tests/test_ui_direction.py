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


def _table(
    values: list[str],
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
) -> QTableWidget:
    table = QTableWidget(1, len(values))
    for column, value in enumerate(values):
        table.setItem(0, column, QTableWidgetItem(value))
    directional(table, numeric_columns, magnitude_columns)
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


def test_a_magnitude_column_is_right_aligned() -> None:
    """Величины сравнивают вниз по столбцу — разряды обязаны встать в столбик.

    Решение Cowork по ревью наряда 0007: направление и выравнивание — два
    разных вопроса. Вправо идут номинал, допуски и величина; счётчики, даты и
    номера остаются влево, у подписи колонки.
    """
    table = _table(["3.75", "12"], magnitude_columns=(0,))

    assert _drawn_alignment(_option(table, 0, 0)) & Qt.AlignmentFlag.AlignRight
    assert _drawn_alignment(_option(table, 0, 1)) & Qt.AlignmentFlag.AlignLeft


def test_a_magnitude_column_is_numeric_without_being_listed_twice() -> None:
    """Величина — частный случай числовой колонки: LTR ей полагается сама."""
    table = _table([HEBREW], magnitude_columns=(0,))

    assert _option(table, 0, 0).direction == LTR


def test_counters_and_dates_stay_left() -> None:
    """Числовая, но не величина: сравнивать нечего, левый край держит подпись."""
    table = _table([NUMBER, "3"], numeric_columns=(0, 1))

    assert _drawn_alignment(_option(table, 0, 0)) & Qt.AlignmentFlag.AlignLeft
    assert _drawn_alignment(_option(table, 0, 1)) & Qt.AlignmentFlag.AlignLeft


def test_the_delegate_is_wired_into_the_deviation_list(seeded_session) -> None:
    """Механизм должен стоять на боевом экране, а не только в этом тесте."""
    from ui.common import DirectionalDelegate
    from ui.deviation_view import (
        COLUMNS,
        MAGNITUDE_COLUMNS,
        NUMERIC_COLUMNS,
        DeviationView,
    )

    seeded_session.commit()
    view = DeviationView(seeded_session.get_bind())

    assert isinstance(view.table.itemDelegate(), DirectionalDelegate)
    # Принудительно LTR — идентификаторы, наряд, дата, количество и исход.
    # Адресуются **по имени**, а не константой: наряд `0028` встал колонкой
    # раскрытия перед `Number` и снял `Inspections`, и прибитый кортеж сообщал бы
    # о сдвиге, а не о том, верно ли объявлены колонки (`CLAUDE.md` §9а.9).
    assert NUMERIC_COLUMNS == tuple(
        COLUMNS.index(name)
        for name in ("Number", "Revision", "WO", "Date", "Dev. qty", "Decision")
    )
    # `Item` и `Explanation` направление берут по содержимому: там бывает иврит,
    # и принудительный LTR перевернул бы его (`CLAUDE.md` §9).
    assert COLUMNS.index("Item") not in NUMERIC_COLUMNS
    assert COLUMNS.index("Explanation") not in NUMERIC_COLUMNS
    # Вправо — только количество отклонения: его и сравнивают по величине
    # вниз по столбцу (канон §6).
    assert MAGNITUDE_COLUMNS == (COLUMNS.index("Dev. qty"),)
    assert COLUMNS.index("Findings") < COLUMNS.index("Decision")


def test_canon_geometry_is_two_tokens_in_two_isolates() -> None:
    """Номинал и допуск — самостоятельные токены, каждый в своём изоляте.

    Один изолят вокруг всей строки задал бы только базу ячейки, а токены
    остались бы переставленными (`CLAUDE.md` §9).
    """
    from ui.common import canon_geometry_label

    cell = canon_geometry_label(38.10, 0.20, -0.10)

    assert strip_iso(cell) == "38.1 +0.2 / −0.1"
    assert cell.count("⁨") == 2


def test_canon_geometry_without_numbers_is_a_dash() -> None:
    """Позиция без геометрии — прочерк: деталь по ней не засеется, это видно."""
    from ui.common import NO_GEOMETRY, canon_geometry_label

    assert canon_geometry_label(None, None, None) == NO_GEOMETRY


# --- предельные отклонения: знак из данных (наряд 0015) ----------------------------


@pytest.mark.parametrize(
    "plus, minus, expected",
    [
        (0.05, -0.05, "+0.05 / −0.05"),  # симметричное поле
        (0.05, 0.02, "+0.05 / +0.02"),  # посадка с натягом — оба в плюс
        (-0.02, -0.05, "−0.02 / −0.05"),  # оба в минус
        (0.05, None, "+0.05"),  # задано одно — второе не выдумывается
        (None, -0.05, "−0.05"),
        (None, None, ""),  # оба пусты — токена нет вовсе
        (0, 0, "0 / 0"),  # ноль знака не несёт вовсе (ISO 286)
    ],
)
def test_each_deviation_carries_its_own_sign(plus, minus, expected) -> None:
    """Критерий 1–2 наряда 0015: знак читается из значения, а не из шаблона.

    Прежняя сборка была `f"+{abs(plus)} / −{abs(minus)}"`, и пара `+0.05 / +0.02`
    выводилась как `+0.05 / −0.02`: поле допуска зеркально, несимметричная
    посадка выглядела симметричной. В базе значения были верны — врал показ.
    """
    from ui.common import tolerance_text

    assert tolerance_text(plus, minus) == expected


def test_the_minus_of_a_deviation_is_the_canonical_one() -> None:
    """`−` (U+2212), а не ASCII-дефис: на экране один минус, а не два разных."""
    from ui.common import tolerance_text

    text = tolerance_text(0.05, -0.05)

    assert "−" in text and "-" not in text


def test_a_deviation_pair_stays_one_token_in_one_isolate() -> None:
    """`CLAUDE.md` §9: пара — атомарный токен, и изолят на неё **один**.

    Два изолята подряд остаются двумя runs и в RTL-контексте раскладываются
    справа налево, превращая `+0.05 / −0.02` в `−0.02 / +0.05`.
    """
    from ui.common import tolerance_label

    cell = tolerance_label(0.05, 0.02)

    assert cell.count("⁨") == 1
    assert strip_iso(cell) == "+0.05 / +0.02"


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
    from db.models import Direction
    from ui.common import signed_label

    cell = signed_label(Direction.MINUS, 0.05)

    assert strip_iso(cell) == "− 0.05"
    assert cell.count("⁨") == 1


def test_both_tables_build_the_signed_cell_the_same_way() -> None:
    """Одна сборка на обе таблицы: находки и прецеденты не должны разъехаться.

    До слияния форма показывала знак и величину двумя колонками, а карточка —
    одной; `_signed` жил в `card_dialog`, и обратная ссылка на него из формы дала
    бы кольцевой импорт (`card_dialog` уже импортирует `FINDING_COLUMNS`).
    Поэтому сборщик живёт в `ui.common`, а колонка называется одинаково.
    """
    from ui.card_dialog import PRECEDENT_COLUMNS
    from ui.deviation_dialog import FINDING_COLUMNS

    assert "Sign · value" in FINDING_COLUMNS
    assert "Sign · value" in PRECEDENT_COLUMNS
    assert "Direction" not in FINDING_COLUMNS and "Value" not in FINDING_COLUMNS


def test_the_groups_column_isolates_every_group_name(seeded_session) -> None:
    """Р-1: имена групп — самостоятельные токены, а не один склеенный текст.

    Деталь входит в две CG, одна названа на иврите. Обычный `", ".join` оставлял
    запятые нейтральными, порядок доставался базе ячейки, и оператор читал
    принадлежность детали неверно.
    """
    from conftest import make_item, rev
    from db.session import session_scope
    from domain.groups import GPositionSpec, create_group
    from domain.mappings import bind
    from ui.item_view import ItemView

    engine = seeded_session.get_bind()
    with session_scope(engine) as session:
        hebrew = create_group(session, "קבוצת הברגה", (GPositionSpec(1, 3.75),))
        latin = create_group(session, "Implant_Con_375_C1", (GPositionSpec(1, 2.0),))
        item = make_item(session, "C1-08375A")
        bind(session, rev(item), hebrew.positions[0], "12")
        bind(session, rev(item), latin.positions[0], "19")

    view = ItemView(engine)
    # Колонка групп сдвинулась на единицу: перед ней встала Revision (QMS-017).
    cell = view.table.item(0, 6).text()

    # Порядок задаёт домен (`groups_of`), проверяем не его, а изоляцию токенов:
    # каждое имя обёрнуто отдельно, склеенного текста в ячейке нет.
    names = strip_iso(cell).split(", ")
    assert sorted(names) == sorted(["קבוצת הברגה", "Implant_Con_375_C1"])
    assert cell == joined(*names, sep=", ")


# --- поля и редакторы ---------------------------------------------------------------


def test_numeric_field_forces_ltr() -> None:
    assert numeric_field(QDateEdit()).layoutDirection() == LTR


def test_a_line_edit_follows_what_is_typed() -> None:
    """У `QLineEdit` базой абзаца служит `layoutDirection` — хелпер здесь нужен."""
    editor = bind_direction(QLineEdit())

    editor.setText(HEBREW)
    assert editor.layoutDirection() == RTL

    editor.setText(LATIN)
    assert editor.layoutDirection() == LTR

    editor.setText("")
    assert editor.layoutDirection() == LTR


def _block_directions(area: QPlainTextEdit) -> list:
    """Направление **каждого абзаца** — то, что Qt действительно рисует.

    Сверять `layoutDirection` текстовой области бессмысленно: это свойство,
    которое код сам же и выставил, а на раскладку текста оно не влияет
    (ревью Р-2 — тот же класс ошибки, что был найден в делегате снимком).
    """
    document = area.document()
    block, directions = document.firstBlock(), []
    while block.isValid():
        directions.append(block.textDirection())
        block = block.next()
    return directions


@pytest.mark.parametrize("widget_direction", [LTR, RTL])
def test_a_text_area_resolves_direction_per_paragraph(widget_direction) -> None:
    """Абзац берёт направление по содержимому — при любом `layoutDirection`.

    Поэтому `bind_direction` текстовой области не нужен: он не влияет на текст,
    зато перебрасывает полосу прокрутки на другую сторону на первом ивритском
    символе. И главное — абзацы в одном поле бывают разных направлений сразу,
    так что одно направление на виджет там неверная единица.
    """
    area = QPlainTextEdit()
    area.setLayoutDirection(widget_direction)
    area.setPlainText(f"{LATIN}\n{HEBREW}\n{NUMBER}")

    assert _block_directions(area) == [LTR, RTL, LTR]


def test_bind_direction_refuses_a_text_area() -> None:
    """Молча-бесполезный вызов хуже громкого отказа: ошибка повторилась бы."""
    with pytest.raises(TypeError):
        bind_direction(QPlainTextEdit())


def test_the_comment_field_resolves_direction_per_paragraph(seeded_session) -> None:
    """То же на боевом виджете: комментарий находки — ивритский абзац RTL."""
    from ui.finding_dialog import FindingDialog

    seeded_session.commit()
    dialog = FindingDialog(seeded_session.get_bind(), None)
    dialog.comment_edit.setPlainText(f"{HEBREW}\n{LATIN}")

    assert _block_directions(dialog.comment_edit) == [RTL, LTR]
