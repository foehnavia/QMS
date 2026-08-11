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
    ItemPositionAbsent,
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


# --- Код 99 отдельной таблицей (rev 0.2) ----------------------------------------


def _group(session: Session, name: str = "CG-A", indexes=(1, 2)) -> CharacteristicGroup:
    cg = CharacteristicGroup(name=name)
    cg.positions = [GPosition(g_index=i, nominal=1.0) for i in indexes]
    session.add(cg)
    session.flush()
    return cg


def test_absent_row_records_which_position_is_missing(seeded_session: Session) -> None:
    """Ради этого код 99 и переехал из флага в таблицу: позиция теперь известна."""
    item = make_item(seeded_session, "IT-001")
    cg = _group(seeded_session)

    seeded_session.add(ItemPositionAbsent(item=item, g_position=cg.positions[1]))
    seeded_session.flush()

    assert item.absent_positions[0].g_position.g_index == 2


def test_absent_pair_is_unique(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    cg = _group(seeded_session)

    seeded_session.add_all(
        [
            ItemPositionAbsent(item=item, g_position=cg.positions[0]),
            ItemPositionAbsent(item=item, g_position=cg.positions[0]),
        ]
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_absent_row_needs_an_existing_position(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001")
    seeded_session.add(ItemPositionAbsent(item_id=item.item_id, g_position_id=424242))
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_mapping_requires_a_position(seeded_session: Session) -> None:
    """Строка `mapping` теперь означает ровно одно — «размер привязан»."""
    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    seeded_session.flush()

    seeded_session.add(Mapping(characteristic=char, g_position=None))
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_balloon_coordinates_must_be_normalized(seeded_session: Session) -> None:
    cg = CharacteristicGroup(name="CG-A")
    seeded_session.add(cg)
    seeded_session.flush()

    seeded_session.add(GPosition(cg=cg, g_index=1, x=1.5, y=0.5))
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
