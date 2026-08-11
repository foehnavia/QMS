"""Критерий приёмки 6 — правка справочников и обе защиты (заметка В)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import make_item
from db.models import (
    GENERAL,
    REFERENCE_MODELS,
    Characteristic,
    Deviation,
    Direction,
    Finding,
    RefConnectionType,
    RefDeviationType,
    RefItemType,
    RefSize,
    RefZone,
)
from domain.errors import DuplicateValue, ProtectedValue, ValidationError, ValueInUse
from domain.reference import (
    REFERENCE_DEPENDENTS,
    add_value,
    delete_value,
    list_values,
    rename_value,
    usage_count,
)
from seed.reference import ref


def test_every_reference_model_declares_its_dependents() -> None:
    """Иначе защита удаления молча пропустит занятое значение."""
    assert set(REFERENCE_DEPENDENTS) == set(REFERENCE_MODELS)


def test_add_rename_delete(seeded_session: Session) -> None:
    value = add_value(seeded_session, RefZone, "  neck  ")
    assert value.name == "neck"  # пробелы обрезаются

    rename_value(seeded_session, RefZone, value, "neck area")
    assert ref(seeded_session, RefZone, "neck area") is value

    delete_value(seeded_session, RefZone, value)
    assert "neck area" not in {row.name for row in list_values(seeded_session, RefZone)}


def test_add_duplicate_is_reported_not_raised_as_integrity_error(seeded_session: Session) -> None:
    with pytest.raises(DuplicateValue):
        add_value(seeded_session, RefZone, "thread")


def test_add_empty_name_is_rejected(seeded_session: Session) -> None:
    with pytest.raises(ValidationError):
        add_value(seeded_session, RefZone, "   ")


def test_rename_onto_existing_name_is_rejected(seeded_session: Session) -> None:
    zone = ref(seeded_session, RefZone, "thread")
    with pytest.raises(DuplicateValue):
        rename_value(seeded_session, RefZone, zone, "cutting edge")


@pytest.mark.parametrize("model", [RefConnectionType, RefSize])
def test_general_default_is_protected(seeded_session: Session, model: type) -> None:
    general = ref(seeded_session, model, GENERAL)
    with pytest.raises(ProtectedValue):
        delete_value(seeded_session, model, general)
    with pytest.raises(ProtectedValue):
        rename_value(seeded_session, model, general, "Обычный")


def test_value_used_by_an_item_cannot_be_deleted(seeded_session: Session) -> None:
    implant = ref(seeded_session, RefItemType, "implant")
    item = make_item(seeded_session, "IT-001")
    item.item_type = implant
    seeded_session.flush()

    assert usage_count(seeded_session, RefItemType, implant) == 1
    with pytest.raises(ValueInUse) as excinfo:
        delete_value(seeded_session, RefItemType, implant)
    assert "implant" in str(excinfo.value)


def test_value_used_by_a_finding_cannot_be_deleted(seeded_session: Session) -> None:
    from datetime import date

    item = make_item(seeded_session, "IT-001")
    char = Characteristic(item=item, local_number="12")
    seeded_session.add(char)
    dev = Deviation(
        dev_number="DEV-260811-0001",
        item=item,
        wo="W1",
        quantity=1,
        date=date(2026, 8, 11),
        explanation="",
    )
    seeded_session.add(dev)
    zone = ref(seeded_session, RefZone, "thread")
    dev_type = ref(seeded_session, RefDeviationType, "angle")
    seeded_session.add(
        Finding(
            deviation=dev,
            characteristic=char,
            direction=Direction.PLUS,
            zone=zone,
            deviation_type=dev_type,
        )
    )
    seeded_session.flush()

    for model, value in ((RefZone, zone), (RefDeviationType, dev_type)):
        with pytest.raises(ValueInUse):
            delete_value(seeded_session, model, value)


def test_free_value_is_deletable(seeded_session: Session) -> None:
    """Незанятое значение удаляется — иначе справочник не почистить."""
    angle = ref(seeded_session, RefDeviationType, "angle")
    assert usage_count(seeded_session, RefDeviationType, angle) == 0

    delete_value(seeded_session, RefDeviationType, angle)
    seeded_session.commit()

    assert "angle" not in {row.name for row in list_values(seeded_session, RefDeviationType)}
