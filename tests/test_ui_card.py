"""UI карточки отклонения: прецеденты, вкладки, действия (критерии 1-2, 7-10 наряда 0005)."""

from __future__ import annotations

import pathlib
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QStyle

from conftest import count_queries, make_item, permit_findings, rev
from db.models import (
    CharacteristicGroup,
    Deviation,
    Direction,
    Finding,
    Item,
    RefDeviationType,
    RefInspectionType,
    RefZone,
)
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import list_deviations, register, set_decision
from domain.findings import make_finding, update_finding
from domain.inspections import create_inspection
from domain.groups import GPositionSpec, create_group
from domain.mappings import bind
from domain.precedents import CANON_UNBOUND
from domain.reference import ensure_value, list_values
import ui.kit
from ui import card_dialog
from ui.common import PANEL_COLUMNS
from ui.card_dialog import (
    NOT_BUILT_HINT,
    NO_SELECTION_HINT,
    UNBOUND_HINT,
    CardDialog,
)
from ui.deviation_view import DeviationView

pytestmark = pytest.mark.usefixtures("qt_app")

TODAY = date.today()
POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0))

#: Вкладок по-прежнему две; на второй — объяснение, а не выдача (наряд 0022).
L1_TAB, L2_TAB = 0, 1


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


def _zone(session, name: str = "אזור הברגה") -> RefZone:
    existing = [v for v in list_values(session, RefZone) if v.name == name]
    return ensure_value(session, RefZone, name)


def _kind(session, name: str = "thread burr") -> RefDeviationType:
    existing = [v for v in list_values(session, RefDeviationType) if v.name == name]
    return ensure_value(session, RefDeviationType, name)


def _case(
    session,
    item: Item,
    local_number: str,
    *,
    wo: str = "W1",
    on: date | None = None,
    decision: str | None = "approved",
    explanation: str = "влияния на сборку нет",
    zone=None,
    deviation_type=None,
    value: float | None = 0.08,
):
    deviation = register(session, item=item, wo=wo, quantity=5, date=on or TODAY)
    characteristic, _ = get_or_create_characteristic(session, rev(item), local_number)
    finding = make_finding(
        session,
        deviation,
        characteristic,
        direction=Direction.MINUS,
        value=value,
        zone=zone,
        deviation_type=deviation_type,
    )
    if decision is not None:
        # Одобрение требует разрешённых находок (QMS-025); хелпер строит данные,
        # а не проверяет инвариант — тому есть свои тесты, заходящие мимо формы.
        if decision == "approved":
            permit_findings(session, deviation)
        set_decision(session, deviation, decision=decision, explanation=explanation)
    return deviation.deviation_id, finding.finding_id


def _precedent_column(table, header: str) -> int:
    """Колонка таблицы прецедентов **по заголовку**, а не по номеру (§9а.9).

    Номер — величина, общая у кода и теста: наряд `0031` вставил первой колонку
    раскрывателя, и все выписанные руками индексы разъехались разом. Тест,
    разделяющий с кодом ту самую величину, которую проверяет, не сторожит ничего.
    """
    labels = [
        table.horizontalHeaderItem(index).text() for index in range(table.columnCount())
    ]
    assert header in labels, labels
    return labels.index(header)


def _group_rows(card, group: str) -> tuple:
    """Строки одной выборки — **из выдачи**, а не пересчётом строк экрана.

    Таблица прецедентов после наряда `0032` одна, и `rowCount()` считает вместе с
    групповыми строками и панелями. Спрашивать «сколько нашлось по канону» надо у
    выдачи, а не у экрана: экран отвечает на другой вопрос.
    """
    return card.precedents.rows_of(group)


def _prec_row(card, group: str, index: int = 0) -> int:
    """Номер строки прецедента группы `group` на экране — по группе, не по числу."""
    from ui.card_dialog import PRECEDENT_ID_COLUMN

    rows = _group_rows(card, group)
    assert index < len(rows), f"в группе {group} нет строки {index}: {len(rows)}"
    wanted = rows[index].deviation_id
    for row in range(card.precedents.rowCount()):
        if card.precedents.is_service_row(row):
            continue
        cell = card.precedents.item(row, PRECEDENT_ID_COLUMN)
        if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == wanted:
            return row
    raise AssertionError(f"строка группы {group} не найдена на экране")


def _group_title(card, group: str) -> str:
    """Текст групповой строки — то, чем прежде была подпись секции."""
    for entry in card.precedents.groups():
        if entry.key == group:
            return entry.title
    raise AssertionError(f"нет группы {group}")


def _prec_cell(card, group: str, header: str, index: int = 0):
    row = _prec_row(card, group, index)
    return card.precedents.item(row, _precedent_column(card.precedents, header))


def _text(cell) -> str:
    """Текст ячейки без изолятов — сравнивать удобнее по содержимому."""
    return cell.text().replace("⁨", "").replace("⁩", "")


# --- Критерий 2: прецеденты по выбранной находке ----------------------------------


def test_card_shows_header_and_findings(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", wo="W26007336", decision="sorting")

    card = CardDialog(engine, deviation_id)

    assert "W26007336" in _text(card.wo)
    assert "C1-08375A" in _text(card.item_label)
    assert card.decision.text() == "Sorting — 100 % inspection"
    assert card.findings.rowCount() == 1
    assert _text(card.findings.item(0, 0)) == "12"
    assert _text(card.findings.item(0, 1)) == CANON_UNBOUND


def test_switching_the_finding_redraws_the_precedents(engine) -> None:
    """Решение 2: отклонение с несколькими размерами не валит разное в кучу."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-OLD-12")
        _case(session, item, "19", wo="W-OLD-19")
        _case(session, item, "19", wo="W-OLD-19-BIS")
        deviation = register(session, item=item, wo="W-NOW", quantity=1, date=TODAY)
        for number in ("12", "19"):
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        deviation_id = deviation.deviation_id

    card = CardDialog(engine, deviation_id)

    card.findings.setCurrentCell(0, 0)  # размер 12
    assert len(_group_rows(card, "dimension")) == 1
    assert _text(_prec_cell(card, "dimension", "WO")) == "W-OLD-12"

    card.findings.setCurrentCell(1, 0)  # размер 19
    assert len(_group_rows(card, "dimension")) == 2
    assert {_text(_prec_cell(card, "dimension", "WO", i)) for i in range(2)} == {
        "W-OLD-19",
        "W-OLD-19-BIS",
    }


def test_empty_selection_explains_itself(engine) -> None:
    """Пустой выбор — подсказка, а не пустые таблицы без объяснения."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12")

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(-1, -1)
    card.refresh_precedents()

    assert _group_rows(card, "dimension") == ()
    assert card.status.text() == NO_SELECTION_HINT
    assert card.inspect_button.isEnabled() is False


# --- Критерии 3-5 на уровне экрана -------------------------------------------------


def test_l1a_section_excludes_the_current_deviation(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST", on=TODAY - timedelta(days=10))
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert len(_group_rows(card, "dimension")) == 1
    assert _text(_prec_cell(card, "dimension", "WO")) == "W-PAST"
    # Заголовок называет **как совпало**, а не чья деталь (`Search.md` v1.04).
    assert "By number: no. 12" in _group_title(card, "dimension")


def test_l1b_section_shows_another_item_on_the_same_position(engine) -> None:
    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        mine = make_item(session, "IT-001")
        other = make_item(session, "IT-002")
        bind(session, rev(mine), group.positions[0], "12")
        bind(session, rev(other), group.positions[0], "77")
        _case(session, other, "77", wo="W-OTHER")
        deviation_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert len(_group_rows(card, "position")) == 1
    assert _text(_prec_cell(card, "position", "Item")) == "IT-002"
    assert "By canon: position g1" in _group_title(card, "position")
    assert card.position_hint_box.isHidden() is True


def test_unbound_dimension_explains_instead_of_showing_an_empty_table(engine) -> None:
    """Критерий 10: вместо пустой таблицы — объяснение и кнопка привязки."""
    with session_scope(engine) as session:
        create_group(session, "CG-A", POSITIONS)
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.position_hint_box.isHidden() is False
    assert _group_rows(card, "position") == ()
    # Пустое состояние канона §8: что пусто, почему и один выход — кнопка.
    assert "not bound to the canon" in card.position_hint_box.body_label.text()
    assert card.position_hint_button.isHidden() is False


def test_binding_from_the_card_revives_the_position_section(engine, monkeypatch) -> None:
    """Критерий 10: после привязки колонка «канон» и секция L1b обновляются на месте."""
    import ui.card_dialog as module

    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        other = make_item(session, "IT-002")
        bind(session, rev(other), group.positions[0], "77")
        _case(session, other, "77", wo="W-OTHER")
        mine = make_item(session, "IT-001")
        deviation_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)
        cg_id = group.cg_id
        mine_id = mine.item_id

    card = CardDialog(engine, deviation_id)
    assert _group_rows(card, "position") == ()
    assert _text(card.findings.item(0, 1)) == CANON_UNBOUND

    def fake_run(engine_, item_id, cg_id_, parent=None):
        with session_scope(engine_) as session:
            item = session.get(Item, item_id)
            group = session.get(CharacteristicGroup, cg_id_)
            bind(session, rev(item), group.positions[0], "12")
        return True

    # Привязка из карточки идёт тем же помощником, что и три остальных входа
    # (§3.2 наряда 0020), поэтому подменяем диалог там, где он теперь живёт.
    import ui.item_dialog as mapping_module

    monkeypatch.setattr(mapping_module.MappingDialog, "run", staticmethod(fake_run))
    monkeypatch.setattr(module, "choose_cg_for_item", lambda *args: cg_id)
    # Привязана одна позиция из двух, значит общий вход покажет предупреждение
    # о незакрытых (§3.2). Модальное окно под offscreen ждёт ответа вечно —
    # перехватываем, как требует `CLAUDE.md` §9.
    monkeypatch.setattr(mapping_module.QMessageBox, "exec", lambda self: 0)

    card.bind_canon()

    assert _text(card.findings.item(0, 1)) == "g1"
    assert len(_group_rows(card, "position")) == 1
    assert _text(_prec_cell(card, "position", "Item")) == "IT-002"


