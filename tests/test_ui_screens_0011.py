"""Что наряд 0011 добавил к экранам: язык списка, позиции детали, вердикт, лента.

Отдельный файл, а не дописка в существующие: проверяется не поведение одной
формы, а три добавки §4 наряда и перестройка шасси §3 — они пересекают экраны.

Модальные диалоги здесь перехватываются везде, где тест утверждает, что
операция **проходит**: под offscreen показанное модальное окно ждёт ответа
вечно, и регрессия вешала бы прогон вместо того, чтобы уронить тест
(`CLAUDE.md` §9).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

import ui.kit
from conftest import make_item
from db.models import Direction
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.findings import make_finding
from domain.groups import GPositionSpec, create_group
from domain.inspections import create_inspection
from domain.mappings import bind
from domain.reference import list_values
from ui import kit
from ui.common import DECISION_INSP_LABELS, strip_iso
from ui.deviation_view import COLUMNS, DeviationView
from ui.item_positions_dialog import ItemPositionsDialog
from ui.item_view import ItemView
from ui.kit import tokens
from ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qt_app")

POSITIONS = (
    GPositionSpec(1, 3.75, 0.05, -0.05),
    GPositionSpec(2, 2.0, 0.02, -0.02),
)


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


@pytest.fixture
def no_modals(monkeypatch):
    """Ловушка модальных окон: тест обязан увидеть их, а не повиснуть на них."""
    shown: list[Exception] = []
    monkeypatch.setattr(
        ui.kit, "show_error", lambda parent, error, **kw: shown.append(error)
    )
    return shown


def _bound_item(engine, *, local_number: str = "12"):
    """Деталь с одним размером, привязанным к канонической позиции g1."""
    with session_scope(engine) as session:
        group = create_group(session, "Implant_Con_375_C1", POSITIONS)
        item = make_item(session, "C1-08375A")
        characteristic, _ = get_or_create_characteristic(session, item, local_number)
        bind(session, item, group.positions[0], local_number)
        return item.item_id


# --- §4: язык списка отклонений ----------------------------------------------------


def test_column_order_and_names_follow_the_design(engine) -> None:
    """Состав колонок — то, что наряд 0011 §4 внёс из макета."""
    assert "Dev. qty" in COLUMNS and "Quantity" not in COLUMNS
    assert "Explanation" in COLUMNS
    assert COLUMNS.index("Findings") < COLUMNS.index("Decision")
    # `Inspections` осталась своей колонкой: в макете она уходит в раскрытие
    # строки, а раскрытия в этой сборке нет (§4, «не входит»).
    assert "Inspections" in COLUMNS


def test_the_explanation_reaches_the_list(engine, no_modals) -> None:
    """Обоснование — главный текст прецедента, и в строке оно видно целиком."""
    text = "no effect on assembly — checked in Solidworks"
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, item, "12")
        make_finding(session, deviation, characteristic, direction=Direction.PLUS, value=0.08)
        set_decision(session, deviation, decision="approved", explanation=text)

    view = DeviationView(engine)
    column = COLUMNS.index("Explanation")

    assert view.table.item(0, column).text() == text
    # Целиком — в подсказке: строка обрезается, а текст терять нельзя.
    assert view.table.item(0, column).toolTip() == text
    assert no_modals == []


def test_the_decision_cell_carries_its_code_for_the_pill(engine, no_modals) -> None:
    """Пилюлю красит **код** исхода, а не разбор человеческой подписи."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, item, "12")
        make_finding(session, deviation, characteristic, direction=Direction.PLUS, value=0.08)
        set_decision(session, deviation, decision="sorting", explanation="")

    view = DeviationView(engine)
    cell = view.table.item(0, COLUMNS.index("Decision"))

    assert cell.data(kit.DECISION_ROLE) == "sorting"
    assert cell.text() == "Sorting — 100 % inspection"
    assert no_modals == []


def test_an_empty_list_explains_itself(engine, no_modals) -> None:
    """Канон §8: пустая таблица уступает место объяснению, а не молчит."""
    view = DeviationView(engine)

    assert view.table.isHidden() is True
    assert view.empty.isHidden() is False
    assert "Registration is step 3" in view.empty.body_label.text()
    assert no_modals == []


