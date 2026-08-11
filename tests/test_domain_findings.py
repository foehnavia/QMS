"""Критерий приёмки 7 — гард «находка ∈ деталь отклонения»."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Deviation, Direction, Finding, Item
from domain.characteristics import get_or_create_characteristic
from domain.errors import InvariantViolation, ValidationError
from domain.findings import ensure_finding_target, make_finding


def _deviation(session: Session, item: Item) -> Deviation:
    dev = Deviation(
        dev_number="DEV-260811-0001",
        item=item,
        wo="W26007336",
        quantity=5,
        date=date(2026, 8, 11),
        explanation="",
    )
    session.add(dev)
    session.flush()
    return dev


def test_finding_on_own_characteristic_is_created(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    dev = _deviation(seeded_session, item)

    finding = make_finding(seeded_session, dev, char, direction=Direction.PLUS, value=0.08)
    seeded_session.commit()

    assert finding.deviation is dev
    assert finding.characteristic is char
    assert seeded_session.query(Finding).count() == 1


def test_finding_on_a_foreign_item_characteristic_is_blocked(seeded_session: Session) -> None:
    own = make_item(seeded_session, "IT-001")
    foreign = make_item(seeded_session, "IT-002")
    foreign_char, _ = get_or_create_characteristic(seeded_session, foreign, "12")
    dev = _deviation(seeded_session, own)

    with pytest.raises(InvariantViolation) as excinfo:
        make_finding(seeded_session, dev, foreign_char, direction=Direction.MINUS)

    message = str(excinfo.value)
    assert "12" in message and dev.dev_number in message
    assert seeded_session.query(Finding).count() == 0


def test_guard_is_callable_on_its_own(seeded_session: Session) -> None:
    """Гард нужен и вне создания — напр. при переносе находки в S4."""
    own = make_item(seeded_session, "IT-001")
    foreign = make_item(seeded_session, "IT-002")
    dev = _deviation(seeded_session, own)
    own_char, _ = get_or_create_characteristic(seeded_session, own, "12")
    foreign_char, _ = get_or_create_characteristic(seeded_session, foreign, "12")

    ensure_finding_target(dev, own_char)  # не бросает
    with pytest.raises(InvariantViolation):
        ensure_finding_target(dev, foreign_char)


def test_unknown_direction_is_rejected_before_the_database(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    dev = _deviation(seeded_session, item)

    with pytest.raises(ValidationError):
        make_finding(seeded_session, dev, char, direction="~")
