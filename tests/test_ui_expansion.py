"""Список отклонений: пилюли находок, раскрытие строки, панель (наряд 0028).

Критерии приёмки 3–10. Каждый тест называет правило, которое сторожит
(`CLAUDE.md` §9а.10): тест, написанный вместе с кодом одним заходом, иначе
сторожит замысел исполнителя, а не требование канона.

Колонки адресуются **по заголовку**, строки — по содержимому (§9а.9): номера
здесь общие у кода и теста, и прибитый индекс остаётся зелёным ровно там, где
обязан покраснеть.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QStyleOptionViewItem

import ui.kit as kit
from conftest import count_queries, make_item, rev
from db.models import Direction, Finding, RefInspectionType
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.findings import make_finding, research_label
from domain.inspections import create_inspection
from domain.reference import ensure_value, list_values
from ui.common import strip_iso
from ui.deviation_view import (
    COLUMNS,
    EXPLANATION_FLOOR,
    FULL_WIDTHS,
    PANEL_COLUMNS,
    PANEL_WIDTHS,
    TIGHT_WIDTHS,
    DeviationView,
    finding_row_height,
    grid_widths,
)
from ui.kit import tokens
from ui.kit.chips import CHIPS_ROLE, EXPANDED_ROLE, Chip, ExpanderDelegate, FindingChipsDelegate

pytestmark = pytest.mark.usefixtures("qt_app")

TODAY = date.today()


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


@pytest.fixture
def no_modals(monkeypatch):
    """Ловушка модальных окон (`CLAUDE.md` §9): тест обязан увидеть их, а не повиснуть."""
    shown: list[Exception] = []
    monkeypatch.setattr(kit, "show_error", lambda parent, error, **kw: shown.append(error))
    return shown


def _deviation(session, item, *, wo: str, numbers=("12",), decision: str | None = None):
    deviation = register(session, item=item, wo=wo, quantity=5, date=TODAY)
    findings = []
    for number in numbers:
        characteristic, _ = get_or_create_characteristic(session, rev(item), number)
        findings.append(
            make_finding(
                session, deviation, characteristic, direction=Direction.PLUS, value=0.08
            )
        )
    if decision is not None:
        set_decision(session, deviation, decision=decision, explanation="ok")
    return deviation, findings


def _inspect(session, finding, position, *, kind: str = "Solidworks assembly"):
    return create_inspection(
        session,
        finding,
        inspection_type=ensure_value(session, RefInspectionType, kind),
        decision_insp=position,
        conclusion=None,
        protocol="p.docx",
    )


def _column(name: str) -> int:
    return COLUMNS.index(name)


def _panel_column(panel, header: str) -> int:
    labels = [
        panel.horizontalHeaderItem(index).text() for index in range(panel.columnCount())
    ]
    assert header in labels, labels
    return labels.index(header)


def _first_panel(view):
    for row in range(view.table.rowCount()):
        panel = view.panel_at(row)
        if panel is not None:
            return row, panel
    raise AssertionError("раскрытой панели на экране нет")


# --- Критерий 3: сетка ------------------------------------------------------------


def test_the_deviation_grid_adds_up_to_the_declared_width_at_1280() -> None:
    """Правило доводки `0028`, пункт 2: «ширины уровня отклонения при 1280
    назначить **замером**, целевая сумма — **1216**», и `design-system.md` §3
    revision 1.8: таблица «at most 90 % of the window, **and never narrower than
    1216**».

    Проверяется **сумма при сжатии**, а не список констант: сумма это то, что
    отличает сошедшуюся сетку от несошедшейся, и она же названа в доводке числом.
    Что ни одно значение при этом не обрезано — вопрос **замера** на нативной
    платформе, и он живёт в `tools/screenshots.py` (`CLAUDE.md` §9а.13).
    """
    widths = grid_widths(1280, revision_width=116)

    assert sum(widths.values()) == 1216 == kit.table_limit(1280)
    # Ровно те колонки, что перечислены в сумме, — и ни одной сверх.
    assert set(widths) == {
        "", "Number", "Item", "WO", "Date", "Qty", "Findings", "Decision", "Explanation"
    }
    assert widths["Explanation"] >= EXPLANATION_FLOOR


def test_the_revision_width_cannot_move_the_1280_sum() -> None:
    """`Revision` в канве нет — её ширина считается по заголовку (§1 наряда).

    Тест на **независимость**: при 1280 колонка уходит, поэтому шрифт на сумму
    не влияет. Без этого сумма 1216 зависела бы от машины прогона, и та же
    сетка была бы верной здесь и неверной у оператора.
    """
    narrow = sum(grid_widths(1280, revision_width=40).values())
    wide = sum(grid_widths(1280, revision_width=400).values())

    assert narrow == wide == 1216


def test_the_full_grid_fits_the_wide_window() -> None:
    """При 1920 лимит 1728, и полная сетка в него укладывается со всеми колонками."""
    widths = grid_widths(1920, revision_width=68)

    assert "Findings" in widths and "Revision" in widths
    assert widths["Explanation"] == FULL_WIDTHS["Explanation"]
    assert sum(widths.values()) <= kit.table_limit(1920)


def test_the_table_width_rule_has_a_floor() -> None:
    """Правило `design-system.md` §3 revision 1.8 и доводка, пункт 5: доля окна
    получает **пол 1216**.

    Пол — ревизия пустого места, а не подстраховка: при минимальном окне прежние
    90 % отдавали 128 px фона, пока колонки голодали настолько, что `W26007336`
    резался. Проверяется с обеих сторон точки перелома, иначе «пол» неотличим от
    «всегда 1216».
    """
    assert kit.table_limit(1280) == 1216      # доля дала бы 1152 — пол выше
    assert kit.table_limit(1440) == 1296      # доля выше пола — правит доля
    assert kit.table_limit(1920) == 1728


def test_the_finding_grid_adds_up_to_1144() -> None:
    """Правило §4 наряда: «**Сумма фиксированных: 1144.** …сходится **без** потери
    `Canon` и **без** сжатия `Inspections`».

    Запас после доводки вырос: предел при 1280 стал 1216 (пол правила ширины),
    и панели остаётся 72 px вместо восьми.
    """
    assert sum(PANEL_WIDTHS.values()) == 1144
    assert sum(PANEL_WIDTHS.values()) <= kit.table_limit(1280)
    assert tuple(PANEL_WIDTHS) == PANEL_COLUMNS


def test_findings_and_explanation_stay_at_the_minimum_window() -> None:
    """Правило доводки `0028`, пункт 1: «`Findings` и `Explanation` **остаются**
    при 1280; уходят зона запаса, `Revision`».

    Это **исправление** прежнего порядка, и исправление по существу. Канва
    обосновывала уход `Findings` тем, что находки на этой ширине показаны
    строками, — но строками они показаны только у **раскрытой** записи. У
    свёрнутой при 1280 про находки не было видно ничего, то есть требование,
    ради которого экран переделан, при минимальном окне не выполнялось вовсе.
    """
    wide = grid_widths(1920, revision_width=68)
    narrow = grid_widths(1280, revision_width=68)

    assert "Revision" in wide and "Revision" not in narrow
    assert "Findings" in narrow, "свёрнутая запись при 1280 осталась бы немой"
    assert "Explanation" in narrow


def test_every_declared_width_is_a_measured_one() -> None:
    """`CLAUDE.md` §9а.12: «Объявленная ширина колонки — не нарисованная… Ширина
    считается проверенной только после **замера на нативной платформе**».

    Под offscreen сам замер непроверяем (§9а.13), и здесь сторожится то, что
    проверяемо: сжатая сетка объявлена **своим** набором чисел, а не полной
    минус что-нибудь. Иначе одно и то же число отвечало бы за две ширины окна,
    и замерить его отдельно для каждой было бы нечем.
    """
    assert sum(TIGHT_WIDTHS.values()) == 1216
    assert set(TIGHT_WIDTHS) == set(FULL_WIDTHS)
    # Сжатая сетка **уже** полной в каждой колонке, кроме тех, где полная и так
    # на минимуме: иначе «сжатие» ничего не сжимает.
    assert all(TIGHT_WIDTHS[name] <= FULL_WIDTHS[name] for name in TIGHT_WIDTHS)
    assert TIGHT_WIDTHS["Findings"] == FULL_WIDTHS["Findings"]


def test_the_short_qty_header_keeps_the_full_wording_in_a_tooltip() -> None:
    """Правило доводки `0028`, пункт 4: «Заголовок `Dev. qty` → `Qty`, подсказка
    «parts in this deviation» сохраняется».

    Сокращение заголовка — это **освобождение места**, а не потеря слов: прежний
    заголовок был шире содержимого и один задавал ширину колонки. Тест сторожит
    вторую половину: слова остались там, где их можно прочесть.
    """
    from ui.deviation_view import QTY_HINT

    assert "Qty" in COLUMNS and "Dev. qty" not in COLUMNS
    assert QTY_HINT == "parts in this deviation"


def test_the_screen_puts_that_tooltip_on_the_header(engine) -> None:
    """И оно доходит до заголовка: константа сама по себе ничего не показывает."""
    view = DeviationView(engine)
    header = view.table.horizontalHeaderItem(_column("Qty"))

    assert header.toolTip() == "parts in this deviation"


# --- Критерий 4: стоимость чтения --------------------------------------------------


def test_rendering_the_screen_costs_two_queries_whatever_the_row_count(engine) -> None:
    """Правило §5 наряда: «Запрет, который проверяется тестом: ни одного запроса
    на строку и ни одного на находку при отрисовке экрана».

    Считается **разность** между двумя размерами выборки, а не абсолютное число:
    так тест ловит именно рост от N, а не переезд какого-нибудь `PRAGMA`.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1", numbers=("12", "19"))

    view = DeviationView(engine)
    with count_queries(engine) as few:
        view.reload()

    with session_scope(engine) as session:
        from db.models import Item

        item = session.query(Item).one()
        for index in range(6):
            _deviation(session, item, wo=f"W{index + 2}", numbers=("12", "19", "77"))

    with count_queries(engine) as many:
        view.reload()

    assert view.table.rowCount() == 7
    assert len(many) == len(few) == 2, (len(few), len(many), many)