def test_the_three_kinds_of_cell_behave_by_the_canon(engine, no_modals) -> None:
    """Критерий 7 на **боевом** списке: иврит, латиница и число в одной строке.

    Проверяется отрисованное, а не запрошенное: поверх `displayAlignment` Qt
    накладывает `visualAlignment`, которая под RTL меняет левое на правое —
    тест на запрошенное выравнивание проходит на неверном экране (канон §6).
    """
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

    from ui.common import LTR, RTL

    hebrew = "אין השפעה על ההרכבה"
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, item, "12")
        make_finding(session, deviation, characteristic, direction=Direction.PLUS, value=0.08)
        set_decision(session, deviation, decision="approved", explanation=hebrew)

    view = DeviationView(engine)

    def option(column: int) -> QStyleOptionViewItem:
        prepared = QStyleOptionViewItem()
        view.table.itemDelegate().initStyleOption(
            prepared, view.table.model().index(0, column)
        )
        return prepared

    def drawn(prepared: QStyleOptionViewItem):
        return QApplication.style().visualAlignment(
            prepared.direction, prepared.displayAlignment
        )

    # Ивритская ячейка — RTL по первому сильному символу и к правому краю.
    explanation = option(COLUMNS.index("Explanation"))
    assert explanation.direction == RTL
    assert drawn(explanation) & Qt.AlignmentFlag.AlignRight

    # Латинский идентификатор — LTR, влево, под своей подписью.
    number = option(COLUMNS.index("Number"))
    assert number.direction == LTR
    assert drawn(number) & Qt.AlignmentFlag.AlignLeft

    # Дата сильных символов не несёт: её база объявлена колонкой, не угадана.
    date = option(COLUMNS.index("Date"))
    assert date.direction == LTR
    assert drawn(date) & Qt.AlignmentFlag.AlignLeft

    # Величина — единственная, что идёт вправо: её сравнивают вниз по столбцу.
    quantity = option(COLUMNS.index("Dev. qty"))
    assert quantity.direction == LTR
    assert drawn(quantity) & Qt.AlignmentFlag.AlignRight

    # Счётчик числовой, но не величина — остаётся влево.
    findings = option(COLUMNS.index("Findings"))
    assert findings.direction == LTR
    assert drawn(findings) & Qt.AlignmentFlag.AlignLeft

    assert no_modals == []


# --- §4: диалог позиций детали (В-7) ------------------------------------------------


def test_item_positions_open_from_the_characteristics_column(engine, no_modals) -> None:
    """До наряда 0011 число в колонке было тупиком — раскрыть его было нечем."""
    item_id = _bound_item(engine)

    dialog = ItemPositionsDialog(engine, item_id)

    assert dialog.table.rowCount() == 1
    assert strip_iso(dialog.table.item(0, 0).text()) == "g1"
    assert strip_iso(dialog.table.item(0, 1).text()) == "12"
    assert strip_iso(dialog.table.item(0, 2).text()) == "3.75"
    # Допуск — атомарный токен с минусом канона, а не ASCII-дефисом.
    assert strip_iso(dialog.table.item(0, 3).text()) == "+0.05 / −0.05"
    assert no_modals == []


def test_item_positions_are_read_only(engine) -> None:
    """Диалог показывает канон, а не правит его: правка — в редакторе группы."""
    item_id = _bound_item(engine)

    dialog = ItemPositionsDialog(engine, item_id)

    from PySide6.QtWidgets import QAbstractItemView

    assert dialog.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_the_positions_button_lives_on_the_item_screen(engine, no_modals) -> None:
    """Вход именно с экрана деталей: раскрывается его собственная колонка."""
    _bound_item(engine)

    from ui.item_view import COLUMNS as ITEM_COLUMNS

    view = ItemView(engine)

    assert view.positions_button.isEnabled()
    # Кнопка раскрывает ровно ту колонку, которая до этого была тупиком.
    assert "Characteristics" in ITEM_COLUMNS
    assert no_modals == []


# --- §4: подписи вердикта исследования (В-9) ----------------------------------------


def test_the_inspection_verdict_names_a_judgement_not_an_object() -> None:
    """В-9: `Deviation approved` называл объект, к которому вердикт не привязан.

    Исследование висит на **находке**, а `approved` дословно совпадало с исходом
    отклонения — две разные сущности под одной подписью в одной карточке.
    """
    assert DECISION_INSP_LABELS == {
        "approved": "Acceptable",
        "not_approved": "Not acceptable",
    }


def test_the_stored_verdict_values_did_not_change(engine, no_modals) -> None:
    """Правится подпись, а не данные: в базе остаются `approved` / `not_approved`."""
    from db.models import RefInspectionType

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, item, "12")
        finding = make_finding(
            session, deviation, characteristic, direction=Direction.PLUS, value=0.08
        )
        inspection = create_inspection(
            session,
            finding,
            inspection_type=list_values(session, RefInspectionType)[0],
            decision_insp="approved",
            protocol="p.docx",
        )
        assert inspection.decision_insp == "approved"

    assert no_modals == []


# --- §3: шасси — лента вместо бокового меню -----------------------------------------


def test_the_chassis_is_a_ribbon_not_a_sidebar(engine) -> None:
    """Перестройка §3: боковое меню съедало ширину, которая нужна таблице."""
    window = MainWindow(engine)

    assert window.ribbon.height() == tokens.RIBBON_HEIGHT
    assert not hasattr(window, "sections")
    # Раздел следующего спринта виден и выключен: порядок сборки на виду.
    disabled = [
        button
        for button in window.ribbon.findChildren(QPushButton)
        if not button.isEnabled()
    ]
    assert [button.text() for button in disabled] == [kit.iso("Search  (S8)")]
    window.close()


def test_the_footer_carries_the_database_path_and_the_summary(engine) -> None:
    """Критерий 5: подвал отвечает «с какой базой я работаю» и «сколько записей»."""
    window = MainWindow(engine)
    window.select_section(3)

    assert str(engine.url) in window.database.text()
    assert "Deviations in the database" in window.summary.text()
    window.close()


def test_switching_a_section_repaints_the_footer(engine) -> None:
    """Сводку в подвале пишет активный экран, а не последний перечитанный."""
    window = MainWindow(engine)

    window.select_section(2)
    assert "Items in the database" in window.summary.text()
    window.select_section(1)
    assert "Groups in the database" in window.summary.text()
    window.close()


def _today():
    from datetime import date

    return date.today()
