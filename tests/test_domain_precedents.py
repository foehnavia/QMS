"""Прецеденты L1/L2 и пакетное состояние канона (критерии 3-6, 8 наряда 0005)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Direction, Item, RefDeviationType, RefZone
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, set_decision
from domain.findings import make_finding
from domain.groups import GPositionSpec, create_group
from domain.mappings import bind, mark_absent
from domain.precedents import (
    CANON_NEW,
    CANON_UNBOUND,
    canon_labels,
    canon_labels_for_item,
    precedents_descriptive,
    precedents_same_dimension,
    precedents_same_position,
)
from domain.reference import add_value, list_values

TODAY = date(2026, 8, 11)
POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0))


def _zone(session: Session, name: str = "אזור הברגה") -> RefZone:
    existing = [v for v in list_values(session, RefZone) if v.name == name]
    return existing[0] if existing else add_value(session, RefZone, name)


def _kind(session: Session, name: str = "thread burr") -> RefDeviationType:
    existing = [v for v in list_values(session, RefDeviationType) if v.name == name]
    return existing[0] if existing else add_value(session, RefDeviationType, name)


def _case(
    session: Session,
    item: Item,
    local_number: str,
    *,
    wo: str = "W1",
    on: date = TODAY,
    decision: str | None = "approved",
    explanation: str = "влияния нет",
    direction: str = Direction.PLUS,
    value: float | None = 0.08,
    zone=None,
    deviation_type=None,
):
    """Отклонение с одной находкой; по умолчанию — уже решённое."""
    deviation = register(session, item=item, wo=wo, quantity=5, date=on)
    characteristic, _ = get_or_create_characteristic(session, item, local_number)
    finding = make_finding(
        session,
        deviation,
        characteristic,
        direction=direction,
        value=value,
        zone=zone,
        deviation_type=deviation_type,
    )
    if decision is not None:
        set_decision(session, deviation, decision=decision, explanation=explanation)
    return deviation, finding, characteristic


# --- Критерий 3: L1a — та же деталь, тот же размер --------------------------------


def test_same_dimension_finds_the_past_case(seeded_session: Session) -> None:
    item = make_item(seeded_session, "C1-08375A")
    _case(seeded_session, item, "12", wo="W1", on=TODAY - timedelta(days=30))
    current, _finding, characteristic = _case(seeded_session, item, "12", wo="W2")
    seeded_session.commit()

    rows = precedents_same_dimension(
        seeded_session, characteristic, exclude_deviation=current
    )

    assert [row.wo for row in rows] == ["W1"]
    assert rows[0].decision == "approved"
    assert rows[0].explanation == "влияния нет"
    assert rows[0].match == "dimension"


def test_same_dimension_excludes_the_current_deviation(seeded_session: Session) -> None:
    item = make_item(seeded_session, "C1-08375A")
    current, _f, characteristic = _case(seeded_session, item, "12")
    seeded_session.commit()

    assert precedents_same_dimension(seeded_session, characteristic, exclude_deviation=current) == []
    # Без исключения та же находка видна — значит фильтр, а не пустая выборка.
    assert len(precedents_same_dimension(seeded_session, characteristic)) == 1


def test_same_dimension_is_fresh_first(seeded_session: Session) -> None:
    item = make_item(seeded_session, "C1-08375A")
    _case(seeded_session, item, "12", wo="OLD", on=TODAY - timedelta(days=100))
    _case(seeded_session, item, "12", wo="NEW", on=TODAY - timedelta(days=1))
    seeded_session.commit()

    rows = precedents_same_dimension(
        seeded_session, seeded_session.query(Item).one().characteristics[0]
    )

    assert [row.wo for row in rows] == ["NEW", "OLD"]


def test_same_dimension_does_not_cross_items(seeded_session: Session) -> None:
    """Номер размера уникален только внутри детали — «12» у двух деталей разные."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    _case(seeded_session, first, "12", wo="W-FIRST")
    _dev, _f, characteristic = _case(seeded_session, second, "12", wo="W-SECOND")
    seeded_session.commit()

    rows = precedents_same_dimension(seeded_session, characteristic)

    assert [row.wo for row in rows] == ["W-SECOND"]


# --- Критерий 4: L1b — другие детали на той же g-позиции ---------------------------


def _bound_pair(session: Session):
    """Две детали, привязанные к одной g-позиции (g1) под разными номерами."""
    group = create_group(session, "CG-A", POSITIONS)
    first = make_item(session, "IT-001")
    second = make_item(session, "IT-002")
    bind(session, first, group.positions[0], "12")
    bind(session, second, group.positions[0], "77")
    return group, first, second


