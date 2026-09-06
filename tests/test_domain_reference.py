"""Критерий приёмки 6 — правка справочников и обе защиты (заметка В)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, rev
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
    find_value,
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
    # Пробелы обрезаются, первая буква — заглавная (находка №6).
    assert value.name == "Neck"

    rename_value(seeded_session, RefZone, value, "neck area")
    assert ref(seeded_session, RefZone, "neck area") is value

    delete_value(seeded_session, RefZone, value)
    assert "Neck area" not in {row.name for row in list_values(seeded_session, RefZone)}


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
    assert "Implant" in str(excinfo.value)


def test_value_used_by_a_finding_cannot_be_deleted(seeded_session: Session) -> None:
    from datetime import date

    item = make_item(seeded_session, "IT-001")
    char = Characteristic(revision=rev(item), local_number="12")
    seeded_session.add(char)
    dev = Deviation(
        dev_number="DEV-260811-0001",
        item=item,
        revision=rev(item),
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


# --- наряд 0021: близнецы по регистру ------------------------------------------------


def _twin(session, model, name):
    """Завести значение **мимо** нормализации — так они и появились в базе."""
    value = model(name=name)
    session.add(value)
    session.flush()
    return value


def test_merging_moves_every_reference_and_drops_the_twin(seeded_session: Session) -> None:
    """§4.1: ссылки перевешиваются, близнец уходит, ни одна запись не теряется."""
    from conftest import make_item
    from db.models import Item, RefItemType
    from domain.reference import merge_values

    # Сид уже кладёт `Drill`; близнеца заводим строчным — так он и появился.
    keep = find_value(seeded_session, RefItemType, "Drill")
    drop = _twin(seeded_session, RefItemType, "drill")
    item = make_item(seeded_session, "MT-SD1037A")
    item.item_type = drop
    seeded_session.flush()

    moved = merge_values(seeded_session, RefItemType, keep, drop)
    seeded_session.commit()

    assert moved == 1
    # Сверяем по имени: после `commit` объекты перечитаны, и тождество ссылок
    # ничего не значит — значение же то самое.
    assert seeded_session.get(Item, item.item_id).item_type.name == "Drill"
    assert {value.name for value in list_values(seeded_session, RefItemType)} >= {"Drill"}
    assert "drill" not in {v.name for v in list_values(seeded_session, RefItemType)}


def test_merging_a_value_into_itself_is_refused(seeded_session: Session) -> None:
    from db.models import RefItemType
    from domain.reference import merge_values

    value = find_value(seeded_session, RefItemType, "Implant")
    with pytest.raises(ValidationError):
        merge_values(seeded_session, RefItemType, value, value)


def test_normalising_merges_twins_and_renames_the_rest(seeded_session: Session) -> None:
    """§4.2: приведение регистра **переименовывает**, а где есть близнец — сводит.

    Добавление вместо переименования и породило бы ровно тех близнецов, ради
    которых наряд написан.
    """
    from db.models import RefDeviationType
    from domain.reference import normalise_case

    _twin(seeded_session, RefDeviationType, "thread burr")  # близнец к засеянному
    _twin(seeded_session, RefDeviationType, "lonely lowercase")  # без близнеца

    report = normalise_case(seeded_session, RefDeviationType)
    seeded_session.commit()

    names = {value.name for value in list_values(seeded_session, RefDeviationType)}
    assert "thread burr" not in names
    assert "Thread burr" in names
    assert "Lonely lowercase" in names
    assert report, "нормализация обязана отчитаться о том, что сделала"


def test_no_list_keeps_two_values_differing_only_in_case(seeded_session: Session) -> None:
    """Критерий 1: проверяется запросом, а не глазами."""
    from db.models import REFERENCE_MODELS
    from domain.reference import normalise_all

    from db.models import RefItemType, RefZone

    _twin(seeded_session, RefItemType, "implant")
    _twin(seeded_session, RefZone, "thread")

    normalise_all(seeded_session)
    seeded_session.commit()

    for model in REFERENCE_MODELS:
        names = [value.name.casefold() for value in list_values(seeded_session, model)]
        assert len(names) == len(set(names)), f"{model.__tablename__}: остались близнецы"


def test_the_seed_does_not_add_a_twin_of_a_differently_cased_value(
    seeded_session: Session,
) -> None:
    """Критерий 4, сид: он и был причиной — сверял имена точно."""
    from db.models import RefDeviationType
    from seed.reference import seed_reference

    _twin(seeded_session, RefDeviationType, "thread burr")
    before = len(list_values(seeded_session, RefDeviationType))

    seed_reference(seeded_session)
    seeded_session.commit()

    after = list_values(seeded_session, RefDeviationType)
    assert len(after) == before, "сид дописал близнеца"


def test_renaming_into_a_differently_cased_twin_is_refused(seeded_session: Session) -> None:
    """Критерий 4, правка: близнец не заводится и переименованием."""
    from db.models import RefZone

    zone = _twin(seeded_session, RefZone, "neck")
    with pytest.raises(DuplicateValue):
        rename_value(seeded_session, RefZone, zone, "THREAD")
