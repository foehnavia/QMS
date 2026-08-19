"""UI карточки отклонения: прецеденты, вкладки, действия (критерии 1-2, 7-10 наряда 0005)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from conftest import count_queries, make_item
from db.models import (
    CharacteristicGroup,
    Deviation,
    Direction,
    Finding,
    Item,
    RefDeviationType,
    RefZone,
)
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.findings import make_finding
from domain.groups import GPositionSpec, create_group
from domain.mappings import bind
from domain.precedents import CANON_UNBOUND
from domain.reference import add_value, list_values
from ui.card_dialog import NO_LABELS_HINT, NO_SELECTION_HINT, CardDialog
from ui.deviation_view import DeviationView

pytestmark = pytest.mark.usefixtures("qt_app")

TODAY = date.today()
POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0))

L1_TAB, L2_TAB = 0, 1


@pytest.fixture
def engine(seeded_session):
    seeded_session.commit()
    return seeded_session.get_bind()


def _zone(session, name: str = "אזור הברגה") -> RefZone:
    existing = [v for v in list_values(session, RefZone) if v.name == name]
    return existing[0] if existing else add_value(session, RefZone, name)


def _kind(session, name: str = "thread burr") -> RefDeviationType:
    existing = [v for v in list_values(session, RefDeviationType) if v.name == name]
    return existing[0] if existing else add_value(session, RefDeviationType, name)


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
    characteristic, _ = get_or_create_characteristic(session, item, local_number)
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
        set_decision(session, deviation, decision=decision, explanation=explanation)
    return deviation.deviation_id, finding.finding_id


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
            characteristic, _ = get_or_create_characteristic(session, item, number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        deviation_id = deviation.deviation_id

    card = CardDialog(engine, deviation_id)

    card.findings.setCurrentCell(0, 0)  # размер 12
    assert card.same_dimension.rowCount() == 1
    assert _text(card.same_dimension.item(0, 3)) == "W-OLD-12"

    card.findings.setCurrentCell(1, 0)  # размер 19
    assert card.same_dimension.rowCount() == 2
    assert {_text(card.same_dimension.item(r, 3)) for r in range(2)} == {
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

    assert card.same_dimension.rowCount() == 0
    assert card.status.text() == NO_SELECTION_HINT
    assert card.inspect_button.isEnabled() is False


# --- Критерии 3-5 на уровне экрана -------------------------------------------------


def test_l1a_section_excludes_the_current_deviation(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST", on=TODAY - timedelta(days=10))
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.same_dimension.rowCount() == 1
    assert _text(card.same_dimension.item(0, 3)) == "W-PAST"
    assert "same characteristic no. 12 (1)" in _text(card.same_dimension_title)


def test_l1b_section_shows_another_item_on_the_same_position(engine) -> None:
    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        mine = make_item(session, "IT-001")
        other = make_item(session, "IT-002")
        bind(session, mine, group.positions[0], "12")
        bind(session, other, group.positions[0], "77")
        _case(session, other, "77", wo="W-OTHER")
        deviation_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.same_position.rowCount() == 1
    assert _text(card.same_position.item(0, 2)) == "IT-002"
    assert "same position g1 (1)" in _text(card.same_position_title)
    assert card.position_hint_box.isHidden() is True


def test_unbound_dimension_explains_instead_of_showing_an_empty_table(engine) -> None:
    """Критерий 10: вместо пустой таблицы — объяснение и кнопка привязки."""
    with session_scope(engine) as session:
        create_group(session, "CG-A", POSITIONS)
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.position_hint_box.isHidden() is False
    assert card.same_position.isHidden() is True
    assert "not bound to the canon" in card.position_hint.text()


def test_binding_from_the_card_revives_the_position_section(engine, monkeypatch) -> None:
    """Критерий 10: после привязки колонка «канон» и секция L1b обновляются на месте."""
    import ui.card_dialog as module

    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        other = make_item(session, "IT-002")
        bind(session, other, group.positions[0], "77")
        _case(session, other, "77", wo="W-OTHER")
        mine = make_item(session, "IT-001")
        deviation_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)
        cg_id = group.cg_id
        mine_id = mine.item_id

    card = CardDialog(engine, deviation_id)
    assert card.same_position.rowCount() == 0
    assert _text(card.findings.item(0, 1)) == CANON_UNBOUND

    def fake_run(engine_, item_id, cg_id_, parent=None):
        with session_scope(engine_) as session:
            item = session.get(Item, item_id)
            group = session.get(CharacteristicGroup, cg_id_)
            bind(session, item, group.positions[0], "12")
        return True

    monkeypatch.setattr(module.MappingDialog, "run", staticmethod(fake_run))
    monkeypatch.setattr(module, "choose_cg_for_item", lambda *args: cg_id)

    card.bind_canon()

    assert _text(card.findings.item(0, 1)) == "g1"
    assert card.same_position.rowCount() == 1
    assert _text(card.same_position.item(0, 2)) == "IT-002"


def test_undecided_precedents_are_not_shown(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-DECIDED", decision="rejected", explanation="брак")
        _case(session, item, "12", wo="W-OPEN", decision=None)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.same_dimension.rowCount() == 1
    assert _text(card.same_dimension.item(0, 3)) == "W-DECIDED"
    assert "already carry a decision" in card.status.text()


# --- Критерии 6-7: вкладка L2 и вкладка по умолчанию -------------------------------


def test_descriptive_tab_shows_the_match_column(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        zone, kind = _zone(session), _kind(session)
        _case(session, item, "10", wo="W-BOTH", zone=zone, deviation_type=kind)
        _case(session, item, "11", wo="W-ZONE", zone=zone)
        deviation_id, _ = _case(
            session, item, "12", wo="W-NOW", decision=None, zone=zone, deviation_type=kind
        )

    card = CardDialog(engine, deviation_id)

    assert card.descriptive.rowCount() == 2
    assert _text(card.descriptive.item(0, 3)) == "W-BOTH"
    assert card.descriptive.item(0, 9).text() == "zone and type"
    assert card.descriptive.item(1, 9).text() == "zone"


def test_card_opens_on_l2_when_l1_is_empty(engine) -> None:
    """Критерий 7 — проверяется состоянием экрана, а не на глаз."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        zone = _zone(session)
        _case(session, item, "10", wo="W-SIMILAR", zone=zone)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None, zone=zone)

    card = CardDialog(engine, deviation_id)

    assert card.same_dimension.rowCount() == 0
    assert card.descriptive.rowCount() == 1
    assert card.tabs.currentIndex() == L2_TAB


