"""Правка группы и чертёж (критерии 2, 3, 7 наряда 0003)."""

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


def _move(session: Session, position: GPosition, x: float, y: float) -> GPosition:
    """Переставить баллон, сохранив геометрию.

    `update_position` заменяет позицию целиком, поэтому «сдвинуть баллон» —
    это передать и то, что не меняется. Помощник держит правило на виду.
    """
    return update_position(
        session,
        position,
        nominal=position.nominal,
        tol_plus=position.tol_plus,
        tol_minus=position.tol_minus,
        x=x,
        y=y,
    )


# --- Название и позиции ----------------------------------------------------------


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

    added = add_position(seeded_session, group, GPositionSpec(3, 0.5, 0.02, -0.02, 0.25, 0.75))
    update_position(seeded_session, added, nominal=0.6, tol_plus=0.03, tol_minus=-0.03, x=0.4, y=0.4)
    seeded_session.commit()

    assert (added.g_index, added.nominal, added.tol_plus) == (3, 0.6, 0.03)
    assert (added.x, added.y) == (0.4, 0.4)


def test_update_position_demands_every_field(seeded_session: Session) -> None:
    """Ревью S3, п. 3: у `update_position` нет значений по умолчанию.

    С ними вызов «поменяй только номинал» молча обнулял бы допуски и координаты
    баллона — подпись приглашала наступить на это в S4.
    """
    group = _group(seeded_session)

    with pytest.raises(TypeError):
        update_position(seeded_session, group.positions[0], nominal=1.0)


def test_moving_a_balloon_keeps_the_geometry(seeded_session: Session) -> None:
    """Обратная сторона того же: сдвиг баллона не трогает номинал и допуски."""
    group = _group(seeded_session)
    position = group.positions[0]

    _move(seeded_session, position, 0.9, 0.1)
    seeded_session.commit()

    assert (position.nominal, position.tol_plus, position.tol_minus) == (3.75, 0.05, -0.05)
    assert (position.x, position.y) == (0.9, 0.1)


def test_duplicate_position_index_is_refused(seeded_session: Session) -> None:
    group = _group(seeded_session)
    with pytest.raises(DuplicateValue):
        add_position(seeded_session, group, GPositionSpec(1))


@pytest.mark.parametrize("x, y", [(1.5, 0.5), (0.5, -0.1)])
def test_coordinates_outside_zero_one_are_refused(seeded_session: Session, x, y) -> None:
    """Нормализованные координаты — иначе баллон уедет за чертёж (заметка А)."""
    group = _group(seeded_session)
    with pytest.raises(ValidationError):
        add_position(seeded_session, group, GPositionSpec(9, x=x, y=y))


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


def test_dropping_the_drawing_keeps_balloon_coordinates(seeded_session: Session) -> None:
    """Заметка Б: снятие чертежа не роняет расстановку баллонов."""
    group = _group(seeded_session)
    _move(seeded_session, group.positions[0], 0.3, 0.7)
    set_drawing(seeded_session, group, make_png(), "cg.png")

    set_drawing(seeded_session, group, None, None)
    seeded_session.commit()

    assert group.drawing is None
    assert (group.positions[0].x, group.positions[0].y) == (0.3, 0.7)


def test_replacing_the_drawing_keeps_coordinates(seeded_session: Session) -> None:
    group = _group(seeded_session)
    _move(seeded_session, group.positions[0], 0.2, 0.2)
    set_drawing(seeded_session, group, make_png(10, 10), "first.png")

    set_drawing(seeded_session, group, make_png(40, 30), "second.png")
    seeded_session.commit()

    assert group.drawing_name == "second.png"
    assert (group.positions[0].x, group.positions[0].y) == (0.2, 0.2)


def test_coordinates_survive_a_reopen(migrated_url: str, seeded_session: Session) -> None:
    """Критерий 3: место баллона переживает перезапуск."""
    group = _group(seeded_session)
    _move(seeded_session, group.positions[0], 0.125, 0.875)
    seeded_session.commit()
    seeded_session.close()

    with reopen(migrated_url) as fresh:
        position = fresh.query(GPosition).filter_by(g_index=1).one()
        assert (position.x, position.y) == (0.125, 0.875)
