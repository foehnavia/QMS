"""Ревизия чертежа: клон, инварианты, прецеденты через ревизию (QMS-017, наряд 0024).

Главный предмет здесь — **клон**. Ревизия, где сдвинулся один допуск, и ревизия,
где переехали все номера, обязаны стоить оператору одного действия; и при этом
прежняя ревизия обязана остаться нетронутой, потому что на неё уже ссылаются
записанные отклонения. Поэтому клон проверяется построчно, а не по счётчику:
совпадение количеств прошло бы и при перенесённых, а не скопированных строках.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import make_item, rev
from db.models import CharacteristicGroup, GPosition, ItemRevision
from domain.deviations import register, set_revision
from domain.errors import DuplicateValue, InvariantViolation, ValidationError
from domain.findings import make_finding
from domain.groups import GPositionSpec, add_position, has_no_current_items, revisions_awaiting_answer
from domain.mappings import bind, mark_absent
from domain.revisions import (
    characteristic_by_number,
    clone_revision,
    create_revision,
    current_revision,
    previous_revision,
    revisions_with_number,
    set_current,
)


def _group(session: Session, name: str = "CG-A", indexes=(1, 2, 3)) -> CharacteristicGroup:
    group = CharacteristicGroup(name=name)
    group.positions = [GPosition(g_index=i, nominal=float(i)) for i in indexes]
    session.add(group)
    session.flush()
    return group


def _stocked(session: Session, number: str = "IT-001"):
    """Деталь ревизии A: два привязанных размера, один не-канонный, один код 99."""
    item = make_item(session, number)
    group = _group(session)
    revision = rev(item)
    bind(session, revision, group.positions[0], "12")
    bind(session, revision, group.positions[1], "19")
    mark_absent(session, revision, group.positions[2])
    # Не-канонный размер: у детали он есть, g-позиции ему не нашлось.
    from domain.characteristics import get_or_create_characteristic

    get_or_create_characteristic(session, revision, "32")
    session.flush()
    return item, group


# --- Лента ревизий ------------------------------------------------------------------


def test_a_second_current_revision_is_refused(seeded_session: Session) -> None:
    """Ровно одна действующая на деталь — держит частичный уникальный индекс."""
    item = make_item(seeded_session, "IT-001")
    seeded_session.add(
        ItemRevision(item=item, designation="B", seq=2, is_current=True)
    )
    with pytest.raises(IntegrityError):
        seeded_session.flush()


def test_a_second_non_current_revision_is_fine(seeded_session: Session) -> None:
    """Частичный индекс сторожит только действующие — прошлых бывает сколько угодно."""
    item = make_item(seeded_session, "IT-001")
    seeded_session.add(ItemRevision(item=item, designation="B", seq=2, is_current=False))
    seeded_session.flush()

    assert len(item.revisions) == 2


def test_previous_is_named_by_seq_not_by_designation(seeded_session: Session) -> None:
    """Порядок хранится явно: `A1` после `B` — законная пара обозначений.

    Ради этого вопроса `seq` в схеме и есть: по строке обозначения ответить
    нельзя, а «предыдущую» система обязана уметь назвать.
    """
    item = make_item(seeded_session, "IT-001", revision="B")
    later = create_revision(seeded_session, item, designation="A1")

    assert previous_revision(later).designation == "B"
    assert previous_revision(rev(item)) is None or previous_revision(later) is not None


def test_a_repeated_designation_is_refused(seeded_session: Session) -> None:
    item = make_item(seeded_session, "IT-001", revision="A")
    with pytest.raises(DuplicateValue):
        create_revision(seeded_session, item, designation="a")


def test_an_empty_designation_is_refused(seeded_session: Session) -> None:
    """Обозначение приходит с чертежа; пустое — не «потом заполним», а ошибка."""
    item = make_item(seeded_session, "IT-001")
    with pytest.raises(ValidationError):
        create_revision(seeded_session, item, designation="   ")


def test_set_current_moves_the_flag_without_tripping_the_index(
    seeded_session: Session,
) -> None:
    """Признак снимается до установки — иначе flush падал бы на частичном индексе."""
    item = make_item(seeded_session, "IT-001")
    first = rev(item)
    second = create_revision(seeded_session, item, designation="B", make_current=False)

    set_current(seeded_session, second)

    assert current_revision(item) is second
    assert first.is_current is False


# --- Клон ----------------------------------------------------------------------------


def test_clone_carries_numbers_mappings_and_code_99(seeded_session: Session) -> None:
    item, group = _stocked(seeded_session)
    source = rev(item)

    clone = clone_revision(seeded_session, item, source, designation="B")

    assert {c.local_number for c in clone.characteristics} == {"12", "19", "32"}
    assert {
        c.local_number: c.mapping.g_position.g_index
        for c in clone.characteristics
        if c.mapping is not None
    } == {"12": 1, "19": 2}
    assert [a.g_position.g_index for a in clone.absent_positions] == [3]
    assert clone.is_current is True


def test_clone_leaves_the_previous_revision_untouched(seeded_session: Session) -> None:
    """Построчно, а не по счётчику.

    Совпадение количеств прошло бы и при **перенесённых** строках, а перенос —
    ровно та ошибка, которой нельзя допустить: на прежнюю ревизию уже ссылаются
    записанные отклонения и находки.
    """
    item, _group = _stocked(seeded_session)
    source = rev(item)
    before = {
        c.characteristic_id: (
            c.local_number,
            c.mapping.g_position_id if c.mapping else None,
        )
        for c in source.characteristics
    }
    absent_before = {a.absent_id: a.g_position_id for a in source.absent_positions}

    clone = clone_revision(seeded_session, item, source, designation="B")

    after = {
        c.characteristic_id: (
            c.local_number,
            c.mapping.g_position_id if c.mapping else None,
        )
        for c in source.characteristics
    }
    assert after == before
    assert {a.absent_id: a.g_position_id for a in source.absent_positions} == absent_before
    # Копируются **значения**, а не строки: у клона свои идентификаторы.
    assert not ({c.characteristic_id for c in clone.characteristics} & set(before))
    assert source.is_current is False


def test_clone_does_not_disturb_findings_of_the_previous_revision(
    seeded_session: Session,
) -> None:
    """Находка прежней ревизии остаётся при своём размере — он никуда не уехал."""
    item, _group = _stocked(seeded_session)
    source = rev(item)
    deviation = register(
        seeded_session, item=item, wo="W1", quantity=1, date=date(2026, 8, 1)
    )
    target = characteristic_by_number(source, "12")
    finding = make_finding(seeded_session, deviation, target, direction="+", value=0.02)

    clone_revision(seeded_session, item, source, designation="B")

    assert finding.characteristic is target
    assert finding.characteristic.revision is source
    assert deviation.revision is source


def test_a_clone_from_another_item_is_refused(seeded_session: Session) -> None:
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    with pytest.raises(ValidationError):
        clone_revision(seeded_session, second, rev(first), designation="B")


# --- Отклонение и ревизия ------------------------------------------------------------


def test_registration_takes_the_current_revision(seeded_session: Session) -> None:
    item, _group = _stocked(seeded_session)
    clone = clone_revision(seeded_session, item, rev(item), designation="B")

    deviation = register(
        seeded_session, item=item, wo="W1", quantity=1, date=date(2026, 8, 1)
    )

    assert deviation.revision is clone


def test_registration_accepts_a_previous_revision_explicitly(
    seeded_session: Session,
) -> None:
    """Детали прежнего выпуска приходят из цеха ещё два-три месяца."""
    item, _group = _stocked(seeded_session)
    source = rev(item)
    clone_revision(seeded_session, item, source, designation="B")

    deviation = register(
        seeded_session,
        item=item,
        revision=source,
        wo="W1",
        quantity=1,
        date=date(2026, 8, 1),
    )

    assert deviation.revision is source


def test_a_revision_of_another_item_is_refused(seeded_session: Session) -> None:
    first = make_item(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    with pytest.raises(InvariantViolation):
        register(
            seeded_session,
            item=first,
            revision=rev(second),
            wo="W1",
            quantity=1,
            date=date(2026, 8, 1),
        )


def test_a_finding_from_another_revision_is_refused(seeded_session: Session) -> None:
    """Гард ужесточён с детали до ревизии: совпадения детали больше не достаточно."""
    item, _group = _stocked(seeded_session)
    source = rev(item)
    clone = clone_revision(seeded_session, item, source, designation="B")
    deviation = register(
        seeded_session, item=item, revision=clone, wo="W1", quantity=1, date=date(2026, 8, 1)
    )
    stale = characteristic_by_number(source, "12")

    with pytest.raises(InvariantViolation):
        make_finding(seeded_session, deviation, stale, direction="+", value=0.02)


def test_moving_a_deviation_with_findings_is_refused(seeded_session: Session) -> None:
    """Перевод не пересчитывает находки — он их проверяет и отбивается, если те чужие."""
    item, _group = _stocked(seeded_session)
    source = rev(item)
    deviation = register(
        seeded_session, item=item, wo="W1", quantity=1, date=date(2026, 8, 1)
    )
    make_finding(
        seeded_session,
        deviation,
        characteristic_by_number(source, "12"),
        direction="+",
        value=0.02,
    )
    clone = clone_revision(seeded_session, item, source, designation="B")

    with pytest.raises(InvariantViolation):
        set_revision(seeded_session, deviation, clone)


# --- Группа и прошлые ревизии ---------------------------------------------------------


def test_a_new_g_position_asks_only_the_current_revisions(seeded_session: Session) -> None:
    """Прошлые ревизии остаются без ответа: их чертёж выпущен и не меняется."""
    item, group = _stocked(seeded_session)
    source = rev(item)
    clone = clone_revision(seeded_session, item, source, designation="B")

    add_position(seeded_session, group, GPositionSpec(4, 4.0))

    awaiting = revisions_awaiting_answer(seeded_session, group)
    assert awaiting == [clone]
    assert source not in awaiting
    # «Без ответа» — это отсутствие строки, а не третье состояние.
    assert len(source.absent_positions) == 1


def test_a_group_whose_items_all_moved_on_reports_no_current_items(
    seeded_session: Session,
) -> None:
    """Признак вычисляемый: группа опустела, ни одной действующей ревизии в ней нет."""
    item, group = _stocked(seeded_session)
    assert has_no_current_items(seeded_session, group) is False

    # Новая ревизия заводится пустой — к группе она не привязана.
    create_revision(seeded_session, item, designation="B")

    assert has_no_current_items(seeded_session, group) is True


# --- Прецеденты через ревизию ---------------------------------------------------------


def test_the_direct_path_searches_every_revision_of_the_item(
    seeded_session: Session,
) -> None:
    """Прямой путь ищет по номеру во всех ревизиях и возвращает ревизию совпадения."""
    item, _group = _stocked(seeded_session)
    source = rev(item)

    assert [r.designation for r in revisions_with_number(item, "12")] == ["A"]

    clone_revision(seeded_session, item, source, designation="B")

    assert [r.designation for r in revisions_with_number(item, "12")] == ["A", "B"]


def test_a_number_absent_from_a_revision_is_reported_as_such(
    seeded_session: Session,
) -> None:
    """На этом ответе форма строит пометку «not in this revision»."""
    item, _group = _stocked(seeded_session)
    source = rev(item)
    clone = clone_revision(seeded_session, item, source, designation="B")
    # Оператор снял размер 32 с нового чертежа.
    clone.characteristics.remove(characteristic_by_number(clone, "32"))
    seeded_session.flush()

    assert characteristic_by_number(source, "32") is not None
    assert characteristic_by_number(clone, "32") is None


def _decided(session: Session, item, revision, local_number: str, wo: str):
    """Отклонение с решением на данном размере — прецедент виден только решённый."""
    deviation = register(
        session, item=item, revision=revision, wo=wo, quantity=1, date=date(2026, 8, 1)
    )
    make_finding(
        session,
        deviation,
        characteristic_by_number(revision, local_number),
        direction="+",
        value=0.02,
    )
    deviation.decision_dev = "approved"
    deviation.explanation = "ok"
    session.flush()
    return deviation


def test_the_canon_path_resolves_through_the_own_revision_mapping(
    seeded_session: Session,
) -> None:
    """Номер переехал между ревизиями — канонный путь всё равно находит прецедент.

    Ради этого канон и заведён: g-позиция переживает перевыпуск чертежа, а
    локальный номер — нет. Маппинг висит на размере, размер на ревизии, поэтому
    своей колонки ревизии маппингу не понадобилось.
    """
    from domain.precedents import precedents_same_position

    first, group = _stocked(seeded_session, "IT-001")
    second = make_item(seeded_session, "IT-002")
    bind(seeded_session, rev(second), group.positions[0], "7")
    _decided(seeded_session, second, rev(second), "7", "W-OTHER")

    # У первой детали выходит новый чертёж, и номер g1 переезжает с 12 на 13.
    source = rev(first)
    clone = clone_revision(seeded_session, first, source, designation="B")
    moved = characteristic_by_number(clone, "12")
    moved.local_number = "13"
    seeded_session.flush()

    rows = precedents_same_position(seeded_session, moved)

    assert [row.item_number for row in rows] == ["IT-002"]
    # Канонный размер пометки не несёт: он разрешён через маппинг своей ревизии.
    assert rows[0].is_canon_bound is True


def test_the_direct_path_marks_a_match_from_another_revision(
    seeded_session: Session,
) -> None:
    """Обе пометки — там, где положено, и **не** там, где нет."""
    from domain.precedents import precedents_same_dimension

    item, _group = _stocked(seeded_session, "IT-001")
    source = rev(item)
    _decided(seeded_session, item, source, "12", "W-OLD")
    _decided(seeded_session, item, source, "32", "W-OLD-NONCANON")

    clone = clone_revision(seeded_session, item, source, designation="B")

    canon_now = characteristic_by_number(clone, "12")
    rows = precedents_same_dimension(seeded_session, canon_now)
    assert [row.revision for row in rows] == ["A"]
    assert rows[0].other_revision is True, "совпадение из прошлой ревизии обязано помечаться"
    assert rows[0].is_canon_bound is True, "канонный размер знака ! не несёт"

    noncanon_now = characteristic_by_number(clone, "32")
    rows = precedents_same_dimension(seeded_session, noncanon_now)
    assert rows[0].other_revision is True
    assert rows[0].is_canon_bound is False, "не-канонный размер обязан нести знак !"


def test_a_match_inside_the_same_revision_carries_no_marks(
    seeded_session: Session,
) -> None:
    """Обратная сторона: та же ревизия, канонный размер — ни одной пометки."""
    from domain.precedents import precedents_same_dimension

    item, _group = _stocked(seeded_session, "IT-001")
    source = rev(item)
    _decided(seeded_session, item, source, "12", "W-OLD")

    rows = precedents_same_dimension(seeded_session, characteristic_by_number(source, "12"))

    assert rows and rows[0].other_revision is False
    assert rows[0].is_canon_bound is True