def test_expanding_one_record_adds_exactly_one_query(engine) -> None:
    """Правило §5.3 наряда: «Исследования — ленивым запросом на раскрытие, один
    на раскрываемое отклонение».

    Свёрнутой строке от исследования нужен один признак, «есть или нет», и он
    приехал счётчиком вторым пакетным запросом.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1", numbers=("12", "19"))
        _inspect(session, findings[0], "approval_possible")

    view = DeviationView(engine)
    with count_queries(engine) as collapsed:
        view.reload()

    view.toggle_expansion(0)
    with count_queries(engine) as expanded:
        view.reload()

    assert len(collapsed) == 2
    assert len(expanded) == 3


# --- Критерий 5: высоты -----------------------------------------------------------


@pytest.mark.parametrize(
    ("findings", "height"),
    [(1, 40), (2, 66), (3, 82), (6, 82)],
)
def test_the_deviation_row_grows_with_its_findings(engine, findings: int, height: int) -> None:
    """Правило `design-system.md` §3, revision 1.7: «There the row carries the
    finding chips themselves, so it grows with them: **40 / 66 / 82** for one /
    two / three-or-more findings».

    Замеряется **отрисованная** высота строки таблицы, а не токен: токен может
    быть верным при том, что экран его не применил.
    """
    numbers = [str(10 + index) for index in range(findings)]
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1", numbers=tuple(numbers))

    view = DeviationView(engine)

    assert view.table.rowHeight(0) == height


@pytest.mark.parametrize(
    ("inspections", "height"), [(0, 28), (1, 28), (2, 43), (3, 58), (5, 58)]
)
def test_the_finding_row_grows_with_its_inspections(inspections: int, height: int) -> None:
    """Правило `design-system.md` §3, revision 1.7: «Inside an expanded record the
    finding sub-row is **28 / 43 / 58** by the number of inspections listed».
    """
    assert finding_row_height(inspections) == height


def test_the_panel_applies_those_heights_to_its_rows(engine) -> None:
    """Та же величина, но **на экране**: панель обязана раздать высоты строкам.

    Отдельным тестом от предыдущего потому, что `finding_row_height` — чистая
    функция, и её зелёность ничего не говорит о том, позвал ли её кто-нибудь.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1", numbers=("12", "19"))
        for position in ("approval_possible", "inconclusive"):
            _inspect(session, findings[1], position, kind="Implantation torque test")

    view = DeviationView(engine)
    view.toggle_expansion(0)
    _, panel = _first_panel(view)

    dim = _panel_column(panel, "Dim.")
    heights = {
        strip_iso(panel.item(row, dim).text()): panel.rowHeight(row)
        for row in range(panel.rowCount())
    }
    assert heights == {"12": 28, "19": 43}


