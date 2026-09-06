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
from conftest import (
    fill_item_form_and_accept,
    make_item,
    rev,
    stub_mapping_dialog,
)
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
from ui.item_positions_dialog import COLUMNS as ItemPositionsColumns
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
        characteristic, _ = get_or_create_characteristic(session, rev(item), local_number)
        bind(session, rev(item), group.positions[0], local_number)
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
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
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
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
        make_finding(session, deviation, characteristic, direction=Direction.PLUS, value=0.08)
        set_decision(session, deviation, decision="sorting", explanation="")

    view = DeviationView(engine)
    cell = view.table.item(0, COLUMNS.index("Decision"))

    assert cell.data(kit.DECISION_ROLE) == "sorting"
    # В колонке списка исход назван коротко; полная формулировка — в диалоге.
    assert cell.text() == "Sorting"
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
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
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
    # Пара отклонений — атомарный токен с минусом канона, а не ASCII-дефисом;
    # знак каждого прочитан из значения (наряд 0015).
    assert strip_iso(dialog.table.item(0, 3).text()) == "+0.05 / −0.05"
    assert no_modals == []


def test_item_positions_show_an_interference_fit_as_entered(engine, no_modals) -> None:
    """Р-2: у посадки с натягом **оба** отклонения плюсовые — и так и показаны.

    Прежняя сборка рисовала знаки в шаблон поверх `abs(value)` и выводила такую
    пару как `+0.05 / −0.02`: поле допуска зеркально, несимметричная посадка
    выглядела симметричной. Тест смотрит на **текст ячейки** — то, что читает
    оператор, — а не на вызов функции показа (`CLAUDE.md` §9).
    """
    from db.models import CharacteristicGroup

    item_id = _bound_item(engine)
    with session_scope(engine) as session:
        position = (
            session.query(CharacteristicGroup).one().positions[0]
        )
        position.tol_plus, position.tol_minus = 0.05, 0.02

    dialog = ItemPositionsDialog(engine, item_id)
    deviations = ItemPositionsColumns.index("Limit deviations")

    assert strip_iso(dialog.table.item(0, deviations).text()) == "+0.05 / +0.02"
    assert no_modals == []


def test_item_positions_name_the_pair_by_iso_286(engine) -> None:
    """Критерий 4: `Tolerance` обещал знак, которого не гарантирует."""
    assert ItemPositionsColumns == (
        "g-position",
        "Local number",
        "Nominal",
        "Limit deviations",
        "State",
    )
    # Прежде та же подпись сверялась и с формой новой детали. Таблицы позиций
    # там больше нет (наряд 0018): номера размеров форма не спрашивает, и
    # составная ячейка осталась в одном месте.


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


# --- О-6: карточка как окно ---------------------------------------------------------


def test_the_card_is_a_resizable_window_with_a_floor(engine, no_modals) -> None:
    """Ревью 0011, О-6: карточка держит шапку, находки и две секции сразу.

    Вертикали ей может не хватить на любом наперёд заданном размере, поэтому
    окно изменяемое, а сжать его ниже читаемого нельзя.
    """
    from ui.card_dialog import CardDialog

    deviation_id = _decided_deviation(engine)

    card = CardDialog(engine, deviation_id)

    assert card.minimumHeight() == tokens.WINDOW_MIN_HEIGHT
    assert card.minimumWidth() == tokens.DIALOG_WIDE
    assert card.height() > card.minimumHeight()
    assert no_modals == []


def test_the_precedent_tabs_scroll_instead_of_squeezing(engine, no_modals) -> None:
    """Секции сохраняют свою высоту, а не делят остаток вертикали пополам."""
    from PySide6.QtWidgets import QScrollArea

    from ui.card_dialog import CardDialog

    deviation_id = _decided_deviation(engine)

    card = CardDialog(engine, deviation_id)

    for index in range(card.tabs.count()):
        assert isinstance(card.tabs.widget(index), QScrollArea)
    # Таблица прецедентов не сжимается до полоски — иначе прокрутка не нужна,
    # а нужна была именно она.
    assert card.same_position.minimumHeight() == tokens.INLINE_TABLE_HEIGHT
    assert no_modals == []


