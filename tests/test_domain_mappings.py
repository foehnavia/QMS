"""Привязка размеров к g-позициям, код 99, полнота (критерии 4–6 наряда 0003)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, reopen
from db.models import Characteristic, CharacteristicGroup, ItemPositionAbsent, Mapping
from domain.characteristics import get_or_create_characteristic
from domain.errors import DuplicateValue, InvariantViolation
from domain.groups import GPositionSpec, create_group
from domain.mappings import (
    bind,
    binding_state,
    clear,
    is_complete,
    items_by_position,
    mark_absent,
)

POSITIONS = (
    GPositionSpec(g_index=1, nominal=3.75, tol_plus=0.05, tol_minus=-0.05),
    GPositionSpec(g_index=2, nominal=2.00),
    GPositionSpec(g_index=3, nominal=0.50),
)


def _group(session: Session, name: str = "CG-A") -> CharacteristicGroup:
    return create_group(session, name, POSITIONS)


def test_bind_creates_characteristic_and_mapping(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)

    mapping = bind(seeded_session, item, group.positions[0], "12")
    seeded_session.commit()

    assert mapping.characteristic.local_number == "12"
    assert mapping.g_position.g_index == 1
    assert seeded_session.query(Characteristic).count() == 1


def test_bind_reuses_an_existing_characteristic(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    existing, _ = get_or_create_characteristic(seeded_session, item, "12")

    mapping = bind(seeded_session, item, group.positions[0], "12")

    assert mapping.characteristic is existing
    assert seeded_session.query(Characteristic).count() == 1


def test_binding_the_same_pair_twice_is_idempotent(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)

    first = bind(seeded_session, item, group.positions[0], "12")
    second = bind(seeded_session, item, group.positions[0], "12")

    assert first is second
    assert seeded_session.query(Mapping).count() == 1


def test_rebinding_a_taken_dimension_is_refused(seeded_session: Session) -> None:
    """Перепривязка — только явная: сперва «Очистить» (решение Cowork 7)."""
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")

    with pytest.raises(InvariantViolation) as excinfo:
        bind(seeded_session, item, group.positions[1], "12")
    assert "g1" in str(excinfo.value)
    assert seeded_session.query(Mapping).count() == 1


def test_second_dimension_on_one_position_is_refused(seeded_session: Session) -> None:
    """«1 баллон = 1 локальный размер = 1 привязка» (Session-03 §4)."""
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")

    with pytest.raises(DuplicateValue) as excinfo:
        bind(seeded_session, item, group.positions[0], "19")
    assert "12" in str(excinfo.value)


def test_the_same_position_serves_different_items(seeded_session: Session) -> None:
    """Канон на то и канон: одна позиция у разных деталей — разные размеры."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    group = _group(seeded_session)

    bind(seeded_session, first, group.positions[0], "12")
    bind(seeded_session, second, group.positions[0], "7")
    seeded_session.commit()

    assert [item.item_number for item in items_by_position(seeded_session, group.positions[0])] == [
        "IT-001",
        "IT-002",
    ]


# --- Код 99 ----------------------------------------------------------------------


def test_mark_absent_records_the_pair(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)

    mark_absent(seeded_session, item, group.positions[2])
    seeded_session.commit()

    rows = seeded_session.query(ItemPositionAbsent).all()
    assert len(rows) == 1
    assert rows[0].g_position.g_index == 3
    assert rows[0].item is item


def test_mark_absent_is_idempotent(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)

    first = mark_absent(seeded_session, item, group.positions[0])
    second = mark_absent(seeded_session, item, group.positions[0])

    assert first is second
    assert seeded_session.query(ItemPositionAbsent).count() == 1


def test_absent_items_are_not_returned_by_position(seeded_session: Session) -> None:
    """Критерий 5: код 99 — не поисковый ключ, деталь в выдачу не входит."""
    linked = make_item(seeded_session, "IT-001")
    absent = make_item(seeded_session, "IT-002")
    group = _group(seeded_session)

    bind(seeded_session, linked, group.positions[0], "12")
    mark_absent(seeded_session, absent, group.positions[0])
    seeded_session.commit()

    found = items_by_position(seeded_session, group.positions[0])
    assert [item.item_number for item in found] == ["IT-001"]


def test_mark_absent_replaces_an_existing_binding(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")

    mark_absent(seeded_session, item, group.positions[0])
    seeded_session.commit()

    assert seeded_session.query(Mapping).count() == 0
    # сам размер у детали остаётся — он существует независимо от канона
    assert [c.local_number for c in item.characteristics] == ["12"]


def test_bind_clears_a_previous_absence(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    mark_absent(seeded_session, item, group.positions[0])

    bind(seeded_session, item, group.positions[0], "12")
    seeded_session.commit()

    assert seeded_session.query(ItemPositionAbsent).count() == 0
    assert seeded_session.query(Mapping).count() == 1


# --- Очистка и состояния ---------------------------------------------------------


def test_clear_returns_the_pair_to_unconsidered(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")

    clear(seeded_session, item, group.positions[0])
    seeded_session.commit()

    states = binding_state(seeded_session, item, group)
    assert states[0].state == "none"
    # характеристику не удаляем
    assert [c.local_number for c in item.characteristics] == ["12"]


def test_clear_after_bind_allows_rebinding(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")
    clear(seeded_session, item, group.positions[0])

    mapping = bind(seeded_session, item, group.positions[1], "12")

    assert mapping.g_position.g_index == 2


def test_binding_state_reports_all_three_states(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")
    mark_absent(seeded_session, item, group.positions[1])

    states = binding_state(seeded_session, item, group)

    assert [state.state for state in states] == ["linked", "absent", "none"]
    assert states[0].local_number == "12"
    assert [state.g_index for state in states] == [1, 2, 3]


def test_completeness_needs_every_balloon(seeded_session: Session) -> None:
    """Критерий 6: «Готово» активна, только когда все баллоны решены."""
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)

    assert is_complete(binding_state(seeded_session, item, group)) is False

    bind(seeded_session, item, group.positions[0], "12")
    bind(seeded_session, item, group.positions[1], "19")
    assert is_complete(binding_state(seeded_session, item, group)) is False

    mark_absent(seeded_session, item, group.positions[2])
    assert is_complete(binding_state(seeded_session, item, group)) is True


def test_binding_survives_a_reopen(migrated_url: str, seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    group = _group(seeded_session)
    bind(seeded_session, item, group.positions[0], "12")
    mark_absent(seeded_session, item, group.positions[1])
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        from db.models import Item

        stored = fresh.query(Item).filter_by(item_number="IT-001").one()
        stored_group = fresh.query(CharacteristicGroup).one()
        states = binding_state(fresh, stored, stored_group)
        assert [state.state for state in states] == ["linked", "absent", "none"]
        assert states[0].local_number == "12"