# --- Критерий 6: инварианты служебной строки ---------------------------------------


def test_the_service_row_is_neither_selectable_nor_reachable_by_arrows(engine) -> None:
    """Правило §3 наряда, инварианты 1 и 2: «**Не выбирается.** Клик по ней не
    меняет выбранное отклонение» и «**Не ловится стрелками клавиатуры.**»

    Проверяется **флагами ячейки**, которыми Qt и решает оба вопроса, а не
    попыткой кликнуть: флаг — то, чем это сделано, а клик по невидимому виджету
    проверил бы диспетчеризацию, а не правило.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1", numbers=("12", "19"))

    view = DeviationView(engine)
    view.toggle_expansion(0)
    row, panel = _first_panel(view)

    holder = view.table.item(row, 0)
    assert not (holder.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (holder.flags() & Qt.ItemFlag.ItemIsEnabled)
    # Панель фокуса не берёт — иначе `Tab` увёл бы курсор внутрь служебной строки.
    assert panel.focusPolicy() == Qt.FocusPolicy.NoFocus
    # И выбирать в ней нечего: единица действия остаётся отклонением.
    assert panel.selectionMode().name == "NoSelection"


def test_the_action_addresses_the_deviation_even_with_the_panel_open(engine) -> None:
    """Правило §3 наряда, инвариант 3: «**Единица действия — отклонение.**
    Карточка, правка, решение, удаление действуют на выбранное отклонение, даже
    когда курсор внутри панели».
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation, _ = _deviation(session, item, wo="W1", numbers=("12", "19"))
        expected = deviation.deviation_id

    view = DeviationView(engine)
    view.table.selectRow(0)
    view.toggle_expansion(0)

    # Служебная строка вставлена, номера строк сдвинулись — выбор обязан остаться
    # на том же **отклонении**, а не на той же строке.
    assert view._selected_id() == expected
    assert "Selected" in view.selection_text()