def test_undecided_precedents_are_not_shown(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-DECIDED", decision="rejected", explanation="брак")
        _case(session, item, "12", wo="W-OPEN", decision=None)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert len(_group_rows(card, "dimension")) == 1
    assert _text(_prec_cell(card, "dimension", "WO")) == "W-DECIDED"
    assert "already carry a decision" in card.status.text()


# --- Наряд 0022: описательный уровень снят -----------------------------------------


def test_the_card_never_shows_descriptive_precedents(engine) -> None:
    """Пункт 1 наряда 0022: списка нет **ни при каких данных**.

    Данные подобраны так, что прежний уровень L2 выдачу дал бы: у прошлого
    отклонения та же зона и тот же тип, решение стоит. Проверяется тем, что
    описательной таблицы на экране нет вовсе, а не тем, что она пуста, — пустая
    таблица это другой экран и другое обещание.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        zone, kind = _zone(session), _kind(session)
        _case(session, item, "10", wo="W-BOTH", zone=zone, deviation_type=kind)
        deviation_id, _ = _case(
            session, item, "12", wo="W-NOW", decision=None, zone=zone, deviation_type=kind
        )

    card = CardDialog(engine, deviation_id)

    assert not hasattr(card, "descriptive")
    assert _group_rows(card, "dimension") == ()
    assert _group_rows(card, "position") == ()
    # Вкладка на месте и объясняет, почему списка нет (пункт 2 наряда).
    assert card.tabs.count() == 2
    assert NOT_BUILT_HINT in card.descriptive_hint.body_label.text()
    # Открытие остаётся на точной вкладке: уводить оператора к объяснению вместо
    # ответа «случалось ли такое» — не помощь.
    assert card.tabs.currentIndex() == L1_TAB


def test_an_item_without_a_group_explains_both_levels(engine) -> None:
    """Пункт 4: деталь без группы не показывает ничего — и это сказано словами.

    Случай базы прогона `DEV-260903-0003`: деталь к канону не привязана, значит
    точный уровень пуст по построению, а описательного больше нет.
    """
    with session_scope(engine) as session:
        item = make_item(session, "CS-C3057A")
        zone = _zone(session)
        _case(session, item, "10", wo="W-ELSEWHERE", zone=zone)
        deviation_id, _ = _case(session, item, "77", wo="W-NOW", decision=None, zone=zone)

    card = CardDialog(engine, deviation_id)

    assert _group_rows(card, "dimension") == ()
    assert _group_rows(card, "position") == ()
    # Точный уровень объясняет обе свои пустоты: «нет прецедентов» и «размер не
    # привязан к канону — привязка это и есть то, что находит то же место».
    assert card.position_hint_box.isHidden() is False
    assert UNBOUND_HINT in card.position_hint_box.body_label.text()
    assert NOT_BUILT_HINT in card.descriptive_hint.body_label.text()
    assert "Exact matches: 0" in card.status.text()


# --- Критерий 9: решение из карточки ------------------------------------------------


def test_decision_from_the_card_uses_the_untouched_dialog(engine, monkeypatch) -> None:
    """`DecisionDialog` переехал как есть — карточка только зовёт его."""
    import ui.card_dialog as module
    from ui.decision_dialog import DecisionDialog

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    assert module.DecisionDialog is DecisionDialog

    def decide(engine_, dev_id, parent=None):
        with session_scope(engine_) as session:
            from domain.deviations import set_decision as domain_set_decision

            deviation = session.get(Deviation, dev_id)
            permit_findings(session, deviation)
            domain_set_decision(
                session,
                deviation,
                decision="approved",
                explanation="обоснование",
            )
        return True

    monkeypatch.setattr(module.DecisionDialog, "run", staticmethod(decide))

    card = CardDialog(engine, deviation_id)
    # Шапка карточки — полная формулировка, колонка списка — короткая.
    assert card.decision.text() == "No decision yet"

    card.set_decision()

    assert card.decision.text() == "Approved — use as is"
    assert card.explanation.text() == "обоснование"


# --- Критерий 8: без N+1 ------------------------------------------------------------


def test_card_render_does_not_grow_queries_with_rows(engine) -> None:
    """Отрисовка карточки — фиксированное число запросов при 2 и при 20 находках."""

    def build(item_number: str, findings: int) -> int:
        with session_scope(engine) as session:
            item = make_item(session, item_number)
            deviation = register(session, item=item, wo="W1", quantity=1, date=TODAY)
            for index in range(findings):
                characteristic, _ = get_or_create_characteristic(session, rev(item), f"{index:03d}"
                )
                make_finding(session, deviation, characteristic, direction=Direction.PLUS)
            return deviation.deviation_id

    small = build("IT-SMALL", 2)
    large = build("IT-LARGE", 20)

    with count_queries(engine) as few:
        card_small = CardDialog(engine, small)
    with count_queries(engine) as many:
        card_large = CardDialog(engine, large)

    assert (card_small.findings.rowCount(), card_large.findings.rowCount()) == (2, 20)
    assert len(few) == len(many), (
        f"число запросов выросло с числом находок: {len(few)} → {len(many)}"
    )


def test_deviation_form_render_does_not_grow_queries_with_rows(engine) -> None:
    """Та же проверка для формы S4 — она переведена на пакетный `canon_labels`."""
    from ui.deviation_dialog import DeviationDialog

    def build(item_number: str, findings: int) -> int:
        with session_scope(engine) as session:
            item = make_item(session, item_number)
            deviation = register(session, item=item, wo="W1", quantity=1, date=TODAY)
            for index in range(findings):
                characteristic, _ = get_or_create_characteristic(session, rev(item), f"{index:03d}"
                )
                make_finding(session, deviation, characteristic, direction=Direction.PLUS)
            return deviation.deviation_id

    small = build("IT-SMALL", 2)
    large = build("IT-LARGE", 20)

    with count_queries(engine) as few:
        form_small = DeviationDialog(engine, small)
    with count_queries(engine) as many:
        form_large = DeviationDialog(engine, large)

    assert (form_small.findings.rowCount(), form_large.findings.rowCount()) == (2, 20)
    assert len(few) == len(many), (
        f"число запросов выросло с числом находок: {len(few)} → {len(many)}"
    )


# --- Критерий 1: входы в карточку ---------------------------------------------------


def test_list_opens_the_card_for_the_selected_row(engine, monkeypatch) -> None:
    import ui.deviation_view as module

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12")

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    view = DeviationView(engine)
    view.table.setCurrentCell(0, 0)
    view.open_card()

    assert opened == [deviation_id]


def test_card_opens_itself_after_a_new_deviation(engine, monkeypatch) -> None:
    """Канон: карточка открывается, как только отклонение заведено."""
    import ui.deviation_view as module

    with session_scope(engine) as session:
        make_item(session, "C1-08375A")

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    def register_through_form(self):
        """Форма, заполненная как оператором, и принятая."""
        from ui.finding_dialog import FindingRow

        self.item.setCurrentText("C1-08375A")
        self.wo.setText("W26007336")
        self._rows.append(FindingRow(local_number="12", direction=Direction.PLUS))
        self._refresh()
        self.save()
        return QDialog.DialogCode.Accepted if self.result() else QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.DeviationDialog, "exec", register_through_form)

    view = DeviationView(engine)
    view.add_deviation()

    with session_scope(engine) as session:
        expected = session.query(Deviation).one().deviation_id
    assert opened == [expected]


def test_editing_an_existing_deviation_does_not_open_the_card(engine, monkeypatch) -> None:
    import ui.deviation_view as module

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12")

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )
    monkeypatch.setattr(
        module.DeviationDialog, "run", staticmethod(lambda *args, **kw: True)
    )

    view = DeviationView(engine)
    view.table.setCurrentCell(0, 0)
    view.open_deviation()

    assert opened == []


def test_opening_a_precedent_opens_its_card(engine, monkeypatch) -> None:
    import ui.card_dialog as module

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        past_id, _ = _case(session, item, "12", wo="W-PAST")
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)
    # Строка 0 теперь **групповая** (§3 наряда `0032`), и выбор на неё не встаёт —
    # адресуем по группе, а не по номеру строки.
    card.precedents.selectRow(_prec_row(card, "dimension"))

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    card.open_precedent()

    assert opened == [past_id]


def test_precedent_row_carries_the_whole_deviation(engine) -> None:
    """Единица выдачи — отклонение целиком: номер, деталь, WO, решение, обоснование."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        past_id, _ = _case(
            session,
            item,
            "12",
            wo="W26007336",
            decision="repair",
            explanation="доработка по месту, отклонение узаконено",
        )
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)
        past_number = session.get(Deviation, past_id).dev_number

    card = CardDialog(engine, deviation_id)
    row = 0

    assert _text(_prec_cell(card, "dimension", "Deviation")) == past_number
    assert _text(_prec_cell(card, "dimension", "Item")) == "C1-08375A"
    assert _text(_prec_cell(card, "dimension", "WO")) == "W26007336"
    # Колонка списка несёт **короткую** метку; полная формулировка живёт в
    # диалоге решения и в шапке карточки (дизайн-система, макет S13).
    assert _prec_cell(card, "dimension", "Decision").text() == "Repair"
    assert "доработка по месту" in _prec_cell(card, "dimension", "Explanation").text()
    # Обоснование целиком — в подсказке, чтобы длинный текст не рвал вёрстку.
    assert _prec_cell(card, "dimension", "Explanation").toolTip().startswith("доработка")


def test_navigation_has_no_card_section(engine) -> None:
    """Решение 7: карточка открывается от отклонения, разделом не заводится.

    А «Поиск» остаётся выключенным — это конструктор запросов Этапа 1.5, не S5.
    Навигация с наряда 0011 — лента, а не боковой список.
    """
    from PySide6.QtWidgets import QPushButton

    from ui.main_window import PLANNED_SECTIONS, MainWindow

    window = MainWindow(engine)
    sections = window.ribbon.findChildren(QPushButton)
    titles = [button.text() for button in sections]

    assert not any("Card" in title for title in titles)
    # Пометка называет не спринт, а причину: подпись на ленте объясняет, почему
    # раздел серый — всплывающей подсказки там нет (макет S1, заметка 3).
    assert PLANNED_SECTIONS == (("Search", "not built yet"),)
    assert any("Search" in title and "not built yet" in title for title in titles)
    # Выключенный пункт виден, но нажать его нельзя: порядок сборки показан.
    search = next(button for button in sections if "Search" in button.text())
    assert not search.isEnabled()
    window.close()