def test_same_position_finds_another_item(seeded_session: Session) -> None:
    group, first, second = _bound_pair(seeded_session)
    _case(seeded_session, second, "77", wo="W-OTHER")
    current, _f, characteristic = _case(seeded_session, first, "12", wo="W-MINE")
    seeded_session.commit()

    rows = precedents_same_position(
        seeded_session, characteristic, exclude_deviation=current
    )

    assert [row.item_number for row in rows] == ["IT-002"]
    assert rows[0].local_number == "77"  # у другой детали свой номер размера
    assert rows[0].g_label == "CG-A · g1"
    assert rows[0].match == "position"


def test_same_position_does_not_repeat_own_item(seeded_session: Session) -> None:
    """Своя деталь — это L1a; в секции по позиции она дублировала бы прецедент."""
    group, first, _second = _bound_pair(seeded_session)
    _case(seeded_session, first, "12", wo="W-OWN-OLD")
    current, _f, characteristic = _case(seeded_session, first, "12", wo="W-OWN-NEW")
    seeded_session.commit()

    assert precedents_same_position(seeded_session, characteristic, exclude_deviation=current) == []


def test_same_position_skips_items_marked_absent(seeded_session: Session) -> None:
    """Код 99 — не поисковый ключ: такая деталь в выдачу по позиции не входит."""
    group, first, second = _bound_pair(seeded_session)
    # У второй детали позицию рассмотрели и пометили «нет у детали».
    mark_absent(seeded_session, second, group.positions[0])
    _case(seeded_session, second, "77", wo="W-ABSENT")
    _dev, _f, characteristic = _case(seeded_session, first, "12")
    seeded_session.commit()

    assert precedents_same_position(seeded_session, characteristic) == []


def test_same_position_is_empty_without_a_mapping(seeded_session: Session) -> None:
    """Непривязанный размер — штатное состояние, а не сбой: пусто без ошибки."""
    item = make_item(seeded_session, "IT-001")
    _dev, _f, characteristic = _case(seeded_session, item, "12")
    seeded_session.commit()

    assert characteristic.mapping is None
    assert precedents_same_position(seeded_session, characteristic) == []


# --- Критерий 5: только решённые ---------------------------------------------------


def test_undecided_deviations_never_appear(seeded_session: Session) -> None:
    """Прецедент существует ради решения; нерешённое подсказать нечего."""
    item = make_item(seeded_session, "C1-08375A")
    _case(seeded_session, item, "12", wo="W-DECIDED", decision="rejected", explanation="брак")
    _case(seeded_session, item, "12", wo="W-OPEN", decision=None)
    current, _f, characteristic = _case(seeded_session, item, "12", wo="W-NOW")
    seeded_session.commit()

    rows = precedents_same_dimension(
        seeded_session, characteristic, exclude_deviation=current
    )

    assert [row.wo for row in rows] == ["W-DECIDED"]


def test_undecided_is_hidden_in_descriptive_search_too(seeded_session: Session) -> None:
    item = make_item(seeded_session, "C1-08375A")
    zone = _zone(seeded_session)
    _case(seeded_session, item, "12", wo="W-OPEN", decision=None, zone=zone)
    seeded_session.commit()

    assert precedents_descriptive(seeded_session, zone=zone) == []


# --- Критерий 6: L2 — описательный -------------------------------------------------


def test_descriptive_matches_zone_and_type_separately_and_together(
    seeded_session: Session,
) -> None:
    item = make_item(seeded_session, "C1-08375A")
    zone, kind = _zone(seeded_session), _kind(seeded_session)
    _case(seeded_session, item, "10", wo="W-ZONE", zone=zone)
    _case(seeded_session, item, "11", wo="W-TYPE", deviation_type=kind)
    _case(seeded_session, item, "12", wo="W-BOTH", zone=zone, deviation_type=kind)
    seeded_session.commit()

    rows = precedents_descriptive(seeded_session, zone=zone, deviation_type=kind)

    # Совпавшие по обоим — выше: сила совпадения читается порядком.
    assert rows[0].wo == "W-BOTH" and rows[0].match == "zone+type"
    assert {row.wo: row.match for row in rows[1:]} == {"W-ZONE": "zone", "W-TYPE": "type"}