def test_the_service_row_spans_the_whole_width(engine) -> None:
    """Правило §3 наряда: «под раскрытой строкой вставляется **служебная строка
    на всю ширину** (объединение ячеек), в неё кладётся виджет-панель находок».
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1")

    view = DeviationView(engine)
    view.toggle_expansion(0)
    row, _ = _first_panel(view)

    assert view.table.columnSpan(row, 0) == len(COLUMNS)


# --- Критерий 7: сводка Research ---------------------------------------------------


@pytest.mark.parametrize(
    ("positions", "expected"),
    [
        ((), "Not researched"),
        (("approval_possible",), "Approval possible"),
        (("approval_not_possible", "approval_not_possible"), "Approval not possible"),
        (("inconclusive",), "Inconclusive"),
        # Позиции разошлись.
        (("approval_possible", "inconclusive"), "Researched · 2"),
        # Позиция проставлена не у всех — то же состояние, другая причина.
        (("approval_possible", None), "Researched · 2"),
        ((None,), "Researched · 1"),
    ],
)
def test_research_summarises_without_judging(positions, expected: str) -> None:
    """Правило `docs/decisions.md`, QMS-018 решение 8, и §4.1 наряда: пять
    состояний, и «`Researched · N` **не выбирает строгейшую позицию** — это было
    бы решение, принятое экраном за инженера».

    Два последних случая — то, ради чего состояние вообще заведено: расхождение
    позиций и непроставленная позиция дают **одну** сводку, потому что обе значат
    «открой и прочитай».
    """
    assert research_label(positions) == expected


def test_the_panel_shows_the_research_summary_it_computed(engine) -> None:
    """Та же сводка, но **на экране**, и рядом — пустое состояние соседней ячейки.

    §4.2 наряда: «Пустое состояние ячейки — `No inspections`… оно согласовано с
    `Not researched` в соседней колонке и не дублирует его словами».
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1", numbers=("12", "19"))
        _inspect(session, findings[1], "approval_possible")
        _inspect(session, findings[1], None, kind="Implantation torque test")

    view = DeviationView(engine)
    view.toggle_expansion(0)
    _, panel = _first_panel(view)

    dim = _panel_column(panel, "Dim.")
    research = _panel_column(panel, "Research")
    inspections = _panel_column(panel, "Inspections")
    rows = {
        strip_iso(panel.item(row, dim).text()): (
            panel.item(row, research).text(),
            panel.item(row, inspections).text(),
        )
        for row in range(panel.rowCount())
    }

    assert rows["12"] == ("Not researched", "No inspections")
    assert rows["19"][0] == "Researched · 2"
    # Тип и позиция — по строке на исследование; вывод в ячейку не попадает.
    assert "Solidworks assembly" in rows["19"][1]
    assert "Not assessed yet" in rows["19"][1]


