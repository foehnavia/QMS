"""Критерии приёмки 2–4 — заведение детали, сид CG-размеров, CG на лету."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import reopen
from db.models import GENERAL, Item, RefConnectionType, RefItemType, RefSize
from domain.errors import DuplicateValue, ValidationError
from domain.groups import GPositionSpec, create_group, list_groups
from domain.items import create_item, groups_of, seed_cg_characteristics
from seed.reference import ref

POSITIONS = (
    GPositionSpec(g_index=1, nominal=3.75, tol_plus=0.05, tol_minus=-0.05),
    GPositionSpec(g_index=2, nominal=2.00, tol_plus=0.00, tol_minus=-0.05),
    GPositionSpec(g_index=3, nominal=0.50, tol_plus=0.02, tol_minus=-0.02),
)


def _new_item(session: Session, number: str = "C1-08375A") -> Item:
    return create_item(
        session,
        item_number=number,
        item_type=ref(session, RefItemType, "implant"),
        connection_type=ref(session, RefConnectionType, "C1"),
        size=ref(session, RefSize, "NP"),
    )


def test_item_is_created_with_classifiers(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    seeded_session.commit()

    assert (item.item_type.name, item.connection_type.name, item.size.name) == (
        "implant",
        "C1",
        "NP",
    )


def test_item_defaults_to_general(seeded_session: Session) -> None:
    """Деталь заводится, когда специфика ещё не важна (`Item.md`)."""
    item = create_item(
        seeded_session,
        item_number="MT-SRH19A",
        connection_type=ref(seeded_session, RefConnectionType, GENERAL),
        size=ref(seeded_session, RefSize, GENERAL),
    )
    seeded_session.commit()

    assert item.item_type is None
    assert (item.connection_type.name, item.size.name) == (GENERAL, GENERAL)


def test_duplicate_item_number_is_a_domain_error(seeded_session: Session) -> None:
    _new_item(seeded_session)
    seeded_session.flush()

    with pytest.raises(DuplicateValue) as excinfo:
        _new_item(seeded_session)
    assert "C1-08375A" in str(excinfo.value)


def test_blank_item_number_is_rejected(seeded_session: Session) -> None:
    with pytest.raises(ValidationError):
        create_item(
            seeded_session,
            item_number="   ",
            connection_type=ref(seeded_session, RefConnectionType, GENERAL),
            size=ref(seeded_session, RefSize, GENERAL),
        )


# --- Сид CG-размеров (критерий 3, заметка Б) ------------------------------------


def test_cg_seed_creates_characteristics_and_mappings(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "Implant_Con_375_C1", POSITIONS)

    created = seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()

    assert [char.local_number for char in created] == ["12", "19", "32"]
    for char in created:
        assert char.mapping is not None
        assert char.mapping.g_position is not None
        assert char.mapping.is_absent is False
    # геометрия осталась на g-позиции и на характеристику не скопирована
    assert created[0].mapping.g_position.nominal == 3.75
    assert not hasattr(created[0], "nominal")


def test_local_numbers_are_required_for_every_position(seeded_session: Session) -> None:
    """Номер размера — с чертежа детали; автоподстановки по `g_index` нет."""
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)

    with pytest.raises(ValidationError) as excinfo:
        seed_cg_characteristics(seeded_session, item, group, {})
    assert "g1" in str(excinfo.value)

    with pytest.raises(ValidationError):
        seed_cg_characteristics(seeded_session, item, group, {1: "12", 3: "32"})


def test_local_number_is_bound_to_the_right_position(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)

    created = seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()

    assert created[1].local_number == "19"
    assert created[1].mapping.g_position.g_index == 2


def test_cg_membership_is_derived_not_stored(seeded_session: Session) -> None:
    """Item↔CG — через characteristic→mapping→g_position→cg, отдельной таблицы нет."""
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()

    assert [g.name for g in groups_of(item)] == ["CG-A"]
    assert groups_of(create_item(
        seeded_session,
        item_number="NO-CG",
        connection_type=ref(seeded_session, RefConnectionType, GENERAL),
        size=ref(seeded_session, RefSize, GENERAL),
    )) == []


def test_duplicate_local_numbers_in_the_seed_are_rejected(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)

    with pytest.raises(DuplicateValue):
        seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "12", 3: "32"})


def test_seed_clashing_with_existing_characteristics_is_rejected(seeded_session: Session) -> None:
    from domain.characteristics import get_or_create_characteristic

    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    get_or_create_characteristic(seeded_session, item, "19")

    with pytest.raises(DuplicateValue) as excinfo:
        seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    assert "19" in str(excinfo.value)


def test_blank_local_number_is_rejected(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)

    with pytest.raises(ValidationError):
        seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "  ", 3: "32"})


# --- CG на лету, R3 (критерий 4) -------------------------------------------------


def test_group_is_created_with_geometry(seeded_session: Session) -> None:
    group = create_group(seeded_session, "  Implant_Con_375_C1  ", POSITIONS)
    seeded_session.commit()

    assert group.name == "Implant_Con_375_C1"
    assert [p.g_index for p in group.positions] == [1, 2, 3]
    assert (group.positions[0].nominal, group.positions[0].tol_minus) == (3.75, -0.05)
    assert [g.name for g in list_groups(seeded_session)] == ["Implant_Con_375_C1"]


def test_group_created_on_the_fly_is_immediately_bindable(seeded_session: Session) -> None:
    """R3: недостающая группа заводится прямо в потоке заведения детали."""
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-new", (GPositionSpec(g_index=1, nominal=1.0),))
    seed_cg_characteristics(seeded_session, item, group, {1: "7"})
    seeded_session.commit()

    assert [g.name for g in groups_of(item)] == ["CG-new"]


@pytest.mark.parametrize(
    "name, positions",
    [
        ("", POSITIONS),
        ("CG-A", ()),
        ("CG-A", (GPositionSpec(g_index=0),)),
    ],
)
def test_invalid_group_input_is_rejected(seeded_session: Session, name, positions) -> None:
    with pytest.raises(ValidationError):
        create_group(seeded_session, name, positions)


def test_duplicate_group_name_and_index_are_rejected(seeded_session: Session) -> None:
    create_group(seeded_session, "CG-A", POSITIONS)
    with pytest.raises(DuplicateValue):
        create_group(seeded_session, "CG-A", POSITIONS)
    with pytest.raises(DuplicateValue):
        create_group(seeded_session, "CG-B", (GPositionSpec(1), GPositionSpec(1)))


def test_seeded_item_survives_a_reopen(migrated_url: str, seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    seed_cg_characteristics(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        stored = fresh.query(Item).filter_by(item_number="C1-08375A").one()
        assert sorted(c.local_number for c in stored.characteristics) == ["12", "19", "32"]
        assert all(c.mapping.g_position is not None for c in stored.characteristics)
        assert [g.name for g in groups_of(stored)] == ["CG-A"]