def test_descriptive_by_zone_alone(seeded_session: Session) -> None:
    item = make_item(seeded_session, "C1-08375A")
    zone, kind = _zone(seeded_session), _kind(seeded_session)
    _case(seeded_session, item, "10", wo="W-ZONE", zone=zone)
    _case(seeded_session, item, "11", wo="W-TYPE", deviation_type=kind)
    seeded_session.commit()

    rows = precedents_descriptive(seeded_session, zone=zone)

    assert [row.wo for row in rows] == ["W-ZONE"]
    assert rows[0].match == "zone"


def test_descriptive_without_labels_returns_nothing(seeded_session: Session) -> None:
    """Ни зоны, ни типа — искать не по чему; пусто, а не «всё подряд»."""
    item = make_item(seeded_session, "C1-08375A")
    _case(seeded_session, item, "12", zone=_zone(seeded_session))
    seeded_session.commit()

    assert precedents_descriptive(seeded_session) == []


def test_descriptive_excludes_rows_already_shown_in_l1(seeded_session: Session) -> None:
    """Вкладки не повторяют друг друга: тот же размер из L1 в L2 не приходит."""
    item = make_item(seeded_session, "C1-08375A")
    zone = _zone(seeded_session)
    _case(seeded_session, item, "12", wo="W-SAME-DIM", zone=zone)
    _case(seeded_session, item, "19", wo="W-OTHER-DIM", zone=zone)
    current, _f, characteristic = _case(seeded_session, item, "12", wo="W-NOW", zone=zone)
    seeded_session.commit()

    rows = precedents_descriptive(
        seeded_session,
        zone=zone,
        exclude_deviation=current,
        exclude_characteristic=characteristic,
    )

    assert [row.wo for row in rows] == ["W-OTHER-DIM"]