def test_the_conclusion_lives_in_the_tooltip_not_in_the_cell(engine) -> None:
    """Правило §4.2 наряда: «**Короткий вывод (`conclusion`) в ячейку не
    помещается** — 340 px это около 45 знаков… Поэтому: **полный вывод — в
    подсказке по наведению**, без обрезки».
    """
    whole = "clearance in the assembled state drops by 20 % under worst case"
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1")
        create_inspection(
            session,
            findings[0],
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approval_possible",
            conclusion=whole,
            protocol="p.docx",
        )

    view = DeviationView(engine)
    view.toggle_expansion(0)
    _, panel = _first_panel(view)
    cell = panel.item(0, _panel_column(panel, "Inspections"))

    assert whole not in cell.text()
    assert whole in cell.toolTip()


# --- Критерий 8: состояние раскрытия ------------------------------------------------


def test_expansion_survives_a_reload_and_does_not_move_the_scroll(engine) -> None:
    """Правило §3 наряда: состояние «**переживает перечитывание списка**: после
    правки, решения или регистрации раскрытые остаются раскрытыми».

    Раскрытых **несколько** (решение 6 реестра): гармошка делает невозможным то,
    ради чего раскрытие и заведено, — сравнение двух отклонений между собой.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        first, _ = _deviation(session, item, wo="W1", numbers=("12", "19"))
        second, _ = _deviation(session, item, wo="W2", numbers=("77",))
        wanted = {first.deviation_id, second.deviation_id}

    view = DeviationView(engine)
    view.toggle_expansion(0)
    # После первого раскрытия строки сдвинулись — второе отклонение ищем по
    # владельцу строки, а не по номеру (§9а.9).
    for row in range(view.table.rowCount()):
        if not view.is_panel_row(row) and view._deviation_at(row) not in view.expanded():
            view.toggle_expansion(row)
            break

    assert view.expanded() == wanted
    scroll = view.table.verticalScrollBar().value()

    view.reload()

    assert view.expanded() == wanted
    assert sum(1 for row in range(view.table.rowCount()) if view.is_panel_row(row)) == 2
    assert view.table.verticalScrollBar().value() == scroll


def test_collapsing_removes_the_panel_and_leaves_the_record(engine) -> None:
    """Обратная сторона: свернуть — значит убрать панель, а не запись."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1")

    view = DeviationView(engine)
    view.toggle_expansion(0)
    assert view.table.rowCount() == 2

    view.toggle_expansion(0)

    assert view.expanded() == set()
    assert view.table.rowCount() == 1
    assert view.row_count() == 1