def test_the_precedent_sections_explain_emptiness_in_one_line(engine, no_modals) -> None:
    """Две секции — соседи одной вкладки, значит компактный вариант (канон §8)."""
    from ui.card_dialog import CardDialog

    deviation_id = _decided_deviation(engine)

    card = CardDialog(engine, deviation_id)

    assert card.dimension_empty.compact is True
    assert card.position_empty.compact is True
    # Пустое состояние вкладки целиком остаётся полным: у него есть свой выход.
    assert card.descriptive_hint.compact is False
    assert card.position_hint_box.compact is False
    assert no_modals == []


def test_an_unselected_finding_gets_its_own_reason(engine, no_modals) -> None:
    """Подменять «не выбрано» на «прецедентов нет» значит объяснять не то."""
    from ui.card_dialog import CardDialog

    deviation_id = _decided_deviation(engine)

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(-1, -1)
    card.refresh_precedents()

    assert "No finding selected" in card.dimension_empty.body_label.text()
    assert no_modals == []


def test_the_precedent_pill_is_painted_by_its_code(engine, no_modals) -> None:
    """Найдено снимком доводки: пилюля прецедента красилась как «нет решения».

    Домен отдаёт в строке прецедента **код** исхода, а карточка искала код по
    подписи — поиск не находил ничего, и каждый решённый прецедент рисовался
    контурной пилюлей открытого состояния. Тест смотрит на то, чем красят, а
    не на то, что написано: подпись была верной и дефект не показывала.
    """
    from ui.card_dialog import PRECEDENT_DECISION_COLUMN, CardDialog

    item_id, deviation_id = _deviation_with_a_precedent(engine)

    card = CardDialog(engine, deviation_id)
    cell = card.same_position.item(0, PRECEDENT_DECISION_COLUMN)

    assert cell.text() == "Approved"
    assert cell.data(kit.DECISION_ROLE) == "approved"
    assert no_modals == []


def _deviation_with_a_precedent(engine) -> tuple[int, int]:
    """Две детали на одной канонической позиции: у второй решённый прецедент."""
    with session_scope(engine) as session:
        group = create_group(session, "Implant_Con_375_C1", POSITIONS)

        past_item = make_item(session, "C1-08420B")
        bind(session, rev(past_item), group.positions[0], "77")
        past = register(
            session, item=past_item, wo="W26007201", quantity=40, date=_today()
        )
        past_characteristic, _ = get_or_create_characteristic(session, rev(past_item), "77")
        make_finding(
            session,
            past,
            past_characteristic,
            direction=Direction.MINUS,
            value=0.05,
        )
        set_decision(
            session, past, decision="approved", explanation="no effect on assembly"
        )

        item = make_item(session, "C1-08375A")
        bind(session, rev(item), group.positions[0], "12")
        current = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
        make_finding(
            session, current, characteristic, direction=Direction.PLUS, value=0.08
        )
        return item.item_id, current.deviation_id


