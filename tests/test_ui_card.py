"""UI карточки отклонения: прецеденты, вкладки, действия (критерии 1-2, 7-10 наряда 0005)."""

from __future__ import annotations

import pathlib
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QStyle

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
from domain.deviations import register, set_decision
from domain.findings import make_finding, update_finding
from domain.inspections import create_inspection
from domain.groups import GPositionSpec, create_group
from domain.mappings import bind
from domain.precedents import CANON_UNBOUND
from domain.reference import ensure_value, list_values
import ui.kit
from ui import card_dialog
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
    assert card.same_dimension.rowCount() == 1
    assert _text(card.same_dimension.item(0, 4)) == "W-OLD-12"

    card.findings.setCurrentCell(1, 0)  # размер 19
    assert card.same_dimension.rowCount() == 2
    assert {_text(card.same_dimension.item(r, 4)) for r in range(2)} == {
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
    assert _text(card.same_dimension.item(0, 4)) == "W-PAST"
    # Заголовок называет **как совпало**, а не чья деталь (`Search.md` v1.04).
    assert "By number: no. 12" in _text(card.same_dimension_title)


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

    assert card.same_position.rowCount() == 1
    assert _text(card.same_position.item(0, 2)) == "IT-002"
    assert "By canon: position g1" in _text(card.same_position_title)
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
    assert card.same_position.rowCount() == 0
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
    assert _text(card.same_dimension.item(0, 4)) == "W-DECIDED"
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
    assert card.same_dimension.rowCount() == 0
    assert card.same_position.rowCount() == 0
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

    assert card.same_dimension.rowCount() == 0
    assert card.same_position.isHidden() is True
    # Точный уровень объясняет обе свои пустоты: «нет прецедентов» и «размер не
    # привязан к канону — привязка это и есть то, что находит то же место».
    assert card.dimension_empty.isHidden() is False
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
    assert _text(card.same_dimension.item(row, 4)) == "W26007336"
    # Колонка списка несёт **короткую** метку; полная формулировка живёт в
    # диалоге решения и в шапке карточки (дизайн-система, макет S13).
    assert card.same_dimension.item(row, 7).text() == "Repair"
    assert "доработка по месту" in card.same_dimension.item(row, 8).text()
    # Обоснование целиком — в подсказке, чтобы длинный текст не рвал вёрстку.
    assert card.same_dimension.item(row, 8).toolTip().startswith("доработка")


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
            characteristic, _ = get_or_create_characteristic(session, rev(item), number)
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
