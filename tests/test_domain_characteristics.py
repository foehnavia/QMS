"""Критерий приёмки 5 — автосоздание не-CG размера (заметка Г)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Characteristic
from domain.characteristics import get_or_create_characteristic
from domain.errors import ValidationError


def test_missing_characteristic_is_created_without_form_or_mapping(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")

    char, created = get_or_create_characteristic(seeded_session, item, "19")
    seeded_session.commit()

    assert created is True
    assert char.local_number == "19"
    assert char.item is item
    assert char.mapping is None  # не-CG размер живёт без канона
    assert char.state_depending_id is None  # спящее поле R1 не трогаем


def test_repeated_call_returns_the_same_row(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")

    first, created_first = get_or_create_characteristic(seeded_session, item, "19")
    second, created_second = get_or_create_characteristic(seeded_session, item, "19")
    seeded_session.commit()

    assert (created_first, created_second) == (True, False)
    assert first is second
    assert seeded_session.query(Characteristic).count() == 1


def test_whitespace_is_trimmed_before_matching(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")

    first, _ = get_or_create_characteristic(seeded_session, item, "19")
    second, created = get_or_create_characteristic(seeded_session, item, "  19 ")

    assert created is False
    assert second is first


def test_same_number_on_another_item_is_a_separate_row(seeded_session: Session) -> None:
    """«Размер 12» вне детали не существует (`Characteristic.md`)."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")

    a, _ = get_or_create_characteristic(seeded_session, first, "12")
    b, created = get_or_create_characteristic(seeded_session, second, "12")
    seeded_session.commit()

    assert created is True
    assert a is not b
    assert seeded_session.query(Characteristic).count() == 2


def test_blank_local_number_is_rejected(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    with pytest.raises(ValidationError):
        get_or_create_characteristic(seeded_session, item, "  ")
