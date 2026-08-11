"""Критерий приёмки 3 — бизнес-номера: формат, уникальность, пакет за сутки."""

from __future__ import annotations

import re
from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, reopen
from db.ids import next_dev_number, next_insp_number
from db.models import Characteristic, Deviation, Direction, Finding, Inspection, RefInspectionType
from seed.reference import ref

DEV_RE = re.compile(r"^DEV-\d{6}-\d{4}$")
INSP_RE = re.compile(r"^INSP-\d{6}-\d{3}$")

BATCH = 25


def _deviation(session: Session, item, number: str, day: date) -> Deviation:
    dev = Deviation(
        dev_number=number,
        item=item,
        wo="W26007336",
        quantity=1,
        date=day,
        explanation="",
    )
    session.add(dev)
    return dev


def test_formats(seeded_session: Session) -> None:
    assert DEV_RE.match(next_dev_number(seeded_session))
    assert INSP_RE.match(next_insp_number(seeded_session))


def test_number_encodes_the_given_day(seeded_session: Session) -> None:
    assert next_dev_number(seeded_session, date(2026, 8, 3)) == "DEV-260803-0001"
    assert next_insp_number(seeded_session, date(2026, 12, 31)) == "INSP-261231-001"


def test_batch_within_one_day_is_sequential_and_unique(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    day = date(2026, 8, 11)

    numbers = []
    for _ in range(BATCH):
        number = next_dev_number(seeded_session, day)
        _deviation(seeded_session, item, number, day)
        numbers.append(number)
    seeded_session.commit()

    assert len(set(numbers)) == BATCH
    assert numbers == [f"DEV-260811-{i:04d}" for i in range(1, BATCH + 1)]
    assert all(DEV_RE.match(number) for number in numbers)


def test_counter_continues_in_a_new_session(migrated_url: str, seeded_session: Session) -> None:
    """Счётчик выводится из БД, поэтому переживает перезапуск приложения."""
    item = make_item(seeded_session, "IT-001")
    day = date(2026, 8, 11)
    for _ in range(3):
        _deviation(seeded_session, item, next_dev_number(seeded_session, day), day)
    seeded_session.commit()

    with reopen(migrated_url) as fresh:
        assert next_dev_number(fresh, day) == "DEV-260811-0004"


def test_counters_are_per_day(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    first_day, second_day = date(2026, 8, 11), date(2026, 8, 12)
    _deviation(seeded_session, item, next_dev_number(seeded_session, first_day), first_day)
    seeded_session.flush()

    assert next_dev_number(seeded_session, second_day) == "DEV-260812-0001"


def test_inspection_numbers_are_sequential(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    seeded_session.flush()
    day = date(2026, 8, 11)
    dev = _deviation(seeded_session, item, next_dev_number(seeded_session, day), day)
    finding = Finding(deviation=dev, characteristic=char, direction=Direction.PLUS)
    seeded_session.add(finding)
    seeded_session.flush()
    insp_type = ref(seeded_session, RefInspectionType, "Solidworks assembly")

    numbers = []
    for _ in range(3):
        number = next_insp_number(seeded_session, day)
        seeded_session.add(
            Inspection(
                insp_number=number,
                deviation=dev,
                finding=finding,
                type=insp_type,
                decision_insp="approved",
                protocol="p.docx",
            )
        )
        numbers.append(number)
    seeded_session.commit()

    assert numbers == ["INSP-260811-001", "INSP-260811-002", "INSP-260811-003"]
    assert seeded_session.query(Inspection).count() == 3


@pytest.mark.parametrize(
    "next_number, expected",
    [(next_dev_number, "DEV-260811-0001"), (next_insp_number, "INSP-260811-001")],
)
def test_leading_zeros(seeded_session: Session, next_number, expected: str) -> None:
    assert next_number(seeded_session, date(2026, 8, 11)) == expected