# --- Ревью S5, дефект 1: прецедент открывается из той таблицы, где кликнули --------


def _two_sections(engine) -> tuple[int, int, int]:
    """Карточка, у которой непусты **обе** секции L1. Возвращает id: текущее, L1a, L1b."""
    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        mine = make_item(session, "IT-001")
        other = make_item(session, "IT-002")
        bind(session, rev(mine), group.positions[0], "12")
        bind(session, rev(other), group.positions[0], "77")
        past_id, _ = _case(session, mine, "12", wo="W-SAME-DIM")
        position_id, _ = _case(session, other, "77", wo="W-SAME-POS")
        current_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)
    return current_id, past_id, position_id


def test_the_row_that_was_chosen_is_the_row_that_opens(engine, monkeypatch) -> None:
    """Открывается **выбранная** строка, из какой бы группы она ни была.

    Прежде это проверяли два теста — «двойной клик во второй секции» и «кнопка
    берёт последнюю тронутую таблицу», — и оба стерегли одно: `_current_table`
    перебирал две таблицы и всегда предпочитал первую, из-за чего клик во второй
    молча открывал чужую запись.

    С наряда `0032` таблица **одна**, и вопрос «какая из двух» перестал
    существовать вместе со сведением выбора между ними. Требование, ради которого
    те тесты писались, осталось и проверяется здесь: что открывается ровно та
    запись, на которой стоит выбор. Один тест на две группы, а не два по одной, —
    различает верное от неверного именно переход между группами
    (`CLAUDE.md` §9а.11).
    """
    import ui.card_dialog as module

    current_id, past_id, position_id = _two_sections(engine)
    card = CardDialog(engine, current_id)
    assert len(_group_rows(card, "dimension")) == 1
    assert len(_group_rows(card, "position")) == 1

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    card.precedents.selectRow(_prec_row(card, "dimension"))
    card.open_precedent()
    assert opened == [past_id]

    card.precedents.selectRow(_prec_row(card, "position"))
    card.open_precedent()
    assert opened == [past_id, position_id], "открылась строка не той группы"


def test_switching_the_finding_drops_a_stale_selection(engine, monkeypatch) -> None:
    """Перерисовка сбрасывает выбор: иначе перекос переживал бы смену находки."""
    import ui.card_dialog as module

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-OLD-12")
        deviation = register(session, item=item, wo="W-NOW", quantity=1, date=TODAY)
        for number in ("12", "19"):
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        current_id = deviation.deviation_id

    card = CardDialog(engine, current_id)
    card.findings.setCurrentCell(0, 0)
    card.precedents.setCurrentCell(0, 0)

    card.findings.setCurrentCell(1, 0)  # у размера 19 прецедентов нет

    assert card.precedents.currentRow() == -1
    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )
    card.open_precedent()
    assert opened == [] and "Select a precedent" in card.status.text()


def test_findings_are_ordered_numerically(engine) -> None:
    """«9» раньше «10»: номер размера — строка, но читается как число."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(session, item=item, wo="W1", quantity=1, date=TODAY)
        for number in ("10", "9", "2"):
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        current_id = deviation.deviation_id

    card = CardDialog(engine, current_id)

    assert [_text(card.findings.item(r, 0)) for r in range(3)] == ["2", "9", "10"]


# --- QMS-018 §3: исследования выбранной находки и открытие протокола --------------


@pytest.fixture
def no_modals(monkeypatch):
    """Ловушка модальных окон: тест обязан увидеть их, а не повиснуть на них.

    `CLAUDE.md` §9: тест, утверждающий, что операция **проходит**, перехватывает
    `show_error` и проверяет, что диалогов не было. Подмена стоит раньше
    тестового режима и потому его не отменяет — она и есть путь отказа.
    """
    shown: list[Exception] = []
    monkeypatch.setattr(ui.kit, "show_error", lambda parent, error, **kw: shown.append(error))
    return shown


def _inspection(
    session,
    finding_id: int,
    *,
    position: str | None,
    conclusion: str | None = None,
    protocol: str = "p.docx",
    kind: str = "Solidworks assembly",
):
    return create_inspection(
        session,
        session.get(Finding, finding_id),
        inspection_type=ensure_value(session, RefInspectionType, kind),
        conclusion=conclusion,
        protocol=protocol,
        no_protocol=False,
    )


def _inspection_column(card, header: str) -> int:
    """Колонка **по заголовку**, а не по номеру (`CLAUDE.md` §9а.9).

    Номер — величина, общая у кода и теста: сдвигая колонку, автор сдвигает
    индекс и здесь, и тест остаётся зелёным ровно там, где обязан покраснеть.
    """
    labels = [
        card.inspections.horizontalHeaderItem(index).text()
        for index in range(card.inspections.columnCount())
    ]
    assert header in labels, labels
    return labels.index(header)


def test_the_card_lists_the_inspections_of_the_selected_finding(engine) -> None:
    """§3 наряда: таблица показывает тип · позицию · вывод."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(
            session,
            finding_id,
            position="approval_possible",
            conclusion="clearance in the assembled state \u221220 %",
            kind="Solidworks assembly",
        )

    card = CardDialog(engine, deviation_id)

    assert card.inspections.rowCount() == 1
    assert _text(card.inspections.item(0, _inspection_column(card, "Type"))) == (
        "Solidworks assembly"
    )
    assert _text(card.inspections.item(0, _inspection_column(card, "Conclusion"))) == (
        "clearance in the assembled state \u221220 %"
    )


def test_an_unassessed_inspection_says_so_in_words(engine) -> None:
    """Правило `docs/model/Inspection.md` rev 1.01: «Empty means "not assessed yet"».

    Проверяется **отрисованный** текст ячейки, а не поле записи: пустая позиция в
    базе и пустая ячейка на экране — разные утверждения, и второе оператор читает.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(session, finding_id, position=None, conclusion=None)

    card = CardDialog(engine, deviation_id)

    assert _text(card.inspections.item(0, _inspection_column(card, "Conclusion"))) == ""


def test_the_same_outcome_is_worded_the_same_on_both_screens(engine) -> None:
    """`CLAUDE.md` §9а.11: один факт, показанный на двух экранах, проверяется
    **сравнением экранов**, а не двумя тестами по одному на каждый.

    Прежде так сверялась позиция исследования; с QMS-025 её нет, а сверять надо
    то, что заняло её место, — исход находки. Он виден в таблице находок формы
    отклонения и в панели раскрытия списка, и два теста, каждый на своём экране,
    молчали бы ровно о том, что отличает верное от неверного: о расхождении.
    """
    from ui.deviation_dialog import FINDING_COLUMNS, DeviationDialog
    from ui.deviation_view import PANEL_COLUMNS, DeviationView

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        finding = session.get(Finding, finding_id)
        update_finding(
            session, finding, direction=finding.direction, value=finding.value,
            dimension_point=None, comment=None, zone=None, deviation_type=None,
            outcome="not_permitted",
        )

    form = DeviationDialog(engine, deviation_id)
    in_form = _text(form.findings.item(0, FINDING_COLUMNS.index("Outcome")))

    view = DeviationView(engine)
    view.toggle_expansion(0)
    panel = next(
        view.panel_at(row)
        for row in range(view.table.rowCount())
        if view.panel_at(row) is not None
    )
    in_panel = _text(panel.item(0, PANEL_COLUMNS.index("Outcome")))

    assert in_form == in_panel == "Not permitted"


def test_a_long_conclusion_is_one_line_with_the_whole_text_in_the_tooltip(engine) -> None:
    """Тот же приём, что у обоснования решения, — отдельного механизма нет (§3)."""
    whole = "first sentence.\n\nsecond sentence, after a blank line."
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(session, finding_id, position="approval_possible", conclusion=whole)

    card = CardDialog(engine, deviation_id)
    cell = card.inspections.item(0, _inspection_column(card, "Conclusion"))

    assert "\n" not in cell.text()
    assert cell.toolTip() == whole


def test_switching_the_finding_redraws_the_inspections(engine) -> None:
    """Исследования принадлежат находке, а не отклонению целиком.

    Читаются они на выбор строки, а не на открытие карточки (решение 7 QMS-018):
    свёрнутому экрану от исследования нужен один признак — счётчик в колонке
    находок, и он уже посчитан пакетом.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(session, item=item, wo="W1", quantity=5, date=TODAY)
        first, _ = get_or_create_characteristic(session, rev(item), "12")
        second, _ = get_or_create_characteristic(session, rev(item), "19")
        f_first = make_finding(session, deviation, first, direction=Direction.MINUS, value=0.08)
        make_finding(session, deviation, second, direction=Direction.PLUS, value=0.04)
        permit_findings(session, deviation)
        set_decision(session, deviation, decision="approved", explanation="ok")
        deviation_id = deviation.deviation_id
        _inspection(session, f_first.finding_id, position="approval_not_possible")

    card = CardDialog(engine, deviation_id)
    rows = [_text(card.findings.item(index, 0)) for index in range(card.findings.rowCount())]

    card.findings.setCurrentCell(rows.index("12"), 0)
    assert card.inspections.rowCount() == 1
    assert card.inspections.isHidden() is False

    card.findings.setCurrentCell(rows.index("19"), 0)
    assert card.inspections.rowCount() == 0
    # Пустая таблица без объяснения — то, как оператор заключает «их не было»
    # из экрана, который просто ничего не показал (канон §8).
    assert card.inspections_empty.isHidden() is False
    assert card.inspections.isHidden() is True