def test_card_stays_on_l1_when_exact_matches_exist(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        zone = _zone(session)
        _case(session, item, "12", wo="W-PAST", zone=zone)
        deviation_id, _ = _case(session, item, "12", wo="W-NOW", decision=None, zone=zone)

    card = CardDialog(engine, deviation_id)

    assert card.same_dimension.rowCount() == 1
    assert card.tabs.currentIndex() == L1_TAB


def test_descriptive_without_labels_explains_itself(engine) -> None:
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation_id, _ = _case(session, item, "12", decision=None)

    card = CardDialog(engine, deviation_id)

    assert card.descriptive.isHidden() is True
    assert card.descriptive_hint.text() == NO_LABELS_HINT


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

            domain_set_decision(
                session,
                session.get(Deviation, dev_id),
                decision="approved",
                explanation="обоснование",
            )
        return True

    monkeypatch.setattr(module.DecisionDialog, "run", staticmethod(decide))

    card = CardDialog(engine, deviation_id)
    assert card.decision.text() == "no decision yet"

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
                characteristic, _ = get_or_create_characteristic(
                    session, item, f"{index:03d}"
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
                characteristic, _ = get_or_create_characteristic(
                    session, item, f"{index:03d}"
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
    card.same_dimension.setCurrentCell(0, 0)

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

    assert _text(card.same_dimension.item(row, 0)) == past_number
    assert _text(card.same_dimension.item(row, 2)) == "C1-08375A"
    assert _text(card.same_dimension.item(row, 3)) == "W26007336"
    assert card.same_dimension.item(row, 6).text() == "Repair — legalised deviation"
    assert "доработка по месту" in card.same_dimension.item(row, 7).text()
    # Обоснование целиком — в подсказке, чтобы длинный текст не рвал вёрстку.
    assert card.same_dimension.item(row, 7).toolTip().startswith("доработка")


def test_navigation_has_no_card_section(engine) -> None:
    """Решение 7: карточка открывается от отклонения, разделом не заводится.

    А «Поиск» остаётся выключенным — это конструктор запросов Этапа 1.5, не S5.
    """
    from ui.main_window import PLANNED_SECTIONS, MainWindow

    window = MainWindow(engine)
    titles = [window.sections.item(i).text() for i in range(window.sections.count())]

    assert not any("Card" in title for title in titles)
    assert PLANNED_SECTIONS == (("Search", "S8"),)
    assert any("Search" in title and "S8" in title for title in titles)
    # Выключенный пункт — без флагов, кликнуть нельзя.
    search = next(
        window.sections.item(i)
        for i in range(window.sections.count())
        if "Search" in window.sections.item(i).text()
    )
    assert search.flags() == Qt.ItemFlag.NoItemFlags
    window.close()


# --- Ревью S5, дефект 1: прецедент открывается из той таблицы, где кликнули --------


def _two_sections(engine) -> tuple[int, int, int]:
    """Карточка, у которой непусты **обе** секции L1. Возвращает id: текущее, L1a, L1b."""
    with session_scope(engine) as session:
        group = create_group(session, "CG-A", POSITIONS)
        mine = make_item(session, "IT-001")
        other = make_item(session, "IT-002")
        bind(session, mine, group.positions[0], "12")
        bind(session, other, group.positions[0], "77")
        past_id, _ = _case(session, mine, "12", wo="W-SAME-DIM")
        position_id, _ = _case(session, other, "77", wo="W-SAME-POS")
        current_id, _ = _case(session, mine, "12", wo="W-NOW", decision=None)
    return current_id, past_id, position_id


def test_double_click_in_the_second_section_opens_its_own_row(engine, monkeypatch) -> None:
    """Секции — независимые таблицы: выбор в первой не должен перебивать вторую.

    Раньше `_current_table` перебирал их в порядке «эта деталь» → «другие детали»
    и всегда предпочитал первую, поэтому двойной клик во второй секции молча
    открывал отклонение из первой.
    """
    import ui.card_dialog as module

    current_id, past_id, position_id = _two_sections(engine)
    card = CardDialog(engine, current_id)
    assert (card.same_dimension.rowCount(), card.same_position.rowCount()) == (1, 1)

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    card.same_dimension.setCurrentCell(0, 0)  # оператор посмотрел первую секцию
    card.same_position.setCurrentCell(0, 0)
    card.open_precedent(card.same_position)   # и кликнул по второй

    assert opened == [position_id], "открылась строка не той секции"


def test_the_button_follows_the_last_touched_table(engine, monkeypatch) -> None:
    """Кнопка источника не имеет — берёт таблицу, в которой выбор меняли последней."""
    import ui.card_dialog as module

    current_id, past_id, position_id = _two_sections(engine)
    card = CardDialog(engine, current_id)

    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )

    card.same_position.setCurrentCell(0, 0)
    card.same_dimension.setCurrentCell(0, 0)
    card.open_precedent()
    assert opened == [past_id]

    card.same_position.setCurrentCell(0, 0)
    card.open_precedent()
    assert opened == [past_id, position_id]


def test_switching_the_finding_drops_a_stale_selection(engine, monkeypatch) -> None:
    """Перерисовка сбрасывает выбор: иначе перекос переживал бы смену находки."""
    import ui.card_dialog as module

    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-OLD-12")
        deviation = register(session, item=item, wo="W-NOW", quantity=1, date=TODAY)
        for number in ("12", "19"):
            characteristic, _ = get_or_create_characteristic(session, item, number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        current_id = deviation.deviation_id

    card = CardDialog(engine, current_id)
    card.findings.setCurrentCell(0, 0)
    card.same_dimension.setCurrentCell(0, 0)

    card.findings.setCurrentCell(1, 0)  # у размера 19 прецедентов нет

    assert card.same_dimension.currentRow() == -1
    opened: list[int] = []
    monkeypatch.setattr(
        module.CardDialog, "run", staticmethod(lambda e, dev_id, parent=None: opened.append(dev_id))
    )
    card.open_precedent()
    assert opened == [] and "Select a precedent" in card.status.text()


def test_status_counts_deviations_not_findings(engine) -> None:
    """Счётчик «похожих» считает случаи — после свёртки L2 по отклонению."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        zone = _zone(session)
        similar = register(session, item=item, wo="W-TWO-DIMS", quantity=1, date=TODAY)
        for number in ("30", "31"):
            characteristic, _ = get_or_create_characteristic(session, item, number)
            make_finding(session, similar, characteristic, direction=Direction.PLUS, zone=zone)
        set_decision(session, similar, decision="approved", explanation="ок")
        current_id, _ = _case(session, item, "12", wo="W-NOW", decision=None, zone=zone)

    card = CardDialog(engine, current_id)

    assert card.descriptive.rowCount() == 1
    assert "descriptive: 1" in card.status.text()


def test_tab_stays_where_the_operator_put_it(engine) -> None:
    """Автопереход на L2 — только при открытии, дальше вкладку выбирает оператор."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        _case(session, item, "12", wo="W-PAST")
        deviation = register(session, item=item, wo="W-NOW", quantity=1, date=TODAY)
        for number in ("12", "19"):
            characteristic, _ = get_or_create_characteristic(session, item, number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        current_id = deviation.deviation_id

    card = CardDialog(engine, current_id)
    card.findings.setCurrentCell(0, 0)
    assert card.tabs.currentIndex() == L1_TAB

    card.tabs.setCurrentIndex(L2_TAB)      # оператор ушёл на «Похожие» руками
    card.findings.setCurrentCell(1, 0)     # у размера 19 точных совпадений нет

    assert card.tabs.currentIndex() == L2_TAB


def test_findings_are_ordered_numerically(engine) -> None:
    """«9» раньше «10»: номер размера — строка, но читается как число."""
    with session_scope(engine) as session:
        item = make_item(session, "C1-08375A")
        deviation = register(session, item=item, wo="W1", quantity=1, date=TODAY)
        for number in ("10", "9", "2"):
            characteristic, _ = get_or_create_characteristic(session, item, number)
            make_finding(session, deviation, characteristic, direction=Direction.PLUS)
        current_id = deviation.deviation_id

    card = CardDialog(engine, current_id)

    assert [_text(card.findings.item(r, 0)) for r in range(3)] == ["2", "9", "10"]
