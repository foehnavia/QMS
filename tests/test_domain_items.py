"""Заведение детали, привязка к канону, CG на лету, откат заведения.

Засева `seed_cg_characteristics` больше нет (наряд 0018): CG-размеры создаёт
привязка, а форма их не спрашивает. Поэтому там, где тесты сеяли размеры одной
доменной функцией, они теперь **привязывают** — тем же путём, которым идёт
оператор.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import reopen, rev
from db.models import GENERAL, Item, RefConnectionType, RefItemType, RefSize
from domain.errors import DuplicateValue, ValidationError, ValueInUse
from domain.groups import GPositionSpec, create_group, list_groups
from domain.items import create_item, discard_item, groups_of, update_item
from domain.mappings import bind, mark_absent
from seed.reference import ref

POSITIONS = (
    GPositionSpec(g_index=1, nominal=3.75, tol_plus=0.05, tol_minus=-0.05),
    GPositionSpec(g_index=2, nominal=2.00, tol_plus=0.00, tol_minus=-0.05),
    GPositionSpec(g_index=3, nominal=0.50, tol_plus=0.02, tol_minus=-0.02),
)


def _bind_all(session: Session, item: Item, group, numbers: dict[int, str]) -> list:
    """Привязать деталь к позициям группы — так же, как это делает оператор.

    Прежде тесты звали `seed_cg_characteristics`; функции больше нет, и размеры
    создаёт сама привязка (`bind` → `get_or_create_characteristic`). Помощник
    держит на виду, что это один и тот же результат, полученный законным путём.
    """
    created = []
    for position in sorted(group.positions, key=lambda p: p.g_index):
        mapping = bind(session, rev(item), position, numbers[position.g_index])
        created.append(mapping.characteristic)
    return created


def _new_item(session: Session, number: str = "C1-08375A") -> Item:
    return create_item(
        session,
        item_number=number,
        item_type=ref(session, RefItemType, "implant"),
        connection_type=ref(session, RefConnectionType, "C1"),
        size=ref(session, RefSize, "NP"),
        revision="A",
    )


def test_item_is_created_with_classifiers(seeded_session: Session) -> None:
    item = _new_item(seeded_session)
    seeded_session.commit()

    assert (item.item_type.name, item.connection_type.name, item.size.name) == (
        "Implant",
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
        revision="A",
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
        revision="A",
    )


# --- Сид CG-размеров (критерий 3, заметка Б) ------------------------------------


def test_binding_creates_the_characteristics_and_keeps_geometry_on_the_canon(
    seeded_session: Session,
) -> None:
    """Размеры CG заводит привязка; геометрия остаётся на g-позиции.

    Прежде это делал засев формы. Проверка та же и по-прежнему нужна: копия
    номинала на характеристике развела бы канон и деталь на первой же правке
    группы.
    """
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "Implant_Con_375_C1", POSITIONS)

    created = _bind_all(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()

    assert [char.local_number for char in created] == ["12", "19", "32"]
    for char in created:
        assert char.mapping is not None and char.mapping.g_position is not None
    assert created[0].mapping.g_position.nominal == 3.75
    assert not hasattr(created[0], "nominal")
    # Номер лёг на свою позицию, а не на соседнюю.
    assert created[1].mapping.g_position.g_index == 2


def test_cg_membership_is_derived_not_stored(seeded_session: Session) -> None:
    """Item↔CG — через characteristic→mapping→g_position→cg, отдельной таблицы нет."""
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    _bind_all(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()

    assert [g.name for g in groups_of(item)] == ["CG-A"]
    assert groups_of(create_item(
        seeded_session,
        item_number="NO-CG",
        connection_type=ref(seeded_session, RefConnectionType, GENERAL),
        size=ref(seeded_session, RefSize, GENERAL),
        revision="A",
    )) == []


# --- откат заведения: наряд 0018 §3.3 ---------------------------------------------


def test_discarding_a_new_item_leaves_no_trace(seeded_session: Session) -> None:
    """Отказ от привязки снимает **всё**, что записалось за сеанс заведения.

    Деталь с назначенной группой не существует в базе с неполной привязкой
    (§1a). Записать сеанс одной транзакцией нельзя — диалог привязки пишет по
    действию (ратификация S3), — поэтому правило держится удалением.
    """
    from db.models import Characteristic, ItemPositionAbsent, Mapping

    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    bind(seeded_session, rev(item), group.positions[0], "12")
    mark_absent(seeded_session, rev(item), group.positions[1])
    seeded_session.commit()

    discard_item(seeded_session, item)
    seeded_session.commit()

    assert seeded_session.query(Item).count() == 0
    assert seeded_session.query(Characteristic).count() == 0
    assert seeded_session.query(Mapping).count() == 0
    assert seeded_session.query(ItemPositionAbsent).count() == 0
    # Канон при этом цел: откат трогает деталь, а не группу.
    assert len(list_groups(seeded_session)[0].positions) == 3


def test_discarding_does_not_touch_a_neighbour(seeded_session: Session) -> None:
    """Откат узкий: чужие привязки к тем же позициям остаются на месте."""
    group = create_group(seeded_session, "CG-A", POSITIONS)
    doomed = _new_item(seeded_session, "C1-08375A")
    neighbour = _new_item(seeded_session, "C1-08420B")
    bind(seeded_session, rev(doomed), group.positions[0], "12")
    bind(seeded_session, rev(neighbour), group.positions[0], "77")
    seeded_session.commit()

    discard_item(seeded_session, doomed)
    seeded_session.commit()

    assert [item.item_number for item in seeded_session.query(Item)] == ["C1-08420B"]
    assert [char.local_number for char in rev(neighbour).characteristics] == ["77"]


def test_an_item_with_deviations_is_not_discarded(seeded_session: Session) -> None:
    """Гард на чужие записи: это уже не «только что заведённая» деталь.

    Здесь же проходит граница с Q-15: перепривязка существующей детали — своя
    работа со своими гарантиями, и этот узкий откат ей дорогу не занимает.
    """
    from datetime import date

    from domain.deviations import register

    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    bind(seeded_session, rev(item), group.positions[0], "12")
    register(seeded_session, item=item, wo="W26007336", quantity=3, date=date.today())
    seeded_session.commit()

    with pytest.raises(ValueInUse) as excinfo:
        discard_item(seeded_session, item)
    assert "deviation" in str(excinfo.value)
    assert seeded_session.query(Item).count() == 1


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
    _bind_all(seeded_session, item, group, {1: "7"})
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
    _bind_all(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        stored = fresh.query(Item).filter_by(item_number="C1-08375A").one()
        assert sorted(c.local_number for c in rev(stored).characteristics) == ["12", "19", "32"]
        assert all(c.mapping.g_position is not None for c in rev(stored).characteristics)
        assert [g.name for g in groups_of(stored)] == ["CG-A"]


# --- правка детали (ревью наряда 0012, В-2) -----------------------------------------


def test_item_number_can_be_corrected(seeded_session: Session) -> None:
    """Опечатка в каталожном номере лечится правкой, а не перезаливкой базы.

    До этой функции форма умела только создавать, и ошибка в номере на шаге 5
    прогона останавливала его целиком.
    """
    item = _new_item(seeded_session)

    update_item(
        seeded_session,
        item,
        item_number="C1-08375B",
        item_type=ref(seeded_session, RefItemType, "implant"),
        connection_type=ref(seeded_session, RefConnectionType, "C1"),
        size=ref(seeded_session, RefSize, "NP"),
    )

    assert item.item_number == "C1-08375B"


def test_renaming_keeps_the_dimensions(seeded_session: Session) -> None:
    """Номер детали — её имя, а не идентичность: размеры ссылаются на `item_id`."""
    item = _new_item(seeded_session)
    group = create_group(seeded_session, "CG-A", POSITIONS)
    _bind_all(seeded_session, item, group, {1: "12", 2: "19", 3: "32"})

    update_item(
        seeded_session,
        item,
        item_number="C1-99999Z",
        item_type=None,
        connection_type=ref(seeded_session, RefConnectionType, "C1"),
        size=ref(seeded_session, RefSize, "NP"),
    )

    assert sorted(c.local_number for c in rev(item).characteristics) == ["12", "19", "32"]
    assert all(c.mapping.g_position is not None for c in rev(item).characteristics)
    assert [g.name for g in groups_of(item)] == ["CG-A"]


def test_renaming_onto_a_taken_number_is_refused(seeded_session: Session) -> None:
    """Гард уникальности тот же, что при заведении."""
    first = _new_item(seeded_session)
    _new_item(seeded_session, "C1-08420B")

    with pytest.raises(DuplicateValue):
        update_item(
            seeded_session,
            first,
            item_number="C1-08420B",
            item_type=None,
            connection_type=ref(seeded_session, RefConnectionType, "C1"),
            size=ref(seeded_session, RefSize, "NP"),
        )


def test_saving_an_item_under_its_own_number_is_not_a_duplicate(
    seeded_session: Session,
) -> None:
    """Гард смотрит на **другие** записи: сохранить деталь как есть — законно.

    Проверка «есть ли такой номер» без исключения самой записи отбивала бы
    правку классификаторов, при которой номер не трогали.
    """
    item = _new_item(seeded_session)

    update_item(
        seeded_session,
        item,
        item_number="C1-08375A",
        item_type=None,
        connection_type=ref(seeded_session, RefConnectionType, "C1"),
        size=ref(seeded_session, RefSize, "SP"),
    )

    assert item.item_number == "C1-08375A"
    assert item.size.name == "SP"
    assert item.item_type is None


@pytest.mark.parametrize("number", ["", "   "])
def test_renaming_to_an_empty_number_is_refused(seeded_session: Session, number) -> None:
    item = _new_item(seeded_session)

    with pytest.raises(ValidationError):
        update_item(
            seeded_session,
            item,
            item_number=number,
            item_type=None,
            connection_type=ref(seeded_session, RefConnectionType, "C1"),
            size=ref(seeded_session, RefSize, "NP"),
        )