def test_descriptive_crosses_items(seeded_session: Session) -> None:
    """L2 работает и для непривязанных размеров разных деталей — в этом его смысл."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    kind = _kind(seeded_session)
    _case(seeded_session, second, "77", wo="W-OTHER-ITEM", deviation_type=kind)
    current, _f, _c = _case(seeded_session, first, "12", wo="W-NOW", deviation_type=kind)
    seeded_session.commit()

    rows = precedents_descriptive(
        seeded_session, deviation_type=kind, exclude_deviation=current
    )

    assert [row.item_number for row in rows] == ["IT-002"]


# --- Строка выдачи -----------------------------------------------------------------


def test_row_carries_the_whole_deviation_not_just_the_finding(
    seeded_session: Session,
) -> None:
    """Единица выдачи — отклонение целиком (`Search.md`), даже при совпадении размера."""
    from db.models import RefInspectionType
    from domain.inspections import create_inspection

    item = make_item(seeded_session, "C1-08375A")
    zone, kind = _zone(seeded_session), _kind(seeded_session)
    deviation, finding, characteristic = _case(
        seeded_session,
        item,
        "12",
        wo="W26007336",
        decision="sorting",
        explanation="100 % контроль",
        direction=Direction.MINUS,
        value=0.05,
        zone=zone,
        deviation_type=kind,
    )
    create_inspection(
        seeded_session,
        finding,
        inspection_type=list_values(seeded_session, RefInspectionType)[0],
        decision_insp="approved",
        protocol="p.docx",
    )
    seeded_session.commit()

    row = precedents_same_dimension(seeded_session, characteristic)[0]

    assert (row.dev_number, row.wo, row.quantity) == (deviation.dev_number, "W26007336", 5)
    assert (row.item_number, row.local_number) == ("C1-08375A", "12")
    assert (row.direction, row.value) == (Direction.MINUS, 0.05)
    assert (row.decision, row.explanation) == ("sorting", "100 % контроль")
    assert (row.zone, row.deviation_type) == (zone.name, kind.name)
    assert row.inspection_count == 1
    assert row.decision_date is not None
    assert row.g_label is None  # размер к канону не привязан


# --- Критерий 8: пакетное состояние канона -----------------------------------------


def test_canon_labels_batches_the_whole_set(seeded_session: Session) -> None:
    group, first, _second = _bound_pair(seeded_session)
    unbound, _ = get_or_create_characteristic(seeded_session, first, "19")
    bound = next(c for c in first.characteristics if c.local_number == "12")
    seeded_session.commit()

    labels = canon_labels(seeded_session, [bound, unbound])

    assert labels[bound.characteristic_id] == "g1"
    assert labels[unbound.characteristic_id] == CANON_UNBOUND


def test_canon_labels_is_empty_for_an_empty_set(seeded_session: Session) -> None:
    assert canon_labels(seeded_session, []) == {}


def test_canon_labels_for_item_covers_all_three_states(seeded_session: Session) -> None:
    group, first, _second = _bound_pair(seeded_session)
    get_or_create_characteristic(seeded_session, first, "19")
    seeded_session.commit()

    labels = canon_labels_for_item(seeded_session, first, ["12", "19", "999"])

    assert labels == {"12": "g1", "19": CANON_UNBOUND, "999": CANON_NEW}


def test_canon_labels_for_item_ignores_blank_numbers(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    seeded_session.commit()

    assert canon_labels_for_item(seeded_session, item, ["", "   "]) == {}


def test_precedent_list_does_not_grow_queries_with_rows(seeded_session: Session) -> None:
    """Критерий 8: выдача — один запрос, сколько бы прецедентов в ней ни было.

    Два набора на одной сессии: у размера №12 два прецедента, у №19 — двадцать.
    Объекты-аргументы прогреваем **до** счётчика: ленивая подгрузка самой
    характеристики после `commit` — работа ORM с аргументом, а не запрос выдачи,
    и в счёт идти не должна.
    """
    from conftest import count_queries

    item = make_item(seeded_session, "C1-08375A")
    for index in range(2):
        _case(seeded_session, item, "12", wo=f"S{index:03d}")
    for index in range(20):
        _case(seeded_session, item, "19", wo=f"L{index:03d}")
    seeded_session.commit()

    engine = seeded_session.get_bind()
    small = next(c for c in item.characteristics if c.local_number == "12")
    large = next(c for c in item.characteristics if c.local_number == "19")
    small.characteristic_id, large.characteristic_id  # прогрев, не проверка

    with count_queries(engine) as few:
        rows_few = precedents_same_dimension(seeded_session, small)
    with count_queries(engine) as many:
        rows_many = precedents_same_dimension(seeded_session, large)

    assert (len(rows_few), len(rows_many)) == (2, 20)
    assert len(few) == len(many) == 1, f"запросов: {len(few)} против {len(many)}"


def test_descriptive_list_does_not_grow_queries_with_rows(seeded_session: Session) -> None:
    """То же для L2 — вкладка «Похожие» строится одним запросом."""
    from conftest import count_queries

    item = make_item(seeded_session, "C1-08375A")
    zone = _zone(seeded_session)
    for index in range(20):
        _case(seeded_session, item, f"{index:03d}", wo=f"W{index:03d}", zone=zone)
    seeded_session.commit()
    zone.zone_id  # прогрев аргумента
    engine = seeded_session.get_bind()

    with count_queries(engine) as statements:
        rows = precedents_descriptive(seeded_session, zone=zone)

    assert len(rows) == 20
    assert len(statements) == 1, f"ожидался один запрос, ушло {len(statements)}"


def test_canon_labels_does_not_grow_queries_with_the_set(seeded_session: Session) -> None:
    """Пакетный запрос состояния канона — один на набор, а не на строку."""
    from conftest import count_queries

    group, first, _second = _bound_pair(seeded_session)
    for index in range(20):
        get_or_create_characteristic(seeded_session, first, f"{index:03d}")
    seeded_session.commit()

    characteristics = list(first.characteristics)
    [c.characteristic_id for c in characteristics]  # прогрев
    engine = seeded_session.get_bind()

    with count_queries(engine) as few:
        canon_labels(seeded_session, characteristics[:2])
    with count_queries(engine) as many:
        labels = canon_labels(seeded_session, characteristics)

    assert len(labels) == len(characteristics) >= 21
    assert len(few) == len(many) == 1, f"запросов: {len(few)} против {len(many)}"


def test_canon_labels_for_item_is_two_queries_regardless_of_size(
    seeded_session: Session,
) -> None:
    """Форма отклонения: два запроса — характеристики детали и их состояние."""
    from conftest import count_queries

    group, first, _second = _bound_pair(seeded_session)
    numbers = [f"{index:03d}" for index in range(20)]
    for number in numbers:
        get_or_create_characteristic(seeded_session, first, number)
    seeded_session.commit()
    first.item_id  # прогрев
    engine = seeded_session.get_bind()

    with count_queries(engine) as few:
        canon_labels_for_item(seeded_session, first, numbers[:2])
    with count_queries(engine) as many:
        labels = canon_labels_for_item(seeded_session, first, numbers)

    assert len(labels) == 20
    assert len(few) == len(many) == 2, f"запросов: {len(few)} против {len(many)}"