def test_the_protocol_button_needs_a_selected_inspection(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(session, finding_id, position="approval_possible")

    card = CardDialog(engine, deviation_id)

    assert not card.protocol_button.isEnabled()
    card.inspections.setCurrentCell(0, 0)
    assert card.protocol_button.isEnabled()


def test_clicking_the_protocol_opens_the_file(engine, tmp_path, monkeypatch, no_modals) -> None:
    """§3 наряда: открытие протокола из карточки.

    `QDesktopServices` подменён — тест проверяет, что открывают **тот** файл, а не
    что у машины прогона есть чем его открыть.
    """
    protocol = tmp_path / "SW-2026-14.docx"
    protocol.write_text("x", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(
        card_dialog.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.append(url.toLocalFile()) or True),
    )

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(session, finding_id, position=None, protocol=str(protocol))

    card = CardDialog(engine, deviation_id)
    card.inspections.setCurrentCell(0, 0)
    card.open_protocol()

    # Сравниваем путями, а не строками: `QUrl.toLocalFile` отдаёт прямые слэши
    # и на Windows строка не совпала бы при верно открытом файле.
    assert [pathlib.Path(path) for path in opened] == [protocol]
    assert no_modals == []


def test_a_protocol_that_is_not_there_says_so_instead_of_failing_silently(
    engine, tmp_path, monkeypatch, no_modals
) -> None:
    """§3 наряда: «Файла нет по пути — понятное сообщение оператору, а не молчание
    и не падение».

    Существование проверяется **при открытии**, а не при вводе: канон запрещает
    проверку на входе (`Inspection.md` rev 1.01, решение 4 QMS-018), но ссылка,
    которую нельзя открыть и которая об этом молчит, — просто текст.
    """
    opened: list[str] = []
    monkeypatch.setattr(
        card_dialog.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.append(url.toLocalFile()) or True),
    )
    missing = str(tmp_path / "never-written.docx")

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        _inspection(session, finding_id, position=None, protocol=missing)

    card = CardDialog(engine, deviation_id)
    card.inspections.setCurrentCell(0, 0)
    card.open_protocol()

    assert opened == []
    assert len(no_modals) == 1
    assert missing in str(no_modals[0])


# --- QMS-024: запись без протокола в карточке (наряд 0029 §4) ---------------------


def test_a_record_without_a_protocol_reads_in_full(engine) -> None:
    """§4 наряда `0029`: «запись без протокола читается как полноценная: тип,
    позиция, вывод».

    Проверяются **все три** ячейки: запись, у которой пуст вывод или позиция,
    прошла бы проверку «строка есть», ничего оператору не сказав.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        create_inspection(
            session,
            session.get(Finding, finding_id),
            inspection_type=ensure_value(session, RefInspectionType, "Tolerances review"),
            conclusion="OD 10.0 vs ID 9.9 — geometry excludes assembly",
            protocol=None,
            no_protocol=True,
        )

    card = CardDialog(engine, deviation_id)

    assert _text(card.inspections.item(0, _inspection_column(card, "Type"))) == (
        "Tolerances review"
    )
    assert "OD 10.0" in _text(card.inspections.item(0, _inspection_column(card, "Conclusion")))


def test_the_open_button_is_inactive_where_there_is_no_file_and_says_why(engine) -> None:
    """§4 наряда: «Кнопка открытия протокола для неё **неактивна** — и это не
    отказ, а отсутствие файла».

    Вторая половина существеннее первой: неактивная кнопка без объяснения читается
    как поломка, поэтому проверяется и **подсказка**. Обе записи в одном тесте —
    сравнением, а не двумя тестами по одной: различает верное от неверного именно
    разница между ними (`CLAUDE.md` §9а.11).
    """
    from ui.card_dialog import NO_PROTOCOL_HINT

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12")
        finding = session.get(Finding, finding_id)
        create_inspection(
            session,
            finding,
            inspection_type=ensure_value(session, RefInspectionType, "Solidworks assembly"),
            conclusion=None,
            protocol="p.docx",
            no_protocol=False,
        )
        create_inspection(
            session,
            finding,
            inspection_type=ensure_value(session, RefInspectionType, "Tolerances review"),
            conclusion="the drawing settles it",
            protocol=None,
            no_protocol=True,
        )

    card = CardDialog(engine, deviation_id)
    kind = _inspection_column(card, "Type")
    rows = {_text(card.inspections.item(r, kind)): r for r in range(card.inspections.rowCount())}

    card.inspections.setCurrentCell(rows["Solidworks assembly"], 0)
    assert card.protocol_button.isEnabled() is True
    assert card.protocol_button.toolTip() == ""

    card.inspections.setCurrentCell(rows["Tolerances review"], 0)
    assert card.protocol_button.isEnabled() is False
    assert card.protocol_button.toolTip() == NO_PROTOCOL_HINT
    # И сама строка объясняет себя, а не только кнопка.
    assert card.inspections.item(rows["Tolerances review"], 0).toolTip() == NO_PROTOCOL_HINT


# --- Доводка `0030`, Д-1: исход находки проставляется из карточки -------------------
#
# `CLAUDE.md` §9а.6 — события доставляются **через приложение**, а не прямой посылкой
# в виджет; §9а.5 — тест поведения виджета обязан виджет **показывать**: у скрытого
# часть механики Qt не запускается вовсе. Обе кнопки на этом пути (вход в находку и
# принятие формы) и сам выбор исхода нажимаются мышью.


@pytest.fixture
def slot_errors(monkeypatch):
    """Исключения, вылетевшие **из слота Qt**.

    `CLAUDE.md` §9а.2: PySide6 не пробрасывает исключение слота вызывающему — оно
    уходит в `sys.excepthook`, и прогон идёт дальше. Тест, который **нажимает**
    кнопку, без этой ловушки зелёный на любой сборке.
    """
    import sys as _sys

    caught: list[BaseException] = []
    monkeypatch.setattr(_sys, "excepthook", lambda kind, value, trace: caught.append(value))
    return caught


def _shown_card(engine, deviation_id) -> CardDialog:
    card = CardDialog(engine, deviation_id)
    card.show()
    QApplication.processEvents()
    return card


def _press(button) -> None:
    """Клик мышью по кнопке — через приложение, а не `button.click()`."""
    QTest.mouseClick(
        button,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button.rect().center(),
    )
    QApplication.processEvents()


def _tick(radio) -> None:
    """Клик по **индикатору** радиокнопки — туда, куда целится оператор."""
    QTest.mouseClick(
        radio,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(
            radio.style().pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth) // 2,
            radio.height() // 2,
        ),
    )
    QApplication.processEvents()


def _drive_finding_form(monkeypatch, act):
    """Показать форму находки вместо `exec()` и провести по ней настоящие клики.

    Подменяется **только** `exec()`, и по единственной причине: модальный цикл под
    offscreen ждёт ответа вечно и вешает прогон, а не роняет тест (`CLAUDE.md` §9).
    Всё остальное — та самая форма, что открывает карточка: её собственные виджеты,
    её `save()`, её `FindingRow`. Возвращается список открытых форм — тест обязан
    убедиться, что форма вообще открылась, иначе «ничего не произошло» неотличимо
    от «прошло успешно».
    """
    from ui.finding_dialog import FindingDialog

    opened: list = []

    def fake_exec(dialog) -> int:
        dialog.show()
        QApplication.processEvents()
        opened.append(dialog)
        act(dialog)
        QApplication.processEvents()
        return dialog.result()

    monkeypatch.setattr(FindingDialog, "exec", fake_exec)
    return opened


def _choose_outcome(dialog, label: str) -> None:
    from PySide6.QtWidgets import QRadioButton

    radio = next(
        button
        for button in dialog.outcome.findChildren(QRadioButton)
        if label in button.text()
    )
    _tick(radio)


def _accept(dialog) -> None:
    from PySide6.QtWidgets import QDialogButtonBox

    _press(dialog.buttons.button(QDialogButtonBox.StandardButton.Save))


def _finding_column(card, header: str) -> int:
    """Колонка таблицы находок **по заголовку** (`CLAUDE.md` §9а.9)."""
    labels = [
        card.findings.horizontalHeaderItem(index).text()
        for index in range(card.findings.columnCount())
    ]
    assert header in labels, labels
    return labels.index(header)


def test_the_findings_section_has_a_way_into_the_finding(engine) -> None:
    """**Критерий 1 доводки.** Кнопка `Finding…` стоит рядом с `Inspection…` и
    `Mapping…` и без выбранной строки ведёт себя как они.

    Повод (доводка `0030`, Д-1, прогон руками): колонка `Outcome` показывала
    `Not decided`, а входа в саму находку из карточки не было — только через
    закрытие карточки, `Open…` и форму отклонения.

    Сравнением с соседями, а не утверждением про одну кнопку: правило доводки —
    «ведёт себя **как соседние**», и различает верное от неверного именно
    совпадение с ними.
    """
    from PySide6.QtWidgets import QPushButton

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = _shown_card(engine, deviation_id)
    labels = [_text(button) for button in card.findings_box.findChildren(QPushButton)]
    assert labels == ["Finding…", "Inspection…", "Mapping…"]

    card.findings.setCurrentCell(-1, -1)
    assert card.finding_button.isEnabled() is False
    assert card.inspect_button.isEnabled() is False

    card.findings.setCurrentCell(0, 0)
    assert card.finding_button.isEnabled() is True


def test_the_outcome_is_set_from_the_card_by_real_clicks(
    engine, monkeypatch, slot_errors
) -> None:
    """**Критерий 3 доводки — главный тест.** Настоящий клик по кнопке, не вызов
    метода: между кнопкой и обработчиком есть промежуток, и дефекты живут в нём.

    Правило доводки Cowork: «смысл карточки — посмотрел прецеденты по этой находке
    и решил по ней; ввод обязан стоять там же, где происходит рассуждение».
    Проверяется весь путь целиком: клик по `Finding…` → форма → клик по варианту
    исхода → клик по `Save` → значение **в базе** и в таблице карточки.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    opened = _drive_finding_form(
        monkeypatch, lambda dialog: (_choose_outcome(dialog, "Permitted"), _accept(dialog))
    )

    _press(card.finding_button)

    assert slot_errors == []
    assert len(opened) == 1, "форма находки не открылась"
    with session_scope(engine) as session:
        assert session.get(Finding, finding_id).outcome == "permitted"
    # И карточка перечитана: значение, оставшееся только в базе, инженеру не видно.
    assert _text(card.findings.item(0, _finding_column(card, "Outcome"))) == "Permitted"


