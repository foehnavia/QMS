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
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

import ui.kit as kit
from conftest import count_queries, make_item, rev
from db.models import Direction, Finding, RefInspectionType
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.findings import make_finding, update_finding
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
from ui.kit.widgets import CENTRING_DEPTH_LIMIT, _centre_columns, centring_margin
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
        # Одобрение требует разрешённых находок (QMS-025); хелпер строит данные,
        # а не проверяет инвариант — тому есть свои тесты, заходящие мимо формы.
        if decision == "approved":
            permit_findings(session, deviation)
        set_decision(session, deviation, decision=decision, explanation="ok")
    return deviation, findings


def _inspect(session, finding, *, kind: str = "Solidworks assembly"):
    """Исследование на находке. Позиции у него нет вовсе (`Inspection.md` 1.03)."""
    return create_inspection(
        session,
        finding,
        inspection_type=ensure_value(session, RefInspectionType, kind),
        conclusion=None,
        protocol="p.docx",
        no_protocol=False,
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
        _inspect(session, findings[0])

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
        for _ in range(2):
            _inspect(session, findings[1], kind="Implantation torque test")

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


# --- Критерий 7: колонка исхода замещает сводку Research ---------------------------


def test_the_panel_shows_the_outcome_of_each_finding(engine) -> None:
    """Правило наряда `0030` §3: «Колонка `Research` в панели раскрытия
    **заменяется на `Outcome`** — те же 168 px, сетка не трогается вовсе».

    `Research` была сводкой того, что говорят исследования; после снятия позиции
    (`Inspection.md` rev 1.03) сводить нечего, а её место занимает то, ради чего
    колонка и смотрелась: суждение по размеру.

    Три состояния сразу, в одной панели: тест на одно был бы зелёным и на экране,
    который всем находкам пишет одно и то же.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1", numbers=("12", "19", "77"))
        update_finding(
            session, findings[0], direction=findings[0].direction, value=findings[0].value,
            dimension_point=None, comment=None, zone=None, deviation_type=None,
            outcome="permitted",
        )
        update_finding(
            session, findings[1], direction=findings[1].direction, value=findings[1].value,
            dimension_point=None, comment=None, zone=None, deviation_type=None,
            outcome="not_permitted",
        )
        # Третья остаётся пустой — «ещё не решали», нормальное состояние.

    view = DeviationView(engine)
    view.toggle_expansion(0)
    _, panel = _first_panel(view)

    dim = _panel_column(panel, "Dim.")
    outcome = _panel_column(panel, "Outcome")
    rows = {
        strip_iso(panel.item(row, dim).text()): panel.item(row, outcome).text()
        for row in range(panel.rowCount())
    }

    assert rows == {"12": "Permitted", "19": "Not permitted", "77": "Not decided"}
    # Колонки сводки больше нет — она не спрятана, а замещена.
    labels = [
        panel.horizontalHeaderItem(index).text() for index in range(panel.columnCount())
    ]
    assert "Research" not in labels


def test_the_inspections_cell_shows_the_type_and_nothing_else(engine) -> None:
    """Правило §3 наряда: «Ячейка `Inspections` показывает **тип** исследования;
    полный вывод — в подсказке. Позиции там больше нет».

    Проверяется и **отсутствие**: прежняя ячейка несла «тип · позиция», и тест на
    одно лишь наличие типа остался бы зелёным, если бы позиция никуда не делась.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(session, item, wo="W1", numbers=("12", "19"))
        _inspect(session, findings[1])
        _inspect(session, findings[1], kind="Implantation torque test")

    view = DeviationView(engine)
    view.toggle_expansion(0)
    _, panel = _first_panel(view)

    dim = _panel_column(panel, "Dim.")
    inspections = _panel_column(panel, "Inspections")
    rows = {
        strip_iso(panel.item(row, dim).text()): panel.item(row, inspections).text()
        for row in range(panel.rowCount())
    }

    assert rows["12"] == "No inspections"
    assert "Solidworks assembly" in rows["19"]
    assert "Implantation torque test" in rows["19"]
    for gone in ("Approval possible", "Not assessed yet", "Inconclusive"):
        assert gone not in rows["19"]


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
            conclusion=whole,
            protocol="p.docx",
            no_protocol=False,
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


def test_the_two_icons_do_not_depend_on_each_other(engine) -> None:
    """**Критерий 6 наряда `0030`:** «иконка исследования не зависит от исхода и
    наоборот».

    Проверяется **перекрёстно**, на всех четырёх сочетаниях: исследования есть или
    нет × исход разрешён, не разрешён или пуст. Тест на одно сочетание был бы
    зелёным и на делегате, который рисует мензурку по исходу, — а именно эту
    ошибку канон запрещает прямо: «Значок — признак наличия, **не вердикт**»
    (`design-system.md` §10).
    """
    cases = (
        ("11", True, "permitted"),
        ("12", True, "not_permitted"),
        ("13", True, None),
        ("14", False, "permitted"),
        ("15", False, None),
    )
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _, findings = _deviation(
            session, item, wo="W1", numbers=tuple(number for number, _, _ in cases)
        )
        for finding, (_, researched, outcome) in zip(findings, cases):
            if researched:
                _inspect(session, finding)
            update_finding(
                session, finding, direction=finding.direction, value=finding.value,
                dimension_point=None, comment=None, zone=None, deviation_type=None,
                outcome=outcome,
            )

    view = DeviationView(engine)
    chips = {
        chip.dimension: chip
        for chip in view.table.item(0, _column("Findings")).data(CHIPS_ROLE)
    }

    for number, researched, outcome in cases:
        chip = chips[f"Dim. {number}"]
        assert chip.researched is researched, (number, "мензурка")
        assert chip.outcome == outcome, (number, "исход")


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


# --- Доводка 2: путь пользователя — настоящим событием ---------------------------
#
# `CLAUDE.md` §9а: «проверка должна входить в систему там же, где в неё входит
# человек — у клавиатуры и мыши, а не у метода», и §9а.6: «события доставляются
# через приложение, а не прямой посылкой в виджет».
#
# Двенадцать тестов выше зовут `toggle_expansion` напрямую, и все двенадцать были
# зелёными, пока раскрытие роняло приложение у пользователя. Прямой вызов остаётся
# там, где проверяется **состояние**; путь человека проверяется здесь.


@pytest.fixture
def two_deviations(engine):
    """Две записи по одной детали, у каждой две находки.

    Ровно тот случай, ради которого раскрытие сделано множественным: отклонения
    сравнивают между собой (решение 6 реестра).
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _deviation(session, item, wo="W26007336", numbers=("12", "19"))
        _deviation(session, item, wo="W26007201", numbers=("12", "77"))
    return engine


@pytest.fixture
def shown_view(two_deviations):
    """Экран, **показанный** на экране (§9а.5).

    У скрытого виджета часть механики Qt не запускается вовсе: `resizeEvent` ему
    не шлётся, и ветка пересчёта центрирования, в которой жил стоп-дефект, не
    исполняется. Скрытый виджет пережил бы то, от чего показанный умирал.
    """
    view = DeviationView(two_deviations)
    view.resize(1280, 760)
    view.show()
    QApplication.processEvents()
    yield view
    view.close()


def _click_expander(view, row: int) -> None:
    """Клик мышью по стрелке раскрытия — **через приложение**, а не вызовом слота.

    Между кнопкой и обработчиком есть промежуток, и дефекты живут ровно в нём
    (§9а.6, находка №12 наряда 0017). Точка берётся из `visualRect` — то есть из
    того же места, откуда её берёт отрисовка.
    """
    table = view.table
    index = table.model().index(row, COLUMNS.index(""))
    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        table.visualRect(index).center(),
    )
    QApplication.processEvents()


def test_the_centring_computation_has_a_fixed_point(shown_view) -> None:
    """**Стоп-дефект доводки 2, названный причиной и проверяемый арифметикой.**

    `kit.centring_margin` задаёт отступ полотна листом стиля, а Qt считает этот
    же отступ частью `frameWidth()`. Пока расчёт вычитал `frameWidth()` без
    поправки, его выход был его входом, и неподвижной точки не существовало:

        margin 0  -> frameWidth 1  -> available 1238 -> margin 11
        margin 11 -> frameWidth 12 -> available 1216 -> margin 0

    Гард `_margin == margin` этого не ловил: значение не повторялось, оно
    **чередовалось**. Раскладка зовёт пересчёт синхронно, поэтому на нативной
    платформе колебание уходило в неограниченную рекурсию — переполнение стека и
    смерть процесса без питоновской трассы.

    Проверяется **неподвижная точка**, а не клик: под offscreen колебание
    затухает, и тест на клик был бы зелёным на сломанном коде (`CLAUDE.md`
    §9а.13). Арифметика же платформы не знает — отступ, который применён, обязан
    пересчитаться сам в себя.
    """
    table = shown_view.table
    applied = getattr(table, "_margin", None)

    assert applied is not None, "центрирование ещё не применялось"
    assert centring_margin(table) == applied, (
        f"расчёт не имеет неподвижной точки: применён {applied}, "
        f"пересчитан {centring_margin(table)} — функция читает собственный "
        "отступ как ширину рамки"
    )


def test_the_convergence_guard_is_a_mechanism_not_a_wish(shown_view) -> None:
    """Обратная сторона: если сходимость когда-нибудь снова сломается, это будет
    **красный тест с текстом**, а не смерть процесса.

    Тот же довод, что закрыл `show_error` (QMS-021) и канон-хеш на приёмке:
    дисциплина остаётся пожеланием, гард — механизмом.
    """
    table = shown_view.table
    table._centring_depth = CENTRING_DEPTH_LIMIT
    table._margin = -1  # заведомо иное значение, чтобы пересчёт дошёл до гарда

    with pytest.raises(RuntimeError) as raised:
        _centre_columns(table)

    assert "did not converge" in str(raised.value)
    table._centring_depth = 0


def test_a_real_click_on_the_arrow_expands_the_row(shown_view) -> None:
    """**Главный критерий приёмки доводки 2.**

    Клик по стрелке настоящим событием на показанном виджете. На прежнем коде
    этот путь убивал процесс; двенадцать тестов, звавших `toggle_expansion`
    напрямую, оставались зелёными.
    """
    before = shown_view.table.rowCount()

    _click_expander(shown_view, 0)

    assert len(shown_view.expanded()) == 1
    assert shown_view.table.rowCount() == before + 1
    assert shown_view.panel_at(1) is not None


def test_a_second_real_click_collapses_it_again(shown_view) -> None:
    """Повторный клик сворачивает — тем же событием, не вызовом метода."""
    _click_expander(shown_view, 0)
    assert len(shown_view.expanded()) == 1

    _click_expander(shown_view, 0)

    assert shown_view.expanded() == set()
    assert shown_view.panel_at(1) is None


def test_a_real_click_expands_a_second_record_beside_the_first(shown_view) -> None:
    """Раскрытие второй записи при уже раскрытой первой — настоящими событиями.

    Решение 6 реестра: раскрытых может быть сколько угодно, потому что отклонения
    сравнивают **между собой**. Именно этот путь проходит по служебной строке,
    вставленной предыдущим раскрытием, и потому опаснее одиночного.
    """
    _click_expander(shown_view, 0)
    # Вторая запись съехала вниз на служебную строку — ищем её по владельцу,
    # а не по номеру (§9а.9).
    table = shown_view.table
    second = next(
        row
        for row in range(table.rowCount())
        if not shown_view.is_panel_row(row)
        and shown_view._deviation_at(row) not in shown_view.expanded()
    )

    _click_expander(shown_view, second)

    assert len(shown_view.expanded()) == 2
    panels = [row for row in range(table.rowCount()) if shown_view.is_panel_row(row)]
    assert len(panels) == 2


def test_a_click_outside_the_arrow_does_not_expand(shown_view) -> None:
    """Обратная сторона: раскрывает **стрелка**, а не строка целиком.

    Без этого предыдущие три теста были бы зелёными и на экране, который
    раскрывается от любого клика, — то есть не отличали бы верное от неверного.
    """
    table = shown_view.table
    index = table.model().index(0, COLUMNS.index("Number"))
    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        table.visualRect(index).center(),
    )
    QApplication.processEvents()

    assert shown_view.expanded() == set()
    # Но выбор строки клик менять обязан — это обычная строка списка.
    assert shown_view._selected_id() is not None


# --- Критерии 6 и 7 наряда 0030: иконки исхода и неизменная сетка -----------------


def _painted(outcome, *, researched: bool = False) -> dict:
    """Отрисовать одну пилюлю и вернуть карту «цвет → координаты его точек».

    Считаются **пиксели**, а не флаг: `design-system.md` §1 требует, чтобы исход
    различался **формой**, и проверить это можно только по нарисованному.
    Координаты, а не количество: галочка и крестик при одной толщине пера дают
    поровну точек (замерено: 38 и 38), и счётчик их не различал бы вовсе.
    """
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui.kit.chips import Chip, FindingChipsDelegate

    kit.apply_theme(QApplication.instance())
    pixmap = QPixmap(360, tokens.ROW_TWO_FINDINGS)
    pixmap.fill(QColor(tokens.WHITE))
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = pixmap.rect()
    option.font = painter.font()
    chip = Chip(
        dimension="Dim. 19", value="+ 0.03", kind="", researched=researched, outcome=outcome
    )
    FindingChipsDelegate()._chip(painter, painter.fontMetrics(), chip, 10, 7, 340)
    painter.end()

    image = pixmap.toImage()
    painted: dict[tuple[int, int, int], set] = {}
    for y in range(image.height()):
        for x in range(image.width()):
            colour = QColor(image.pixel(x, y))
            key = (colour.red(), colour.green(), colour.blue())
            painted.setdefault(key, set()).add((x, y))
    return painted


def _near(painted: dict, colour: str, tolerance: int = 40) -> set:
    """Точки, нарисованные **этим** цветом, с допуском на сглаживание."""
    from PySide6.QtGui import QColor

    wanted = QColor(colour)
    found: set = set()
    for (r, g, b), points in painted.items():
        if max(abs(r - wanted.red()), abs(g - wanted.green()), abs(b - wanted.blue())) < tolerance:
            found |= points
    return found


def test_the_three_outcomes_are_three_different_shapes(qt_app) -> None:
    """**Критерий 6 наряда `0030`:** «три состояния исхода дают **три разные
    фигуры**».

    Правило `design-system.md` §1: цвет никогда не несёт смысл в одиночку. Места
    на слово в пилюле нет — она заведена ради скана взглядом, — поэтому различать
    состояния обязан **контур**, а цвет только усиливает уже прочитанное.

    Различающая величина здесь — **число закрашенных точек контура**: галочка,
    крестик и кружок при одной толщине пера дают разную длину линии, и совпадение
    любых двух означало бы, что нарисована одна фигура в двух цветах. Именно эта
    ошибка и была бы естественной: `permitted` зелёной галочкой, `not_permitted`
    зелёной же галочкой другого оттенка.
    """
    permitted = _painted("permitted")
    refused = _painted("not_permitted")
    undecided = _painted(None)

    tick = _near(permitted, tokens.OUTCOME_PERMITTED)
    cross = _near(refused, tokens.OUTCOME_REFUSED)
    circle = _near(undecided, tokens.N_400)

    assert tick, "галочка не нарисована"
    assert cross, "крестик не нарисован"
    assert circle, "пустой кружок не нарисован"

    # Три **разные** фигуры: сравниваются занятые координаты, а не их число —
    # галочка и крестик при одной толщине пера дают поровну точек (38 и 38), и
    # счётчик объявил бы их одинаковыми. Совпадение любых двух означало бы одну
    # фигуру в двух цветах — ровно ту ошибку, которую канон запрещает прямо.
    assert tick != cross
    assert tick != circle
    assert cross != circle
    # И расходятся они существенно, а не на пиксель сглаживания.
    for first, second in ((tick, cross), (tick, circle), (cross, circle)):
        overlap = len(first & second) / min(len(first), len(second))
        assert overlap < 0.6, overlap


def test_the_undecided_outcome_is_drawn_and_not_left_blank(qt_app) -> None:
    """Правило §3 наряда: «Пустой кружок для «не решено» показывается **всегда**:
    пустое место неотличимо от «иконка не поместилась»».

    Сравнивается с пилюлей, у которой исхода нет вовсе — так выглядел бы экран,
    если бы третье состояние решили не рисовать.
    """
    undecided = _painted(None)

    # Кружок нейтрального цвета есть, и он не совпадает с заливкой пилюли.
    assert _near(undecided, tokens.N_400)
    assert _near(undecided, tokens.N_100)


def test_the_flask_and_the_outcome_are_drawn_side_by_side(qt_app) -> None:
    """**Критерий 6, вторая половина:** две иконки уживаются в одной пилюле.

    Пилюля с исследованием и без него обязана нести исход одинаково: если бы
    мензурка занимала место исхода, у исследованной находки исход пропадал бы —
    и именно это скрыл бы тест, рисующий только один случай.
    """
    lonely = _painted("permitted")
    together = _painted("permitted", researched=True)

    alone = _near(lonely, tokens.OUTCOME_PERMITTED)
    beside = _near(together, tokens.OUTCOME_PERMITTED)

    assert beside, "исход исчез рядом с мензуркой"
    assert _near(together, tokens.N_500), "мензурка не нарисована"

    # Сравнивается **фигура**, приведённая к собственной рамке, а не абсолютные
    # координаты: пилюля с мензуркой шире, исход в ней стоит правее — и обязан,
    # он крайний справа. Разъехалась бы именно фигура, если бы мензурка легла
    # поверх исхода или сжала его.
    def normalised(points: set) -> set:
        left = min(x for x, _ in points)
        top = min(y for _, y in points)
        return {(x - left, y - top) for x, y in points}

    assert normalised(alone) == normalised(beside)


def test_the_panel_grid_did_not_change_when_the_column_was_replaced() -> None:
    """**Критерий 7 наряда `0030`:** «сумма панели раскрытия не изменилась —
    колонка **замещена**, не добавлена».

    Правило §3: «Колонка `Research` в панели раскрытия заменяется на `Outcome` —
    **те же 168 px, сетка не трогается вовсе**». Сумма — то, что отличает
    замещение от добавления: колонка, добавленная рядом, дала бы 1312.
    """
    assert sum(PANEL_WIDTHS.values()) == 1144
    assert PANEL_WIDTHS["Outcome"] == 168
    assert "Research" not in PANEL_WIDTHS
    assert tuple(PANEL_WIDTHS) == PANEL_COLUMNS
