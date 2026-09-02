"""Правка группы и чертёж (критерии 2, 3, 7 наряда 0003; правка наряда 0014).

Координаты `x`/`y` код больше не пишет (QMS-016): чертёж приходит размеченным.
Проверяется здесь **обратная сторона** этого решения — что новые позиции живут
без координат, а координаты, заведённые до решения, правкой не стираются.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from conftest import make_item, make_png, reopen
from db.models import CharacteristicGroup, GPosition
from domain.errors import DuplicateValue, ValidationError, ValueInUse
from domain.groups import (
    MAX_DRAWING_BYTES,
    GPositionSpec,
    add_position,
    create_group,
    detect_image_format,
    position_usage,
    remove_position,
    set_drawing,
    update_group,
    update_position,
)
from domain.mappings import bind, mark_absent

POSITIONS = (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0))


def _group(session: Session, name: str = "CG-A") -> CharacteristicGroup:
    return create_group(session, name, POSITIONS)


def _legacy_coordinates(session: Session, position: GPosition, x: float, y: float) -> GPosition:
    """Проставить координаты **мимо домена** — как их проставила прежняя форма.

    Доменного пути к `x`/`y` больше нет, а данные с ними в базе есть: их завела
    механика баллонов до наряда 0014. Тесты ниже проверяют, что эти значения
    переживают правку, поэтому и заводить их приходится так же, как они там
    оказались, — прямо в модель.
    """
    position.x, position.y = x, y
    session.flush()
    return position


def test_group_is_renamed(seeded_session: Session) -> None:
    group = _group(seeded_session)
    update_group(seeded_session, group, name="  CG-Б  ")
    seeded_session.commit()

    assert group.name == "CG-Б"


def test_rename_onto_an_existing_name_is_refused(seeded_session: Session) -> None:
    _group(seeded_session, "CG-A")
    other = _group(seeded_session, "CG-B")

    with pytest.raises(DuplicateValue):
        update_group(seeded_session, other, name="CG-A")


def test_blank_group_name_is_refused(seeded_session: Session) -> None:
    group = _group(seeded_session)
    with pytest.raises(ValidationError):
        update_group(seeded_session, group, name="   ")


def test_position_is_added_and_updated(seeded_session: Session) -> None:
    group = _group(seeded_session)

    added = add_position(seeded_session, group, GPositionSpec(3, 0.5, 0.02, -0.02))
    update_position(seeded_session, added, nominal=0.6, tol_plus=0.03, tol_minus=-0.03)
    seeded_session.commit()

    assert (added.g_index, added.nominal, added.tol_plus) == (3, 0.6, 0.03)
    # Критерий 6 наряда 0014: у новой позиции координат нет и после правки.
    assert (added.x, added.y) == (None, None)


def test_a_position_may_carry_a_tolerance_without_a_nominal(seeded_session: Session) -> None:
    """Критерий 4: допуск формы заводится обычной позицией, номинала у неё нет."""
    group = _group(seeded_session)

    added = add_position(seeded_session, group, GPositionSpec(3, None, 0.02, -0.02))
    seeded_session.commit()

    assert (added.nominal, added.tol_plus, added.tol_minus) == (None, 0.02, -0.02)


def test_editing_geometry_leaves_old_coordinates_alone(seeded_session: Session) -> None:
    """Заведённое прежней механикой не стирается: миграции наряд не заказывал."""
    group = _group(seeded_session)
    position = _legacy_coordinates(seeded_session, group.positions[0], 0.3, 0.7)

    update_position(seeded_session, position, nominal=4.0, tol_plus=0.1, tol_minus=-0.1)
    seeded_session.commit()

    assert (position.nominal, position.tol_plus) == (4.0, 0.1)
    assert (position.x, position.y) == (0.3, 0.7)


def test_update_position_demands_every_field(seeded_session: Session) -> None:
    """Ревью S3, п. 3: у `update_position` нет значений по умолчанию.

    С ними вызов «поменяй только номинал» молча обнулял бы допуски — подпись
    приглашала наступить на это в S4.
    """
    group = _group(seeded_session)

    with pytest.raises(TypeError):
        update_position(seeded_session, group.positions[0], nominal=1.0)


def test_update_position_no_longer_takes_coordinates(seeded_session: Session) -> None:
    """Критерий 6: писать `x`/`y` больше нечем — параметров у домена нет."""
    group = _group(seeded_session)

    with pytest.raises(TypeError):
        update_position(
            seeded_session,
            group.positions[0],
            nominal=1.0,
            tol_plus=None,
            tol_minus=None,
            x=0.5,
            y=0.5,
        )


def test_duplicate_position_index_is_refused(seeded_session: Session) -> None:
    group = _group(seeded_session)
    with pytest.raises(DuplicateValue):
        add_position(seeded_session, group, GPositionSpec(1))


def test_a_new_position_carries_no_coordinates(seeded_session: Session) -> None:
    """Критерий 6: `GPositionSpec` координат не принимает, позиция их не несёт."""
    group = _group(seeded_session)

    with pytest.raises(TypeError):
        GPositionSpec(9, x=0.5, y=0.5)

    added = add_position(seeded_session, group, GPositionSpec(9))
    seeded_session.commit()
    assert (added.x, added.y) == (None, None)


# --- Предельные отклонения: единственный инвариант пары (наряд 0015) ----------------


@pytest.mark.parametrize(
    "upper, lower",
    [
        (0.05, -0.05),  # симметричное поле
        (0.05, 0.02),  # посадка с натягом: оба в плюс
        (-0.02, -0.05),  # оба в минус
        (0.05, 0.05),  # равные — не переставлены
        (0.05, None),  # задано одно
        (None, -0.05),
    ],
)
def test_any_pair_with_the_upper_not_below_the_lower_is_accepted(
    seeded_session: Session, upper, lower
) -> None:
    """Критерий 3: проверки знака нет — законны и `+/+`, и `−/−`, и `+/−`.

    Прежняя редакция находки предлагала считать нижнее отклонение всегда
    отрицательным. Это неправда: у посадок с натягом оба уходят в плюс, и
    отбивать такую пару значило бы запрещать реальную геометрию.
    """
    group = _group(seeded_session)

    added = add_position(seeded_session, group, GPositionSpec(9, 3.75, upper, lower))
    seeded_session.commit()

    assert (added.tol_plus, added.tol_minus) == (upper, lower)


def test_swapped_deviations_are_refused_on_add(seeded_session: Session) -> None:
    """Верхнее ниже нижнего — поле допуска вывернуто наизнанку."""
    group = _group(seeded_session)

    with pytest.raises(ValidationError) as excinfo:
        add_position(seeded_session, group, GPositionSpec(9, 3.75, 0.02, 0.05))

    # Сообщение называет обе величины: оператор должен видеть, что переставлено.
    assert "0.02" in str(excinfo.value) and "0.05" in str(excinfo.value)
    assert "swapped" in str(excinfo.value)


def test_swapped_deviations_are_refused_on_create(seeded_session: Session) -> None:
    with pytest.raises(ValidationError):
        create_group(
            seeded_session, "CG-SWAP", (GPositionSpec(1, 3.75, -0.05, 0.05),)
        )


def test_swapped_deviations_are_refused_on_update(seeded_session: Session) -> None:
    """Третий путь ввода — правка позиции; инвариант живёт в домене, не в форме."""
    group = _group(seeded_session)

    with pytest.raises(ValidationError):
        update_position(
            seeded_session,
            group.positions[0],
            nominal=3.75,
            tol_plus=-0.05,
            tol_minus=0.05,
        )


def test_the_refusal_speaks_the_minus_the_screen_shows(seeded_session: Session) -> None:
    """Сообщение читает оператор — значит это интерфейс (`CLAUDE.md` §9).

    Минус в нём тот же, что в ячейке: `−` (U+2212), а не ASCII-дефис.
    """
    group = _group(seeded_session)

    with pytest.raises(ValidationError) as excinfo:
        add_position(seeded_session, group, GPositionSpec(9, 3.75, -0.05, -0.02))

    assert "−0.05" in str(excinfo.value) and "-0.05" not in str(excinfo.value)


def test_free_position_is_removed(seeded_session: Session) -> None:
    group = _group(seeded_session)
    position = group.positions[1]

    remove_position(seeded_session, position)
    seeded_session.commit()

    assert [p.g_index for p in group.positions] == [1]


def test_position_used_by_a_binding_is_protected(seeded_session: Session) -> None:
    group = _group(seeded_session)
    item = make_item(seeded_session, "IT-001")
    bind(seeded_session, item, group.positions[0], "12")

    assert position_usage(seeded_session, group.positions[0]) == 1
    with pytest.raises(ValueInUse) as excinfo:
        remove_position(seeded_session, group.positions[0])
    assert "g1" in str(excinfo.value) and "1" in str(excinfo.value)


def test_position_used_by_an_absence_is_protected(seeded_session: Session) -> None:
    """Отметка «нет у детали» держит позицию так же, как привязка."""
    group = _group(seeded_session)
    item = make_item(seeded_session, "IT-001")
    mark_absent(seeded_session, item, group.positions[1])

    assert position_usage(seeded_session, group.positions[1]) == 1
    with pytest.raises(ValueInUse):
        remove_position(seeded_session, group.positions[1])


# --- Чертёж ----------------------------------------------------------------------


def test_drawing_is_stored_in_the_database(migrated_url: str, seeded_session: Session) -> None:
    """Критерий 2: чертёж переживает перезапуск, потому что лежит в самой БД."""
    group = _group(seeded_session)
    data = make_png(24, 18)

    set_drawing(seeded_session, group, data, "cg-a.png")
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        stored = fresh.query(CharacteristicGroup).one()
        assert stored.drawing == data
        assert stored.drawing_name == "cg-a.png"


def test_drawing_is_detected_by_signature_not_extension(seeded_session: Session) -> None:
    group = _group(seeded_session)

    with pytest.raises(ValidationError) as excinfo:
        set_drawing(seeded_session, group, b"PK\x03\x04 not an image at all", "drawing.png")
    assert "PNG" in str(excinfo.value)
    assert group.drawing is None


def test_oversized_drawing_is_refused(seeded_session: Session) -> None:
    group = _group(seeded_session)
    oversized = make_png()[:8] + b"\x00" * (MAX_DRAWING_BYTES + 1)

    with pytest.raises(ValidationError) as excinfo:
        set_drawing(seeded_session, group, oversized, "big.png")
    assert "5" in str(excinfo.value)


def test_jpeg_is_accepted() -> None:
    assert detect_image_format(b"\xff\xd8\xff\xe0 jpeg body") == "JPEG"
    assert detect_image_format(b"just text") is None


def test_dropping_the_drawing_keeps_old_coordinates(seeded_session: Session) -> None:
    """Снятие чертежа не трогает позиции — в том числе прежние координаты."""
    group = _group(seeded_session)
    _legacy_coordinates(seeded_session, group.positions[0], 0.3, 0.7)
    set_drawing(seeded_session, group, make_png(), "cg.png")

    set_drawing(seeded_session, group, None, None)
    seeded_session.commit()

    assert group.drawing is None
    assert (group.positions[0].x, group.positions[0].y) == (0.3, 0.7)


def test_replacing_the_drawing_keeps_coordinates(seeded_session: Session) -> None:
    group = _group(seeded_session)
    _legacy_coordinates(seeded_session, group.positions[0], 0.2, 0.2)
    set_drawing(seeded_session, group, make_png(10, 10), "first.png")

    set_drawing(seeded_session, group, make_png(40, 30), "second.png")
    seeded_session.commit()

    assert group.drawing_name == "second.png"
    assert (group.positions[0].x, group.positions[0].y) == (0.2, 0.2)


def test_coordinates_survive_a_reopen(migrated_url: str, seeded_session: Session) -> None:
    """Заведённое до QMS-016 переживает перезапуск: миграции наряд не заказывал."""
    group = _group(seeded_session)
    _legacy_coordinates(seeded_session, group.positions[0], 0.125, 0.875)
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        position = fresh.query(GPosition).filter_by(g_index=1).one()
        assert (position.x, position.y) == (0.125, 0.875)
