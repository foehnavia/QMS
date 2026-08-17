"""Находка: гард «находка ∈ деталь отклонения» (0002 п. 7) + правка/удаление (0004)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import Deviation, Direction, Finding, Item
from domain.characteristics import get_or_create_characteristic
from domain.errors import InvariantViolation, ValidationError, ValueInUse
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


# --- Правка и удаление (наряд 0004, критерии 2 и 8) -------------------------------


def test_finding_is_updated_wholesale(seeded_session: Session) -> None:
    from db.models import RefDeviationType, RefZone
    from domain.findings import update_finding
    from domain.reference import list_values

    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    dev = _deviation(seeded_session, item)
    finding = make_finding(seeded_session, dev, char, direction=Direction.PLUS, value=0.08)

    zone = list_values(seeded_session, RefZone)[0] if list_values(seeded_session, RefZone) else None
    kind = (
        list_values(seeded_session, RefDeviationType)[0]
        if list_values(seeded_session, RefDeviationType)
        else None
    )
    update_finding(
        seeded_session,
        finding,
        direction=Direction.MINUS,
        value=0.11,
        dimension_point=3,
        comment="GO не проходит",
        zone=zone,
        deviation_type=kind,
    )
    seeded_session.commit()

    assert (finding.direction, finding.value, finding.dimension_point) == ("-", 0.11, 3)
    assert finding.comment == "GO не проходит"
    assert finding.zone is zone and finding.deviation_type is kind


def test_update_finding_demands_every_field(seeded_session: Session) -> None:
    """Правило S3: пропущенный аргумент не должен выглядеть как «не трогаем»."""
    from domain.findings import update_finding

    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    finding = make_finding(
        seeded_session, _deviation(seeded_session, item), char, direction=Direction.PLUS
    )

    with pytest.raises(TypeError):
        update_finding(seeded_session, finding, direction=Direction.MINUS)


def test_update_finding_rejects_an_unknown_direction(seeded_session: Session) -> None:
    from domain.findings import update_finding

    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    finding = make_finding(
        seeded_session, _deviation(seeded_session, item), char, direction=Direction.PLUS
    )

    with pytest.raises(ValidationError):
        update_finding(
            seeded_session,
            finding,
            direction="~",
            value=None,
            dimension_point=None,
            comment=None,
            zone=None,
            deviation_type=None,
        )


def test_the_last_finding_of_a_deviation_is_not_removable(seeded_session: Session) -> None:
    """Инвариант `1..N`: отклонение без размера невидимо для поиска прецедентов."""
    from domain.findings import remove_finding

    item = make_item(seeded_session, "IT-001")
    char, _ = get_or_create_characteristic(seeded_session, item, "12")
    dev = _deviation(seeded_session, item)
    finding = make_finding(seeded_session, dev, char, direction=Direction.PLUS)

    with pytest.raises(InvariantViolation) as excinfo:
        remove_finding(seeded_session, finding)

    assert dev.dev_number in str(excinfo.value)
    assert seeded_session.query(Finding).count() == 1


def test_a_finding_is_removable_while_another_one_remains(seeded_session: Session) -> None:
    from domain.findings import remove_finding

    item = make_item(seeded_session, "IT-001")
    first, _ = get_or_create_characteristic(seeded_session, item, "12")
    second, _ = get_or_create_characteristic(seeded_session, item, "19")
    dev = _deviation(seeded_session, item)
    doomed = make_finding(seeded_session, dev, first, direction=Direction.PLUS)
    kept = make_finding(seeded_session, dev, second, direction=Direction.MINUS)

    remove_finding(seeded_session, doomed)
    seeded_session.commit()

    assert seeded_session.query(Finding).count() == 1
    # Граф в памяти согласован с базой — коллекция владельца, не session.delete.
    assert dev.findings == [kept]
    # Размер детали переживает удаление находки: он существует сам по себе.
    assert {c.local_number for c in item.characteristics} == {"12", "19"}


def test_a_finding_with_an_inspection_is_not_removable(seeded_session: Session) -> None:
    """Критерий 8: исследование адресовано находке — без неё оно теряет адрес."""
    from db.models import RefInspectionType
    from domain.findings import remove_finding
    from domain.inspections import create_inspection
    from domain.reference import list_values

    item = make_item(seeded_session, "IT-001")
    first, _ = get_or_create_characteristic(seeded_session, item, "12")
    second, _ = get_or_create_characteristic(seeded_session, item, "19")
    dev = _deviation(seeded_session, item)
    studied = make_finding(seeded_session, dev, first, direction=Direction.PLUS)
    make_finding(seeded_session, dev, second, direction=Direction.MINUS)
    create_inspection(
        seeded_session,
        studied,
        inspection_type=list_values(seeded_session, RefInspectionType)[0],
        decision_insp="approved",
        protocol="p.docx",
    )

    with pytest.raises(ValueInUse) as excinfo:
        remove_finding(seeded_session, studied)

    assert "1" in str(excinfo.value)
    assert seeded_session.query(Finding).count() == 2