def _decided_deviation(engine) -> int:
    """Отклонение с находкой и решением — карточке есть что показать."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
        make_finding(
            session, deviation, characteristic, direction=Direction.PLUS, value=0.08
        )
        set_decision(session, deviation, decision="approved", explanation="checked")
        return deviation.deviation_id


# --- наряд 0018: привязка как часть заведения детали ---------------------------------


@pytest.fixture
def group_engine(engine):
    """Движок с группой из трёх позиций — то, к чему привязывается новая деталь."""
    from domain.groups import GPositionSpec, create_group

    with session_scope(engine) as session:
        create_group(
            session,
            "CG-A",
            (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0), GPositionSpec(3, 0.5)),
        )
    return engine


def test_new_item_with_a_group_opens_the_mapping_at_once(group_engine, monkeypatch) -> None:
    """Критерий §3.5.1: привязка открывается сама — с той деталью и той группой.

    Заведение заканчивается не формой, а завершённой привязкой: в форме находки
    известен только локальный номер размера, и при неполной привязке отклонение
    ляжет мимо канона (§1a наряда 0018).
    """
    import ui.item_view as view_module
    from db.models import CharacteristicGroup, Item
    from domain.mappings import mark_absent

    def operator_closes_every_position(engine, item_id, cg_id, attempt):
        # Привязку доводим до конца: тест смотрит, **с чем** открылось окно, и
        # не должен упереться в вопрос об откате — под offscreen модальное окно
        # ждёт ответа вечно (`CLAUDE.md` §9).
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            for position in session.get(CharacteristicGroup, cg_id).positions:
                mark_absent(session, rev(item), position)

    monkeypatch.setattr(view_module.ItemDialog, "exec", fill_item_form_and_accept())
    calls = stub_mapping_dialog(monkeypatch, operator_closes_every_position)

    view = ItemView(group_engine)
    view.add_button.click()

    with session_scope(group_engine) as session:
        item_id = session.query(Item).one().item_id
        cg_id = session.query(CharacteristicGroup).one().cg_id
    assert calls == [(item_id, cg_id)]


def test_a_completed_mapping_creates_the_item_with_its_dimensions(
    group_engine, monkeypatch
) -> None:
    """Критерий §3.5.3: после «Done» деталь на месте вместе с размерами и группой."""
    import ui.item_view as view_module
    from db.models import Item
    from domain.mappings import bind, mark_absent

    from db.models import CharacteristicGroup
    from domain.items import groups_of

    def operator_maps(engine, item_id, cg_id, attempt):
        # Две позиции получили номер, третьей у детали нет — код 99.
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            positions = sorted(
                session.get(CharacteristicGroup, cg_id).positions, key=lambda p: p.g_index
            )
            bind(session, rev(item), positions[0], "12")
            bind(session, rev(item), positions[1], "19")
            mark_absent(session, rev(item), positions[2])

    monkeypatch.setattr(view_module.ItemDialog, "exec", fill_item_form_and_accept())
    stub_mapping_dialog(monkeypatch, operator_maps)

    view = ItemView(group_engine)
    view.add_button.click()

    with session_scope(group_engine) as session:
        item = session.query(Item).one()
        assert sorted(c.local_number for c in rev(item).characteristics) == ["12", "19"]
        assert [g.name for g in groups_of(item)] == ["CG-A"]
    # И группа видна в колонке `Groups` — экран перечитан.
    from ui.item_view import COLUMNS as ItemViewColumns

    groups_column = ItemViewColumns.index("Groups")
    assert strip_iso(view.table.item(0, groups_column).text()) == "CG-A"


def test_refusing_the_mapping_leaves_no_trace(group_engine, monkeypatch) -> None:
    """Критерий §3.5.4: «Close» с незакрытыми позициями отменяет заведение.

    Проверяется после сеанса, в котором **часть** позиций уже была привязана:
    удалиться обязана не только деталь, но и всё, что за ней записалось.
    """
    from PySide6.QtWidgets import QMessageBox

    import ui.item_dialog as dialog_module
    import ui.item_view as view_module
    from db.models import Characteristic, CharacteristicGroup, ItemPositionAbsent, Item, Mapping
    from domain.mappings import bind, mark_absent

    def operator_gives_up(engine, item_id, cg_id, attempt):
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            positions = sorted(
                session.get(CharacteristicGroup, cg_id).positions, key=lambda p: p.g_index
            )
            bind(session, rev(item), positions[0], "12")
            mark_absent(session, rev(item), positions[1])
            # Третья позиция остаётся нерешённой — привязка неполна.

    monkeypatch.setattr(view_module.ItemDialog, "exec", fill_item_form_and_accept())
    stub_mapping_dialog(monkeypatch, operator_gives_up)
    asked: list[str] = []

    def confirm(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(dialog_module.QMessageBox, "question", staticmethod(confirm))

    view = ItemView(group_engine)
    view.add_button.click()

    # Вопрос задан **до** отката, и он говорит, что деталь не будет заведена.
    assert asked and "will not be created" in asked[0]
    with session_scope(group_engine) as session:
        assert session.query(Item).count() == 0
        assert session.query(Characteristic).count() == 0
        assert session.query(Mapping).count() == 0
        assert session.query(ItemPositionAbsent).count() == 0
        # Канон цел: откат трогает деталь, а не группу.
        assert len(session.query(CharacteristicGroup).one().positions) == 3
    assert view.table.rowCount() == 0


def test_answering_no_returns_to_the_mapping(group_engine, monkeypatch) -> None:
    """Критерий §3.5.4, вторая половина: «нет» возвращает в привязку.

    Закрытое окно бывает и промахом мыши, поэтому откат — только по явному «да».
    """
    from PySide6.QtWidgets import QMessageBox

    import ui.item_dialog as dialog_module
    import ui.item_view as view_module
    from db.models import CharacteristicGroup, Item
    from domain.mappings import bind, mark_absent

    def operator_finishes_on_the_second_go(engine, item_id, cg_id, attempt):
        if attempt == 1:
            return  # первый раз закрыл, ничего не решив
        with session_scope(engine) as session:
            item = session.get(Item, item_id)
            positions = sorted(
                session.get(CharacteristicGroup, cg_id).positions, key=lambda p: p.g_index
            )
            bind(session, rev(item), positions[0], "12")
            mark_absent(session, rev(item), positions[1])
            mark_absent(session, rev(item), positions[2])

    monkeypatch.setattr(view_module.ItemDialog, "exec", fill_item_form_and_accept())
    calls = stub_mapping_dialog(monkeypatch, operator_finishes_on_the_second_go)
    monkeypatch.setattr(
        dialog_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )

    view = ItemView(group_engine)
    view.add_button.click()

    assert len(calls) == 2, "после «нет» привязка обязана открыться снова"
    with session_scope(group_engine) as session:
        assert session.query(Item).count() == 1


def test_without_a_group_no_mapping_is_opened(engine, monkeypatch) -> None:
    """Критерий §3.5.6: группа не выбрана — привязывать нечего."""
    import ui.item_view as view_module
    from db.models import Item

    monkeypatch.setattr(view_module.ItemDialog, "exec", fill_item_form_and_accept(group=None))
    calls = stub_mapping_dialog(monkeypatch)

    view = ItemView(engine)
    view.add_button.click()

    assert calls == []
    with session_scope(engine) as session:
        assert session.query(Item).count() == 1


# --- §3.3a: ранее заведённая деталь — предупреждение без отката ----------------------


def test_an_existing_item_is_warned_but_never_rolled_back(engine, monkeypatch) -> None:
    """Критерий §3.5.7: у заведённой детали привязка закрывается предупреждением.

    Откат здесь невозможен — записи уже лежат, прежнее состояние нигде не
    сохранено, — а запрет производил бы ложные данные: оператор выходил бы из
    окна, вписав номер наугад. Конечное решение — Q-15.
    """
    from PySide6.QtWidgets import QMessageBox

    import ui.item_dialog as dialog_module
    import ui.item_view as view_module
    from db.models import CharacteristicGroup, Item

    item_id = _bound_item(engine)  # деталь с одной привязанной позицией из двух
    with session_scope(engine) as session:
        cg_id = session.query(CharacteristicGroup).one().cg_id

    monkeypatch.setattr(view_module, "choose_cg_for_item", lambda *a, **k: cg_id)
    calls = stub_mapping_dialog(monkeypatch)
    # Окно предупреждения закрывается «Close anyway»: `clickedButton()` не
    # совпадает с кнопкой возврата, и цикл заканчивается.
    monkeypatch.setattr(dialog_module.QMessageBox, "exec", lambda self: 0)

    view = ItemView(engine)
    view.table.setCurrentCell(0, 0)
    view.map_button.click()

    assert len(calls) == 1
    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        assert item is not None, "существующую деталь откатывать нельзя"
        assert [c.local_number for c in rev(item).characteristics] == ["12"]


def test_the_warning_names_the_unfinished_positions(engine) -> None:
    """Текст предупреждения проверяем сам — его читает оператор (§3.3a)."""
    from ui.common import strip_iso
    from ui.item_dialog import incomplete_mapping_text

    one = strip_iso(incomplete_mapping_text(["g4"], "C1-08375A"))
    many = strip_iso(incomplete_mapping_text(["g4", "g7"], "C1-08375A"))

    assert one == "g4 has no state. The mapping of item C1-08375A stays incomplete."
    assert many == (
        "g4, g7 have no state. The mapping of item C1-08375A stays incomplete."
    )


# --- наряд 0017: точка входа в форму детали ------------------------------------------


def _opened_dialogs(monkeypatch) -> list:
    """Перехватить показ формы детали и вернуть список открытых экземпляров.

    Смотрим на то, **с чем форма открылась**, а не на то, что вызов состоялся:
    дефект №12 был именно в аргументах, а не в самом факте вызова.
    """
    import ui.item_view as module

    opened: list = []
    monkeypatch.setattr(module.ItemDialog, "exec", lambda self: opened.append(self) or 0)
    return opened


def test_new_item_from_the_section_opens_a_create_form(engine, monkeypatch) -> None:
    """Критерий 1 наряда 0017: «New item» открывает форму заведения.

    `ItemDialog(engine, self)` клал родителя в слот `item_id` — ревью 0012
    вставило `item_id` вторым параметром, перед `parent`, и вызов молча сменил
    смысл. Форма шла грузить деталь с идентификатором-виджетом:
    `sqlite3.ProgrammingError: type 'ItemView' is not supported`.
    """
    opened = _opened_dialogs(monkeypatch)
    view = ItemView(engine)

    view.add_button.click()

    assert opened, "форма детали не открылась"
    assert opened[0]._item_id is None
    assert opened[0].windowTitle() == "New item"
    assert opened[0].parent() is view


def test_edit_item_from_the_section_opens_the_selected_item(engine, monkeypatch) -> None:
    """Критерий 4: правка детали продолжает работать — и это тот же вход кнопкой."""
    item_id = _bound_item(engine)
    opened = _opened_dialogs(monkeypatch)

    view = ItemView(engine)
    view.table.setCurrentCell(0, 0)
    view.edit_button.click()

    assert opened, "форма детали не открылась"
    assert opened[0]._item_id == item_id
    assert opened[0].windowTitle() == "Edit item"
    # Строка группы в правке скрыта: перепривязка существующей детали — своя
    # работа со своими гарантиями, она вынесена в Q-15 (наряд 0018 §3.3a).
    assert not opened[0].group_row.isVisibleTo(opened[0])


# --- доводка 0012: правка детали, радиокнопки, уплотнение хрома ----------------------


def test_the_item_form_edits_an_existing_item(engine, no_modals) -> None:
    """Ревью 0012 В-2: номер детали правится формой, а не перезаливкой базы."""
    from db.models import Item
    from ui.item_dialog import ItemDialog

    item_id = _bound_item(engine)

    dialog = ItemDialog(engine, item_id)
    assert dialog.windowTitle() == "Edit item"
    assert dialog.number_edit.text() == "C1-08375A"
    # Группа в правке не показывается — см. выше.
    assert not dialog.group_row.isVisibleTo(dialog)

    dialog.number_edit.setText("C1-08375B")
    # Ревизия обязательна: без неё домен отбивает сохранение, форма
    # показывает модальное окно, и прогон под offscreen виснет (§9).
    dialog.revision_edit.setText("A")
    dialog.save()

    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        assert item.item_number == "C1-08375B"
        # Правка имени не трогает размеры — они ссылаются на `item_id`.
        assert [c.local_number for c in rev(item).characteristics] == ["12"]
    assert no_modals == []


def test_a_duplicate_item_number_is_refused_by_the_form(engine, no_modals) -> None:
    """Гард уникальности доходит до оператора сообщением, а не падением."""
    from db.models import GENERAL, RefConnectionType, RefSize
    from domain.items import create_item
    from seed.reference import ref
    from ui.item_dialog import ItemDialog

    item_id = _bound_item(engine)
    with session_scope(engine) as session:
        create_item(
            session,
            item_number="C1-08420B",
            connection_type=ref(session, RefConnectionType, GENERAL),
            size=ref(session, RefSize, GENERAL),
        revision="A",
    )

    dialog = ItemDialog(engine, item_id)
    dialog.number_edit.setText("C1-08420B")
    # Ревизия обязательна: без неё домен отбивает сохранение, форма
    # показывает модальное окно, и прогон под offscreen виснет (§9).
    dialog.revision_edit.setText("A")
    dialog.save()

    assert no_modals and "already exists" in str(no_modals[0])


def test_the_item_screen_has_an_edit_entry(engine, no_modals) -> None:
    """Вход в правку — на экране деталей, рядом с позициями и привязкой."""
    _bound_item(engine)

    view = ItemView(engine)

    assert kit.strip_iso(view.edit_button.text()) == "Edit item"
    assert no_modals == []


def test_the_outcome_is_chosen_by_radio_without_a_default(engine, no_modals) -> None:
    """Канон §4: четыре исхода читают перед выбором, и ни один не предвыбран."""
    from ui.decision_dialog import DecisionDialog

    deviation_id = _decided_deviation(engine)

    dialog = DecisionDialog(engine, deviation_id)

    assert len(dialog.decision.buttons()) == 4
    # У решённого отклонения отмечен его исход, у нового — ничего.
    assert dialog.decision.value() == "approved"
    assert no_modals == []


def test_the_inspection_result_is_chosen_by_radio(engine, no_modals) -> None:
    """Два значения — радиокнопками; без выбора исследование не сохраняется."""
    from db.models import Inspection
    from ui.inspection_dialog import InspectionDialog

    finding_id = _finding_of(engine)

    dialog = InspectionDialog(engine, finding_id)
    assert len(dialog.verdict.buttons()) == 2
    assert dialog.verdict.value() is None

    dialog.protocol.setText("p.docx")
    dialog.save()

    assert no_modals and "inspection result" in str(no_modals[0])
    with session_scope(engine) as session:
        assert session.query(Inspection).count() == 0


def test_the_chrome_is_the_tightened_one(engine) -> None:
    """Ревизия канона 1.3: шесть высот уплотнены, лента и строка — нет."""
    assert tokens.SECTION_HEADER_HEIGHT == 48
    assert tokens.FOOTER_HEIGHT == 26
    assert tokens.BUTTON_HEIGHT == 28
    assert tokens.INPUT_HEIGHT == 26
    assert tokens.TAB_STRIP_HEIGHT == 34
    assert tokens.TABLE_HEADER_HEIGHT == 30
    # Не тронуты: лента (В-5) и строка таблицы (канон §3).
    assert tokens.RIBBON_HEIGHT == 44
    assert tokens.TABLE_ROW_HEIGHT == 40


def _finding_of(engine) -> int:
    """Находка, на которой можно завести исследование."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(
            session, item=item, wo="W26007336", quantity=12, date=_today()
        )
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
        finding = make_finding(
            session, deviation, characteristic, direction=Direction.PLUS, value=0.08
        )
        return finding.finding_id


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
        characteristic, _ = get_or_create_characteristic(session, rev(item), "12")
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
    assert [kit.strip_iso(button.text()) for button in disabled] == [
        "Search — not built yet"
    ]
    window.close()


def test_the_footer_carries_the_database_path_and_the_selection(engine) -> None:
    """Подвал: что выбрано слева, с какой базой работаем справа (макет S1).

    Счётчик выдачи сюда не пишется: он стоит в подзаголовке экрана, и второй
    раз то же число на одном экране не показывается.
    """
    window = MainWindow(engine)
    window.select_section(3)

    assert str(engine.url) in window.database.text()
    assert window.summary.text() == "No selection"
    assert "deviations" in window.deviation_view.summary_text()
    window.close()


def test_switching_a_section_repaints_the_header(engine) -> None:
    """Счётчик выдачи принадлежит экрану и меняется вместе с разделом."""
    window = MainWindow(engine)

    window.select_section(2)
    assert "items" in window.item_view.summary_text()
    window.select_section(1)
    assert "groups" in window.cg_view.summary_text()
    # Подвал при этом говорит про выбор, а не про счётчик.
    assert window.summary.text() == "No selection"
    window.close()


def _today():
    from datetime import date

    return date.today()