def test_the_expander_carries_its_state_as_a_code_not_as_a_glyph(engine) -> None:
    """Стрелку рисует делегат, и берёт он состояние **ролью**, а не разбором
    подписи (`CLAUDE.md` §9а: сверяй то, чем рисуют).

    Колонка объявлена в 23 px, а лист стиля даёт ячейке `padding: 0 10px`: на
    текстовую стрелку остаётся 3 px, и она исчезает совсем.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1")

    view = DeviationView(engine)
    cell = view.table.item(0, 0)

    assert cell.data(EXPANDED_ROLE) is False
    assert cell.text() == ""
    assert isinstance(view.table.itemDelegateForColumn(0), ExpanderDelegate)

    view.toggle_expansion(0)
    assert view.table.item(0, 0).data(EXPANDED_ROLE) is True


# --- Критерий 9: два числа в подвале ------------------------------------------------


def test_the_footer_counts_deviations_and_findings_as_different_numbers(engine) -> None:
    """Правило §6 наряда: «Подвал говорит **двумя числами**: `12 deviations /
    24 findings`. Счётчики считают **отклонения**, а не находки: экран,
    показывающий «12» там, где отклонений семь, а находок двенадцать,
    обманывает».

    Числа взяты **разными**: при равных счётчик, считающий не то, был бы зелёным.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W1", numbers=("12", "19", "77"))
        _deviation(session, item, wo="W2", numbers=("21",))

    view = DeviationView(engine)

    assert "2 deviations" in view.summary_text()
    assert "4 findings" in view.summary_text()
    # Счётчик ленты — это **отклонения**, не находки.
    assert view.row_count() == 2


# --- Критерий 10: значок мензурки ---------------------------------------------------


def test_the_flask_marks_presence_of_inspections_not_their_position(engine) -> None:
    """Правило §2 наряда и `design-system.md` §10: «значок мензурки 13 px только
    тогда, когда у этой находки есть исследования… Значок — признак наличия,
    **не вердикт**: он не меняется от позиции исследования».

    Проверяется на трёх позициях подряд и на пустой: если бы значок зависел от
    позиции, один из четырёх случаев разошёлся бы с остальными.
    """
    positions = ("approval_possible", "approval_not_possible", "inconclusive", None)
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        numbers = tuple(str(11 + index) for index in range(len(positions) + 1))
        _, findings = _deviation(session, item, wo="W1", numbers=numbers)
        for finding, position in zip(findings, positions):
            _inspect(session, finding, position)
        bare = findings[-1]

    view = DeviationView(engine)
    chips = view.table.item(0, _column("Findings")).data(CHIPS_ROLE)
    marked = {chip.dimension: chip.researched for chip in chips}

    # Четыре находки с исследованиями — помечены все четыре, независимо от позиции.
    assert sum(marked.values()) == len(positions)
    # Пятая, без исследований, — не помечена.
    with session_scope(engine) as session:
        number = session.get(Finding, bare.finding_id).characteristic.local_number
    assert marked[f"Dim. {number}"] is False


def test_the_flask_is_actually_drawn_and_a_bare_chip_is_not(qt_app) -> None:
    """Считаем **пиксели**, а не флаг: «сверяй то, чем рисуют» (`CLAUDE.md` §9а).

    Флаг `researched` мог бы стоять верно при делегате, который его не рисует, —
    и предыдущий тест был бы зелёным на экране без единого значка. Различающая
    величина здесь — число закрашенных точек **справа в пилюле**, там, где
    мензурка и стоит; на всей пилюле разница утонула бы в подписи.
    """
    kit.apply_theme(qt_app)
    delegate = FindingChipsDelegate()

    def painted(researched: bool) -> int:
        pixmap = QPixmap(320, tokens.ROW_TWO_FINDINGS)
        pixmap.fill(QColor(tokens.WHITE))
        painter = QPainter(pixmap)
        option = QStyleOptionViewItem()
        option.rect = pixmap.rect()
        option.font = painter.font()
        chip = Chip(dimension="Dim. 19", value="+ 0.03", kind="", researched=researched)
        delegate._chip(painter, painter.fontMetrics(), chip, 10, 7, 300)
        painter.end()
        image = pixmap.toImage()
        # Считаем точки **цвета мензурки**, а не «не белые»: заливка пилюли, её
        # рамка и подпись — три других цвета, и «не белых» точек в обоих случаях
        # поровну. Различающая величина здесь именно цвет контура (§9а.4:
        # «считать надо ту величину, которая отличает верное от неверного»).
        flask = QColor(tokens.N_500)
        near = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = QColor(image.pixel(x, y))
                if max(
                    abs(colour.red() - flask.red()),
                    abs(colour.green() - flask.green()),
                    abs(colour.blue() - flask.blue()),
                ) < 24:
                    near += 1
        return near

    with_flask, without = painted(True), painted(False)
    assert with_flask > without, f"мензурка не нарисована: {with_flask} против {without}"