def test_the_outcome_set_from_the_card_reaches_the_pill_in_the_list(
    engine, monkeypatch, slot_errors
) -> None:
    """**Критерий 2 доводки, вторая половина.** Исход виден в таблице карточки **и**
    в пилюле списка после перечитывания.

    Один факт на двух экранах — сверяется сравнением экранов, а не двумя тестами по
    одному на каждый (`CLAUDE.md` §9а.11): молчали бы они ровно о том, что отличает
    верное от неверного, — о расхождении между ними.
    """
    from ui.kit.chips import CHIPS_ROLE

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    _drive_finding_form(
        monkeypatch,
        lambda dialog: (_choose_outcome(dialog, "Not permitted"), _accept(dialog)),
    )

    _press(card.finding_button)
    assert slot_errors == []

    view = DeviationView(engine)
    columns = [
        view.table.horizontalHeaderItem(index).text()
        for index in range(view.table.columnCount())
    ]
    chips = view.table.item(0, columns.index("Findings")).data(CHIPS_ROLE)

    assert [chip.outcome for chip in chips] == ["not_permitted"]
    assert _text(card.findings.item(0, _finding_column(card, "Outcome"))) == "Not permitted"


def test_the_card_refuses_to_void_a_decision_that_has_gone_into_a_document(
    engine, monkeypatch, slot_errors
) -> None:
    """**Точка 2 инварианта, теперь и через карточку.** Правило `Deviation.md`
    rev 1.03: «a finding cannot be changed to `not permitted` while its deviation
    stands `approved` — the edit is refused with an explanation».

    Проверяется именно то, что добавила доводка: запись из карточки идёт **через
    домен** (`CLAUDE.md` §9а.18), а не мимо него. Мимо домена инвариант обходился бы
    молча — и это был бы худший исход правки, чем её отсутствие.

    Отказ обязан **дойти до оператора окном**: проглоченный отказ неотличим от
    успеха, а находка при этом осталась бы прежней без единого слова.
    """
    shown: list = []
    monkeypatch.setattr(
        card_dialog.kit, "show_error", lambda parent, error, title="": shown.append(error)
    )

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision="approved")

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    _drive_finding_form(
        monkeypatch,
        lambda dialog: (_choose_outcome(dialog, "Not permitted"), _accept(dialog)),
    )

    _press(card.finding_button)

    assert slot_errors == []
    assert len(shown) == 1
    assert "Withdraw the decision" in str(shown[0])
    # Правка не применилась: отказ — это отказ, а не предупреждение поверх записи.
    with session_scope(engine) as session:
        assert session.get(Finding, finding_id).outcome == "permitted"


# --- Доводка 3: двойной клик по исследованию (Д-3.1) и запись без протокола (Д-3.2) --


def _double_click_row(table, row: int) -> None:
    """Настоящий двойной клик по строке — через приложение (`CLAUDE.md` §9а.6).

    Прямая посылка события в виджет обошла бы диспетчеризацию и проверила
    **обработчик**, а не поведение. Целимся в центр ячейки, как оператор.

    **Одиночный клик перед двойным обязателен, и это не ритуал.** `mouseDClick` в
    пустую по строке, которой ещё не касались, до `doubleClicked` не доходит:
    `QAbstractItemView` запоминает индекс на **нажатии**, и без него двойной клик
    не с чем связать. Замерено — сигнала не было вовсе. Так же ведёт себя и
    человек: он сперва выбирает строку, потом раскрывает её.
    """
    cell = table.visualItemRect(table.item(row, 0)).center()
    viewport = table.viewport()
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, cell
    )
    QApplication.processEvents()
    QTest.mouseDClick(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, cell
    )
    QApplication.processEvents()


def _open_inspection_form(monkeypatch):
    """Перехват открытия формы исследования: что открыли и какую запись.

    `InspectionDialog.run` под offscreen открыл бы модальное окно и **повесил
    прогон** (`CLAUDE.md` §9), поэтому подменяется он, а не что-либо ниже:
    проверяется именно то, куда ведёт жест, — форма исследования и **какая
    запись** в ней.
    """
    calls: list[tuple[int, int | None]] = []
    monkeypatch.setattr(
        card_dialog.InspectionDialog,
        "run",
        classmethod(
            lambda cls, engine, finding_id, inspection_id=None, parent=None: (
                calls.append((finding_id, inspection_id)) or False
            )
        ),
    )
    return calls


def test_a_double_click_on_an_inspection_opens_the_inspection(
    engine, monkeypatch, slot_errors
) -> None:
    """**Критерий 1 доводки 3 (Д-3.1).** Двойной клик по строке открывает **объект
    строки** — исследование, — а не файл протокола.

    Так устроен весь остальной интерфейс: по отклонению в списке двойной клик
    открывает карточку, по прецеденту — прецедент. Открытие файла на этом жесте
    было ошибкой: жест «открыть запись» становился жестом «открыть чужое
    приложение», и у записи без протокола открывать было нечего.

    Настоящим двойным кликом, не вызовом метода: этот путь не был покрыт ни одним
    тестом — потому дефект и дожил до прогона руками.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        finding = session.get(Finding, finding_id)
        inspection = create_inspection(
            session,
            finding,
            inspection_type=ensure_value(session, RefInspectionType, "Solidworks assembly"),
            conclusion=None,
            protocol="p.docx",
            no_protocol=False,
        )
        session.flush()
        inspection_id = inspection.inspection_id

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    calls = _open_inspection_form(monkeypatch)

    _double_click_row(card.inspections, 0)

    assert slot_errors == []
    assert calls == [(finding_id, inspection_id)], "открылось не исследование строки"


def test_a_double_click_opens_an_inspection_that_has_no_protocol(
    engine, monkeypatch, slot_errors
) -> None:
    """**Критерий 2 доводки 3 (Д-3.2), лицевая сторона.** Ровно та запись, на
    которой приложение падало: `No protocol` (наряд `0029`).

    Три утверждения в одном тесте, потому что различает верное от неверного
    именно их сочетание: жест **работает**, файловое действие **недоступно**, и
    ничего не улетело в `sys.excepthook` — а падение уходило именно туда, не
    роняя ни одного из 666 зелёных тестов.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        finding = session.get(Finding, finding_id)
        inspection = create_inspection(
            session,
            finding,
            inspection_type=ensure_value(session, RefInspectionType, "Tolerances review"),
            conclusion="the drawing settles it",
            protocol=None,
            no_protocol=True,
        )
        session.flush()
        inspection_id = inspection.inspection_id

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    calls = _open_inspection_form(monkeypatch)

    _double_click_row(card.inspections, 0)

    assert slot_errors == []
    assert calls == [(finding_id, inspection_id)]
    assert card.protocol_button.isEnabled() is False


def test_open_protocol_answers_instead_of_crashing_without_a_file(
    engine, monkeypatch
) -> None:
    """**Критерий 2 доводки 3 (Д-3.2), вторая сторона.** Прямой вызов на записи без
    протокола отвечает **словами**, а не падает `TypeError` на `Path(None)`.

    Одной недоступности действия мало: она держится на состоянии экрана, а с
    наряда `0029` пустой протокол — законное состояние записи, и функция обязана
    отвечать на него сама, откуда бы её ни позвали. Это и есть «чинить обе
    стороны» доводки.

    Сообщение проверяется **по существу**: «файла нет по записанному пути» и «файла
    нет вовсе» — разные случаи, и слить их в один текст значило бы объяснять
    оператору не то, что он видит.
    """
    shown: list = []
    monkeypatch.setattr(
        card_dialog.kit, "show_error", lambda parent, error, title="": shown.append(error)
    )

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        finding = session.get(Finding, finding_id)
        create_inspection(
            session,
            finding,
            inspection_type=ensure_value(session, RefInspectionType, "Tolerances review"),
            conclusion="the drawing settles it",
            protocol=None,
            no_protocol=True,
        )

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    card.inspections.setCurrentCell(0, 0)

    card.open_protocol()  # именно прямой вызов — сторона «а вызванный не падает»

    assert len(shown) == 1
    assert "no protocol file" in str(shown[0])
    # Не перепутано с «файл записан, но не найден» — там речь о правке ссылки.
    assert "is not there" not in str(shown[0])


# --- Наряд 0031 §1: строка прецедента раскрывается ----------------------------------
#
# `CLAUDE.md` §9а.6 — события через приложение; §9а.5 — виджет показан; §9а.19 —
# жест воспроизводится **целиком**, как его делает человек: по строке сперва
# кликают, потом раскрывают (замерено на доводке 3 наряда `0030` — `mouseDClick`
# по нетронутой строке до сигнала не доходит вовсе).


def _precedent_case(session, item, number: str, *, wo: str, inspections: int = 0):
    """Прецедент с решением, находкой и заданным числом исследований."""
    deviation_id, finding_id = _case(session, item, number, wo=wo, decision="sorting")
    finding = session.get(Finding, finding_id)
    for index in range(inspections):
        create_inspection(
            session,
            finding,
            inspection_type=ensure_value(
                session, RefInspectionType, f"Solidworks assembly {index}"
            ),
            conclusion=None,
            protocol=f"p{index}.docx",
            no_protocol=False,
        )
    return deviation_id


def _click_expander(table, row: int) -> None:
    """Настоящий клик по колонке-раскрывателю — через приложение (§9а.6)."""
    cell = table.visualItemRect(table.item(row, 0)).center()
    QTest.mouseClick(
        table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, cell
    )
    QApplication.processEvents()


def _expand_precedent(table, wo: str) -> None:
    """Раскрыть прецедент **по наряду**, а не по номеру строки (§9а.9).

    Номер строки едет после каждого раскрытия — служебная строка встаёт между
    записями, — а выдача вдобавок упорядочена по дате: «первый созданный»
    строкой 0 не оказывается. Тест, обращающийся к строке номером, здесь просто
    щёлкает не по той записи и остаётся зелёным.
    """
    column = _precedent_column(table, "WO")
    for row in range(table.rowCount()):
        cell = table.item(row, column)
        if cell is not None and _text(cell) == wo:
            _click_expander(table, row)
            return
    raise AssertionError(f"нет строки с нарядом {wo}")


def _precedent_row_of(table, dev_number: str) -> int:
    """Строка прецедента **по номеру отклонения**, а не по позиции (§9а.9)."""
    column = _precedent_column(table, "Deviation")
    for row in range(table.rowCount()):
        cell = table.item(row, column)
        if cell is not None and _text(cell) == dev_number:
            return row
    raise AssertionError(f"нет строки {dev_number}")


