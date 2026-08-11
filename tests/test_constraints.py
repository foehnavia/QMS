"""Критерий приёмки 2 — FK и UNIQUE держат; плюс словарные CHECK и спящий R1."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import (
    Characteristic,
    CharacteristicGroup,
    Deviation,
    Direction,
    Finding,
    GPosition,
    Inspection,
    Item,
    Mapping,
    RefInspectionType,
)
from seed.reference import ref


def _deviation(session: Session, item: Item, dev_number: str) -> Deviation:
    dev = Deviation(
        dev_number=dev_number,
        item=item,
        wo="W26007336",
        quantity=10,
        date=date(2026, 8, 1),
        decision_dev="approved",
        explanation="ok",
    )
    session.add(dev)
    session.flush()
    return dev


def test_foreign_keys_pragma_is_on(seeded_session: Session) -> None:
    assert seeded_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_finding_with_unknown_characteristic_fails(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    dev = _deviation(seeded_session, item, "DEV-260801-0001")

    seeded_session.add(
        Finding(deviation_id=dev.deviation_id, characteristic_id=424242, direction=Direction.PLUS)
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_duplicate_item_number_fails(seeded_session: Session) -> None:
    make_item(seeded_session, "IT-001")
    with pytest.raises(IntegrityError):
        make_item(seeded_session, "IT-001")


def test_duplicate_dev_number_fails(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    _deviation(seeded_session, item, "DEV-260801-0001")
    with pytest.raises(IntegrityError):
        _deviation(seeded_session, item, "DEV-260801-0001")


def test_duplicate_insp_number_fails(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    dev = _deviation(seeded_session, item, "DEV-260801-0001")
    finding = Finding(deviation=dev, characteristic=char, direction=Direction.MINUS)
    seeded_session.add(finding)
    seeded_session.flush()
    insp_type = ref(seeded_session, RefInspectionType, "Solidworks assembly")

    for _ in range(2):
        seeded_session.add(
            Inspection(
                insp_number="INSP-260801-001",
                deviation=dev,
                finding=finding,
                type=insp_type,
                decision_insp="approved",
                protocol="p.docx",
            )
        )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_second_mapping_on_same_characteristic_fails(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    cg = CharacteristicGroup(name="CG-A")
    cg.positions = [
        GPosition(g_index=1, nominal=1.0, tol_plus=0.1, tol_minus=-0.1),
        GPosition(g_index=2, nominal=2.0, tol_plus=0.1, tol_minus=-0.1),
    ]
    seeded_session.add_all([char, cg])
    seeded_session.flush()

    seeded_session.add(Mapping(characteristic=char, g_position=cg.positions[0]))
    seeded_session.flush()
    seeded_session.add(
        Mapping(characteristic_id=char.characteristic_id, g_position_id=cg.positions[1].g_position_id)
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_duplicate_local_number_within_item_fails(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    seeded_session.add_all(
        [Characteristic(item=item, local_number="12"), Characteristic(item=item, local_number="12")]
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_same_local_number_on_different_items_is_allowed(seeded_session: Session) -> None:
    """Номер размера уникален только внутри детали (`Characteristic.md`)."""
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    seeded_session.add_all(
        [
            Characteristic(item=first, local_number="12"),
            Characteristic(item=second, local_number="12"),
        ]
    )
    seeded_session.flush()


@pytest.mark.parametrize("value", ["accepted", "approve", ""])
def test_unknown_decision_dev_is_rejected(seeded_session: Session, value: str) -> None:
    item = make_item(seeded_session, "IT-001")
    seeded_session.add(
        Deviation(
            dev_number="DEV-260801-0001",
            item=item,
            wo="W1",
            quantity=1,
            date=date(2026, 8, 1),
            decision_dev=value,
            explanation="",
        )
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_unknown_direction_is_rejected(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    dev = _deviation(seeded_session, item, "DEV-260801-0001")
    seeded_session.add(Finding(deviation=dev, characteristic=char, direction="~"))
    with pytest.raises(IntegrityError):
        seeded_session.flush()


# --- Заметка А: три состояния маппинга ------------------------------------------


def test_code99_mapping_has_no_g_position(seeded_session: Session) -> None:
    """Код 99 = строка есть, канонической позиции нет — «рассмотрено, отсутствует»."""
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="32")
    seeded_session.add(char)
    seeded_session.flush()

    seeded_session.add(Mapping(characteristic=char, is_absent=True))
    seeded_session.flush()

    assert char.mapping.is_absent is True
    assert char.mapping.g_position is None


def test_mapping_cannot_be_both_bound_and_absent(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    cg = CharacteristicGroup(name="CG-A")
    cg.positions = [GPosition(g_index=1, nominal=1.0, tol_plus=0.1, tol_minus=-0.1)]
    seeded_session.add_all([char, cg])
    seeded_session.flush()

    seeded_session.add(Mapping(characteristic=char, g_position=cg.positions[0], is_absent=True))
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_empty_mapping_row_is_rejected(seeded_session: Session) -> None:
    """«Маппинга ещё нет» выражается отсутствием строки, а не пустой строкой."""
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    seeded_session.flush()

    seeded_session.add(Mapping(characteristic=char, is_absent=False))
    with pytest.raises(IntegrityError):
        seeded_session.flush()


# --- Заметка Г: спящее поле R1 ---------------------------------------------------


def test_state_depending_is_a_dormant_self_fk(seeded_session: Session, engine) -> None:
    """Поле в схеме есть (self-FK), по умолчанию NULL; в S1 не заполняется."""
    fks = inspect(engine).get_foreign_keys("characteristic")
    self_fk = [
        fk
        for fk in fks
        if fk["constrained_columns"] == ["state_depending_id"]
        and fk["referred_table"] == "characteristic"
    ]
    assert self_fk, "state_depending_id должен быть self-FK на characteristic"

    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    seeded_session.flush()
    assert char.state_depending_id is None