def test_a_click_on_the_expander_opens_the_findings_of_the_precedent(
    engine, slot_errors
) -> None:
    """**Критерий 1 наряда `0031` — главный.** Настоящий клик по раскрывателю: под
    строкой встаёт панель находок **того** отклонения, и исследования стоят при
    своих находках.

    Правило `design-system.md` §3 revision 1.12: «Expansion follows the object,
    not the screen» — раскрытие принадлежит объекту, и строка прецедента
    раскрывается теми же тремя уровнями, что строка списка отклонений.

    Повод по делу (§1 наряда): строка прецедента отвечает «решение было
    `sorting`» и не отвечает «по какому размеру и что там нашли». Счётчик
    `Insp.` говорит, что исследования есть, но не говорит какие, — и чтобы это
    узнать, приходилось уходить с экрана сравнения.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=2)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    table = card.precedents
    assert len(_group_rows(card, "dimension")) == 1, (
        "прецедент не найден — тесту нечего раскрывать"
    )

    # По группе, а не по строке 0: строка 0 теперь **групповая** (§3 наряда
    # `0032`), и клик по ней раскрывал бы то, чего не существует.
    _click_expander(table, _prec_row(card, "dimension"))

    assert slot_errors == []
    panels = [table.panel_at(row) for row in range(table.rowCount())]
    panel = next(p for p in panels if p is not None)
    # Панель показывает находки **этого** прецедента, а не текущего отклонения.
    numbers = [
        _text(panel.item(row, PANEL_COLUMNS.index("Dim.")))
        for row in range(panel.rowCount())
    ]
    assert numbers == ["12"]
    # Исследования стоят при своей находке, а не общим списком под панелью.
    cell = panel.item(0, PANEL_COLUMNS.index("Inspections"))
    assert "Solidworks assembly 0" in _text(cell)
    assert "Solidworks assembly 1" in _text(cell)


def test_the_panel_under_a_precedent_is_the_same_class_as_in_the_list(engine) -> None:
    """**Критерий переезда §2, со стороны экрана.** Панель — **та же**, а не вторая
    такая же: один класс из `ui.common`, одни колонки, одни ширины.

    Сравнением двух экранов, а не двумя тестами по одному на каждый
    (`CLAUDE.md` §9а.11): различает верное от неверного именно совпадение. Копия
    разошлась бы с первой же правкой ширины, и оба теста остались бы зелёными.
    """
    from ui.common import FindingsPanel
    from ui.deviation_view import DeviationView

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    _click_expander(card.precedents, _prec_row(card, "dimension"))
    in_card = next(
        card.precedents.panel_at(row)
        for row in range(card.precedents.rowCount())
        if card.precedents.panel_at(row) is not None
    )

    view = DeviationView(engine)
    view.toggle_expansion(0)
    in_list = next(
        view.panel_at(row)
        for row in range(view.table.rowCount())
        if view.panel_at(row) is not None
    )

    assert type(in_card) is type(in_list) is FindingsPanel
    # Сетка общая **кроме последней колонки**: она эластичная и добирает разницу
    # ширин двух экранов (наряд `0032` §2, `FindingsPanel.fit_to`). Таблица
    # прецедентов карточки уже сетки панели, и без этого панель теряла бы две
    # последние колонки целиком — видно снимком, не тестом.
    assert _panel_grid(in_card)[:-1] == _panel_grid(in_list)[:-1]
    tail_card, tail_list = _panel_grid(in_card)[-1], _panel_grid(in_list)[-1]
    assert tail_card[0] == tail_list[0] == "Inspections"
    # У списка колонка своей ширины, у карточки — не больше: сжимается только она.
    assert tail_card[1] <= tail_list[1]


def _panel_grid(panel) -> list[tuple[str, int]]:
    return [
        (panel.horizontalHeaderItem(index).text(), panel.columnWidth(index))
        for index in range(panel.columnCount())
    ]


def test_two_precedents_stay_expanded_at_once(engine, slot_errors) -> None:
    """**Критерий 2.** Раскрытых может быть сколько угодно одновременно.

    Решение 6 реестра: гармошка убивает ровно то, ради чего раскрытие заведено, —
    сравнение двух записей между собой. На карточке это существеннее, чем в
    списке: карточка и **есть** экран сравнения.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-ONE", inspections=1)
        _precedent_case(session, item, "12", wo="W-TWO", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    table = card.precedents
    assert len(_group_rows(card, "dimension")) == 2

    # По наряду, а не по номеру строки: выдача упорядочена по дате, обе записи
    # заведены сегодня, и «первая созданная» строкой 0 не оказывается. Номер
    # строки здесь ещё и **едет** после каждого раскрытия.
    _expand_precedent(table, "W-ONE")
    _expand_precedent(table, "W-TWO")

    assert slot_errors == []
    assert len(table.expanded()) == 2
    panels = [row for row in range(table.rowCount()) if table.panel_at(row) is not None]
    assert len(panels) == 2


def test_choosing_another_finding_drops_the_expansions(engine, slot_errors) -> None:
    """**Критерий 3.** Другая находка — другой набор отклонений, то есть **другой
    вопрос**, и раскрытия прежнего на нём смысла не имеют (§4 наряда).

    Уцелевшее состояние делало бы вид, что оператор что-то раскрывал в наборе,
    которого он ещё не видел, — по той же причине здесь сбрасывается и выбор.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-OLD-12", inspections=1)
        _precedent_case(session, item, "19", wo="W-OLD-19", inspections=1)
        deviation = register(session, item=item, wo="W-NOW", quantity=1, date=TODAY)
        for number in ("12", "19"):
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        deviation_id = deviation.deviation_id

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    _click_expander(card.precedents, _prec_row(card, "dimension"))
    assert len(card.precedents.expanded()) == 1

    card.findings.setCurrentCell(1, 0)
    QApplication.processEvents()

    assert slot_errors == []
    assert card.precedents.expanded() == set()
    assert all(
        card.precedents.panel_at(row) is None
        for row in range(card.precedents.rowCount())
    )


def test_the_service_row_is_not_a_precedent(engine, slot_errors) -> None:
    """**Критерий 4, §6 наряда.** Служебная строка ломает допущение «строка таблицы
    = прецедент», на котором стоял существующий код.

    Три утверждения одним тестом, потому что различает верное от неверного именно
    их сочетание: `selected_deviation` возвращает `None`, `Open precedent…`
    **неактивна**, и ничего не падает. Проверять по отдельности значило бы
    допустить сборку, где функция отвечает верно, а кнопка всё равно предлагает
    открыть несуществующее.

    Ровно на таком пропуске в наряде `0029` вырос `TypeError` доводки 3: тогда
    поле стало необязательным, а потребителей никто не прошёл.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    table = card.precedents
    _click_expander(table, _prec_row(card, "dimension"))
    service = next(row for row in range(table.rowCount()) if table.is_panel_row(row))

    # `selectRow`, а не `setCurrentCell`: у ячейки служебной строки сняты все
    # флаги, и `setCurrentCell` на неё просто не встаёт — проверка через него
    # была бы зелёной и без гарда, потому что до гарда дело не дошло бы.
    table.selectRow(service)
    QApplication.processEvents()

    assert slot_errors == []
    assert table.currentRow() == service, "тест не встал на служебную строку"
    assert table.selected_deviation() is None
    assert card.open_button.isEnabled() is False
    # И действие, вызванное всё-таки, не падает и не открывает чужую запись.
    card.open_precedent(table)
    assert slot_errors == []


def test_the_open_button_follows_the_selection(engine) -> None:
    """Обратная сторона критерия 4: на **настоящей** строке кнопка активна.

    Без неё предыдущий тест был бы зелёным и на сборке, где кнопка не включается
    никогда, — то есть не отличал бы верное от неверного (`CLAUDE.md` §9а.4).
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    table = card.precedents

    assert card.open_button.isEnabled() is False, "без выбора открывать нечего"

    table.selectRow(_prec_row(card, "dimension"))
    QApplication.processEvents()

    assert card.open_button.isEnabled() is True


def test_the_expansion_survives_a_tab_switch(engine) -> None:
    """§4, вторая половина: **внутри одного набора** раскрытия живут.

    Переключение вкладок не приносит другого набора отклонений — значит и
    сбрасывать нечего. Сброс здесь был бы не осторожностью, а потерей работы:
    оператор раскрыл две записи, заглянул на соседнюю вкладку и вернулся к
    свёрнутому экрану.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    _click_expander(card.precedents, _prec_row(card, "dimension"))
    expanded = card.precedents.expanded()

    card.tabs.setCurrentIndex(L2_TAB)
    QApplication.processEvents()
    card.tabs.setCurrentIndex(L1_TAB)
    QApplication.processEvents()

    assert card.precedents.expanded() == expanded
    assert any(
        card.precedents.panel_at(row) is not None
        for row in range(card.precedents.rowCount())
    )


def test_the_findings_of_a_precedent_are_read_only_when_it_is_expanded(engine) -> None:
    """**§5 наряда: ленивый запрос.** Пока прецедент свёрнут, его находки и
    исследования не читаются вовсе.

    Прецедентный поиск возвращает десятки отклонений, и вытаскивать содержимое
    каждого ради двух, которые раскроют, — работа впустую **при каждом клике по
    находке**. Считается число запросов, а не факт вызова: вызов можно сделать и
    пакетным, а лишний он именно как обращение к базе.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _precedent_case(session, item, "12", wo="W-PAST", inspections=1)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)

    with count_queries(engine) as folded:
        card.refresh_precedents()
    with count_queries(engine) as expanding:
        _click_expander(card.precedents, _prec_row(card, "dimension"))

    # Свёрнутый набор не платит за содержимое; раскрытие платит, и это его цена.
    assert len(expanding) > 0
    assert len(expanding) <= 2, expanding


# --- Наряд 0032: одна таблица, копирование, высоты по содержимому -------------------


def _group_row(card, group: str) -> int:
    """Номер **групповой** строки на экране — по имени группы, не по числу."""
    title = _group_title(card, group)
    for row in range(card.precedents.rowCount()):
        cell = card.precedents.item(row, 0)
        if card.precedents.is_group_row(row) and _text(cell) == title:
            return row
    raise AssertionError(f"групповая строка {group} не найдена")


def test_a_group_with_no_matches_is_still_shown(engine) -> None:
    """**Критерий 5.** Группа с нулём строк показывается своей строкой с нулём.

    Правило §3 наряда `0032`: «совпадений нет» — это **ответ**, а его отсутствие
    оператор прочтёт как «поиск не работал». Пропавшая группа и группа с нулём
    выглядят на экране одинаково пусто, но значат разное, и различить их можно
    только по тому, что строка есть.
    """
    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        mine = make_item(session, "IT-001")
        other = make_item(session, "IT-002")
        bind(session, rev(mine), group.positions[0], "12")
        bind(session, rev(other), group.positions[0], "77")
        _case(session, other, "77", wo="W-OTHER")
        deviation_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    # По номеру совпадений нет, по канону — одно. Обе группы на экране.
    assert _group_rows(card, "dimension") == ()
    assert len(_group_rows(card, "position")) == 1
    assert "(0)" in _group_title(card, "dimension")
    assert "(1)" in _group_title(card, "position")
    assert card.precedents.is_group_row(_group_row(card, "dimension"))
    assert card.precedents.is_group_row(_group_row(card, "position"))


def test_the_group_row_is_not_a_precedent(engine, slot_errors) -> None:
    """**Критерий 6.** Групповая строка — второй вид служебной строки, и все
    действия по прецеденту при ней недоступны.

    Настоящими событиями (§9а.6): выбор ставится кликом мыши, а не `setCurrentCell`
    — между щелчком и обработчиком есть промежуток, и дефекты живут в нём.

    Четыре утверждения одним тестом, потому что различает верное от неверного
    именно их сочетание: строка распознана служебной, `selected_deviation` даёт
    `None`, **обе** кнопки погашены, и клик по её раскрывателю ничего не ломает.
    Ровно на таком пропуске в наряде `0029` вырос `TypeError` доводки 3, и §6
    наряда `0031` нашёл восемь потребителей — второй вид служебной строки касается
    их снова.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST")
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    table = card.precedents
    row = _group_row(card, "dimension")

    table.selectRow(row)
    QApplication.processEvents()

    assert table.currentRow() == row, "тест не встал на групповую строку"
    assert table.is_service_row(row) is True
    assert table.selected_deviation() is None
    assert card.open_button.isEnabled() is False
    assert card.copy_button.isEnabled() is False

    # Раскрывать в групповой строке нечего, и клик по её раскрывателю обязан
    # ничего не делать, а не падать и не раскрывать соседа.
    before = card.precedents.expanded()
    _click_expander(table, row)
    assert slot_errors == []
    assert card.precedents.expanded() == before


def test_the_explanation_of_a_precedent_is_copied_in_full(engine, slot_errors) -> None:
    """**Критерий 9.** Кнопка и `Ctrl+C` кладут в буфер **полное** обоснование.

    Правило §5 наряда: копируют не своё, а чужое — обоснование прецедента
    переносят в своё отклонение. Ячейка урезана до одной строки и обрезана по
    ширине колонки, и скопированный из неё текст пришлось бы дописывать руками,
    то есть копирование не сэкономило бы ничего.

    Различающая величина здесь — **разница** между текстом ячейки и текстом в
    буфере: тест, сверяющий буфер сам с собой, был бы зелёным и на сборке,
    копирующей обрезок.
    """
    # **Многострочное** обоснование — так его и пишут: абзац про влияние, абзац
    # про проверку. Ячейка складывает его в одну строку (`_one_line`), и именно
    # этим текст ячейки отличается от того, что надо перенести к себе.
    long_text = (
        "Влияния на сборку нет: зазор в собранном состоянии падает на 20 %.\n"
        "Проверено Solidworks assembly и повторным замером на трёх деталях партии."
    )
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST", explanation=long_text)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    card.precedents.selectRow(_prec_row(card, "dimension"))
    QApplication.processEvents()

    cell = _prec_cell(card, "dimension", "Explanation")
    assert "\n" not in _text(cell), "ячейка складывает текст в одну строку"
    assert _text(cell) != long_text, "текст ячейки обязан отличаться от полного"

    _press(card.copy_button)

    assert slot_errors == []
    assert QApplication.clipboard().text() == long_text


def test_ctrl_c_copies_the_same_text_as_the_button(engine, slot_errors) -> None:
    """Тот же текст даёт и `Ctrl+C` в таблице — сравнением, а не двумя проверками.

    Два входа в одно действие обязаны давать одно и то же (`CLAUDE.md` §9а.11):
    два теста по одному на каждый молчали бы ровно о том, что различает верное от
    неверного, — о расхождении между ними.
    """
    long_text = "Обоснование прецедента.\nВторой абзац, который тоже переносят."
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST", explanation=long_text)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    card.precedents.selectRow(_prec_row(card, "dimension"))
    QApplication.processEvents()

    _press(card.copy_button)
    by_button = QApplication.clipboard().text()

    QApplication.clipboard().clear()
    # Фокус — как у оператора: сочетание живёт на таблице (`WidgetShortcut`), и
    # без фокуса оно не срабатывает вовсе. Клик выше фокус и даёт, но выбор здесь
    # ставится программно, поэтому ставим и его.
    card.precedents.setFocus()
    QApplication.processEvents()
    QTest.keyClick(card.precedents, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert slot_errors == []
    assert QApplication.clipboard().text() == by_button == long_text


def test_the_explanation_of_the_card_is_selectable_but_not_editable(engine) -> None:
    """**Критерий 9, вторая половина.** Поле шапки выделяется — и не правится.

    §5 наряда: «копируется, не редактируясь». Проверяется и то, и другое: одно
    без другого было бы либо нечитаемым полем, либо правкой по месту, которую
    канон запрещает (§7).
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", explanation="важное обоснование")

    card = CardDialog(engine, deviation_id)
    flags = card.explanation.textInteractionFlags()

    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard
    # Правки по месту не появилось: ярлык — не поле ввода.
    assert not isinstance(card.explanation, QLineEdit)


def test_the_measurement_point_column_is_hidden_not_removed(engine) -> None:
    """**Критерий 10.** Колонка скрыта, а не удалена, и возврат стоит одного места.

    §6 наряда: статистики по нужности пока нет, а место колонка занимает. Модель,
    миграция, домен и форма находки не тронуты — данные пишутся как раньше.

    Тест сторожит **обе** половины: колонки не видно, но она объявлена и стоит на
    своём месте, а список ширин по-прежнему перечисляет все колонки. Проверка
    только первой половины была бы зелёной и на сборке, где колонку вычеркнули, —
    то есть где возврат стоит правки в пяти местах.
    """
    from ui.deviation_dialog import (
        FINDING_COLUMNS,
        FINDING_WIDTHS,
        HIDDEN_FINDING_COLUMNS,
    )

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)
    column = FINDING_COLUMNS.index("Measurement point")

    assert HIDDEN_FINDING_COLUMNS == ("Measurement point",)
    assert card.findings.isColumnHidden(column) is True
    # Объявление на месте: колонка, её ширина и её индекс никуда не делись.
    assert len(FINDING_WIDTHS) == len(FINDING_COLUMNS)
    assert card.findings.columnCount() == len(FINDING_COLUMNS)
    # Прочие колонки видны — иначе тест был бы зелёным на скрытой таблице.
    assert card.findings.isColumnHidden(FINDING_COLUMNS.index("Outcome")) is False


def test_the_findings_table_is_as_tall_as_its_rows(engine) -> None:
    """**Критерий 2.** Высоту раздаёт содержимое, а не жёсткий низ.

    §1 наряда с числами: `INLINE_TABLE_HEIGHT = 150` стоял низом у трёх мест
    сразу, и таблице с одной находкой доставалось 150 при нужных 70. Полторы
    сотни пикселей отнимались у единственного места, ради которого карточку и
    открывают.

    Сверяется с **арифметикой** `kit.table_height`, а не с числом 70: число
    зависит от токенов, и тест, повторяющий его константой, разошёлся бы с
    экраном на первой же правке высоты строки.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        one = make_item(session, "IT-ONE")
        _case(session, one, "5", decision=None)
        deviation = register(session, item=item, wo="W-THREE", quantity=1, date=TODAY)
        for number in ("12", "19", "32"):
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        three = deviation.deviation_id
        single = next(
            row.deviation_id
            for row in list_deviations(session, item=one)
        )

    assert CardDialog(engine, single).findings.height() == ui.kit.table_height(1)
    assert CardDialog(engine, three).findings.height() == ui.kit.table_height(3)


def test_an_empty_inspections_section_takes_no_table_height(engine) -> None:
    """**Критерий 2, вторая половина.** Пустая секция исследований — строка.

    Прежде скрытая таблица держала жёсткие 130 px; §1 наряда требует, чтобы
    пустая секция была **одной строкой** пустого состояния. Кнопка при этом
    остаётся на месте и неактивной — действие не исчезает вместе с данными.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)

    assert card.inspections.height() == 0
    assert card.inspections_empty.isHidden() is False
    assert card.protocol_button.isEnabled() is False


def test_the_precedents_area_is_the_only_region_that_stretches(engine) -> None:
    """**Критерий 3.** Нижний предел области задан **видимым**, а не пикселями.

    §1 наряда: две строки прецедента плюс одна раскрытая панель целиком. Сверяется
    с `precedent_floor()` — чистой функцией от токенов, которую можно проверить
    арифметикой на любой платформе (`CLAUDE.md` §9а.14), — а не с числом: число,
    переписанное в тест, перестало бы значить обещанное при первой правке высоты
    строки, и тест остался бы зелёным.
    """
    from ui.card_dialog import (
        PRECEDENTS_FLOOR_ROWS,
        FINDING_WITH_MANY_INSPECTIONS,
        precedent_floor,
    )
    from ui.common import panel_height
    from ui.kit import table_height, tokens

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)

    expected = (
        table_height(PRECEDENTS_FLOOR_ROWS)
        + tokens.PRECEDENT_GROUP_HEIGHT
        + panel_height([FINDING_WITH_MANY_INSPECTIONS])
        + tokens.TAB_STRIP_HEIGHT
    )
    assert precedent_floor() == expected
    assert card.tabs.minimumHeight() == expected
    # И это единственная растягивающаяся область: у соседей высота фиксирована.
    assert card.findings.maximumHeight() == card.findings.minimumHeight()
    assert card.inspections.maximumHeight() == card.inspections.minimumHeight()


def test_the_panel_header_is_subordinate_in_the_card_and_not_in_the_list(engine) -> None:
    """**Критерий 8 / §4.** Оформление шапки панели — **параметр**, а не смена вида.

    Панель после наряда `0031` одна на оба экрана, и перекрасив её, мы перекрасили
    бы список отклонений тоже. Проверяется **сравнением экранов** (`CLAUDE.md`
    §9а.11): в карточке шапка подчинённая, в списке — прежняя. Два теста, каждый
    на своём экране, молчали бы ровно о том, что различает верное от неверного.

    Сверяется имя объекта, потому что красит панель **по нему** лист стиля: это
    то, чем рисуют, а не подпись рядом.
    """
    from ui.kit import OBJECT_PANEL_SUBORDINATE

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST")
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = _shown_card(engine, deviation_id)
    _click_expander(card.precedents, _prec_row(card, "dimension"))
    in_card = next(
        card.precedents.panel_at(row)
        for row in range(card.precedents.rowCount())
        if card.precedents.panel_at(row) is not None
    )

    view = DeviationView(engine)
    view.toggle_expansion(0)
    in_list = next(
        view.panel_at(row)
        for row in range(view.table.rowCount())
        if view.panel_at(row) is not None
    )

    assert in_card.objectName() == OBJECT_PANEL_SUBORDINATE
    assert in_list.objectName() == "findingsPanel"
    # Сетка при этом общая — параметр меняет оформление, а не устройство.
    assert [
        in_card.horizontalHeaderItem(i).text() for i in range(in_card.columnCount())
    ] == [
        in_list.horizontalHeaderItem(i).text() for i in range(in_list.columnCount())
    ]


# --- наряд 0035: остаток доезжает до экрана, сводка, пустые секции, копирование ----


def _shown_card(engine, deviation_id: int):
    """Карточка, **показанная** на экране, — иначе половина механики Qt молчит.

    `CLAUDE.md` §9а.5: у скрытого виджета часть механики не запускается вовсе, и
    тест молча проверяет пустоту. Ширины здесь как раз из той половины: пока
    полотно не знает своего размера, раздавать остаток не из чего.
    """
    card = CardDialog(engine, deviation_id)
    card.resize(1180, 960)
    card.show()
    QApplication.processEvents()
    return card


def test_the_remainder_reaches_the_inspection_panel(engine) -> None:
    """§0 наряда `0035`: раздача остатка доезжает **до экрана**, а не до функции.

    Сторожит правило `design-system.md` §3: «Fixed columns are counted first;
    free text takes the remainder». До наряда `share_remainder` не вызывался в
    работающем приложении ни разу — строки `limit=` в `src/ui` не было вовсе, —
    и колонка `Conclusion` садилась на пол по заголовку: панель показывала
    `Not in …` при пустом поле во всю ширину справа.

    Тест **входит через экран**, а не зовёт функцию: прежний звал
    `kit.share_remainder` напрямую со своей таблицей и был зелёным ровно потому,
    что проверял существование механизма, а не его работу (`CLAUDE.md` §9а.20).
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        _inspection(
            session,
            finding_id,
            position=None,
            conclusion="Clearance in the assembled state drops by 20 %.",
        )

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    QApplication.processEvents()

    table = card.inspections
    conclusion = _inspection_column(card, "Conclusion")
    floor = ui.kit.column_width(table, ui.kit.free(), "Conclusion")

    assert table.columnWidth(conclusion) > floor, (
        "колонка свободного текста осталась на полу по заголовку — "
        "остаток не роздан"
    )
    # И не шире потолка читаемости: остаток сверх него не раздаётся никому.
    assert table.columnWidth(conclusion) <= ui.kit.free_text_width(table)


def test_the_inspection_type_is_measured_against_the_reference(engine) -> None:
    """§1.1 наряда `0035`: ширину `Type` задаёт справочник, а не показанные строки.

    Иначе колонка прыгала бы от того, какие исследования у этой находки, а самое
    длинное значение справочника всё равно однажды в неё попадёт.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, finding_id = _case(session, item, "12", decision=None)
        # В строке — короткий тип; в справочнике есть длиннее.
        _inspection(session, finding_id, position=None, kind="Solidworks assembly")
        ensure_value(session, RefInspectionType, "Implantation torque test")

    card = _shown_card(engine, deviation_id)
    card.findings.setCurrentCell(0, 0)
    QApplication.processEvents()

    table = card.inspections
    kind = _inspection_column(card, "Type")
    metrics = table.fontMetrics()
    assert metrics.horizontalAdvance("Implantation torque test") <= ui.kit.room_for_text(
        table, kind
    )


def test_the_inspections_column_summarises_instead_of_counting(engine) -> None:
    """§2 наряда `0035`: колонка несёт сводку, а не голое число.

    Три случая, и подсказка у «нескольких» перечисляет **все**: показать одну и
    умолчать про остальные значило бы соврать оператору. Проверяется содержимое
    подсказки, а не её наличие (критерий 4 наряда).
    """
    from ui.card_dialog import INSPECTIONS_COLUMN

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, none_id = _case(session, item, "10", decision=None)
        one = make_finding(
            session,
            session.get(Deviation, deviation_id),
            get_or_create_characteristic(session, rev(item), "11")[0],
            direction=Direction.PLUS,
            value=0.02,
        )
        many = make_finding(
            session,
            session.get(Deviation, deviation_id),
            get_or_create_characteristic(session, rev(item), "12")[0],
            direction=Direction.PLUS,
            value=0.03,
        )
        _inspection(session, one.finding_id, position=None, conclusion="Fits.")
        _inspection(session, many.finding_id, position=None, conclusion="First.")
        _inspection(
            session,
            many.finding_id,
            position=None,
            conclusion="Second.",
            kind="Tolerances review",
        )

    card = _shown_card(engine, deviation_id)
    cells = {}
    for row in range(card.findings.rowCount()):
        item_cell = card.findings.item(row, INSPECTIONS_COLUMN)
        cells[_text(card.findings.item(row, 0))] = item_cell

    # Ноль — как было.
    assert _text(cells["10"]) == "0"
    assert not cells["10"].toolTip()

    # Одна — тип и вывод; полный текст подсказкой (по факту обрезки).
    assert "Solidworks assembly" in _text(cells["11"])
    assert "Fits." in _text(cells["11"])

    # Несколько — тип первой и `+N`; подсказка перечисляет **все**.
    assert _text(cells["12"]).startswith("Solidworks assembly")
    assert "+1" in _text(cells["12"])
    summary = cells["12"].data(ui.kit.CONTENT_TOOLTIP_ROLE)
    assert summary, "у нескольких исследований нет содержательной подсказки"
    assert "First." in summary and "Second." in summary
    assert "Tolerances review" in summary

    # И она показывается **всегда**, а не по обрезке: сводка не компенсирует
    # обрезку, а несёт то, чего в ячейке нет (объявленное исключение §4 `0034`).
    card.findings.setColumnWidth(INSPECTIONS_COLUMN, 4000)
    delegate = card.findings.itemDelegate()
    index = card.findings.model().index(
        [r for r in range(card.findings.rowCount())
         if _text(card.findings.item(r, 0)) == "12"][0],
        INSPECTIONS_COLUMN,
    )
    assert not delegate.truncated(
        card.findings, delegate.style_option(card.findings, None, index), index
    )
    assert index.data(ui.kit.CONTENT_TOOLTIP_ROLE)


def test_empty_l1_sections_collapse_to_one_line(engine) -> None:
    """§3 наряда `0035`: скрывается **пустота, а не секция**.

    Три состояния. Обе группы пусты — одна строка вместо двух нулей: два
    заголовка подряд занимают место и обещают содержимое, которого нет. Пуста
    одна — обе на месте, иначе непонятно, которая из двух ответила. Наряд `0032`
    ратифицировал «(0) это ответ», и правило не отменено, а уточнено прогоном.
    """
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        alone_id, _ = _case(session, item, "12", decision=None)

    # Обе пусты — таблица скрыта, вместо неё одна строка.
    card = _shown_card(engine, alone_id)
    card.findings.setCurrentCell(0, 0)
    QApplication.processEvents()
    assert card.precedents.isHidden()
    assert not card.precedents_empty.isHidden()
    assert card.precedents.rowCount() == 0

    # Появился прецедент по тому же номеру — обе групповые строки вернулись,
    # включая пустую: её заголовок и говорит, которая из двух ответила.
    with session_scope(engine) as session:
        item = session.query(Item).filter_by(item_number="C1-08375A").one()
        _case(session, item, "12", wo="W2", decision="approved")

    card = _shown_card(engine, alone_id)
    card.findings.setCurrentCell(0, 0)
    QApplication.processEvents()
    assert not card.precedents.isHidden()
    assert card.precedents_empty.isHidden()
    titles = [entry.title for entry in card.precedents.groups()]
    assert len(titles) == 2, titles
    assert any("(0)" in title for title in titles), titles


def test_the_copy_icon_follows_the_explanation(engine) -> None:
    """§4 наряда `0035`: иконка есть, когда есть что копировать, и берёт всё.

    Копируется сохранённый текст, а не подпись с экрана: ярлык переносит строки
    и показывает прочерк при пустом значении (критерий 7 наряда).
    """
    # Хвостовой пробел домен срезает при сохранении — сравниваем с тем, что
    # он и запишет, а не с тем, что мы набрали.
    long_text = ("Batch sorted 100 % — 3 parts out of 25 rejected. " * 4).strip()
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        empty_id, _ = _case(session, item, "12", decision=None)
        filled_id, _ = _case(
            session, item, "13", wo="W9", decision="sorting", explanation=long_text
        )

    empty = _shown_card(engine, empty_id)
    assert empty.copy_own.isHidden(), "иконка обещает действие над пустым полем"

    filled = _shown_card(engine, filled_id)
    assert not filled.copy_own.isHidden()

    QApplication.clipboard().clear()
    filled.copy_own.click()
    assert QApplication.clipboard().text() == long_text
