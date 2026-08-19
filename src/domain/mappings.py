"""Привязка размеров детали к каноническим g-позициям (наряд 0003).

Правило Session-03 §4 — **«1 баллон = 1 локальный размер = 1 привязка»**: на одну
g-позицию у детали приходится ровно один размер, и один размер привязан ровно к
одной позиции. Обе стороны этого правила проверяются здесь.

Состояния пары (деталь, g-позиция) — ровно три:

* `linked(local_number)` — размер привязан (`mapping`);
* `absent` — **код 99**: позицию рассмотрели, у детали её нет
  (`item_position_absent`);
* `none` — ещё не рассматривали.

Перепривязка занятого размера **не молчаливая** (решение Cowork 7): сперва
«Очистить», потом привязать заново — иначе можно потерять прежнюю связь, не
заметив этого.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    Characteristic,
    CharacteristicGroup,
    GPosition,
    Item,
    ItemPositionAbsent,
    Mapping,
)

from .characteristics import get_or_create_characteristic
from .errors import DuplicateValue, InvariantViolation

State = Literal["linked", "absent", "none"]


@dataclass(frozen=True)
class PositionState:
    """Состояние одной g-позиции у конкретной детали — то, чем красится баллон."""

    g_position_id: int
    g_index: int
    state: State
    local_number: str | None = None

    @property
    def is_decided(self) -> bool:
        """Позиция «получила состояние» — номер размера или «нет у детали»."""
        return self.state != "none"


def _drop_mapping(session: Session, mapping: Mapping) -> None:
    """Снять привязку через коллекцию владельца.

    Не `session.delete`: тот оставляет `characteristic.mapping` указывать на
    удалённую строку, и следующая попытка привязать тот же размер упирается в
    призрак. `delete-orphan` на связи удаляет строку и чинит граф разом.
    """
    mapping.characteristic.mapping = None
    session.flush()


def _drop_absence(session: Session, absence: ItemPositionAbsent) -> None:
    absence.item.absent_positions.remove(absence)
    session.flush()


def _mapping_for(session: Session, item: Item, position: GPosition) -> Mapping | None:
    return session.scalar(
        select(Mapping)
        .join(Characteristic, Mapping.characteristic_id == Characteristic.characteristic_id)
        .where(Characteristic.item_id == item.item_id)
        .where(Mapping.g_position_id == position.g_position_id)
    )


def _absence_for(session: Session, item: Item, position: GPosition) -> ItemPositionAbsent | None:
    return session.scalar(
        select(ItemPositionAbsent)
        .where(ItemPositionAbsent.item_id == item.item_id)
        .where(ItemPositionAbsent.g_position_id == position.g_position_id)
    )


def bind(session: Session, item: Item, position: GPosition, local_number: str) -> Mapping:
    """Привязать размер детали к g-позиции; характеристику создаст при отсутствии."""
    characteristic, _ = get_or_create_characteristic(session, item, local_number)

    existing = characteristic.mapping
    if existing is not None:
        if existing.g_position_id == position.g_position_id:
            return existing
        raise InvariantViolation(
            f"Characteristic no. {characteristic.local_number} is already bound to position "
            f"g{existing.g_position.g_index}. Clear that mapping first."
        )

    occupied = _mapping_for(session, item, position)
    if occupied is not None:
        raise DuplicateValue(
            f"Position g{position.g_index} already carries characteristic "
            f"no. {occupied.characteristic.local_number} — one characteristic per position."
        )

    # Привязка отменяет прежнее «у детали этой позиции нет».
    absence = _absence_for(session, item, position)
    if absence is not None:
        _drop_absence(session, absence)

    mapping = Mapping(characteristic=characteristic, g_position=position)
    session.add(mapping)
    session.flush()
    return mapping


def mark_absent(session: Session, item: Item, position: GPosition) -> ItemPositionAbsent:
    """Код 99 — «позицию рассмотрели, у детали её нет». Идемпотентно."""
    mapping = _mapping_for(session, item, position)
    if mapping is not None:
        # Характеристику не трогаем: размер у детали может существовать сам по себе.
        _drop_mapping(session, mapping)

    absence = _absence_for(session, item, position)
    if absence is None:
        absence = ItemPositionAbsent(item=item, g_position=position)
        session.add(absence)
        session.flush()
    return absence


def clear(session: Session, item: Item, position: GPosition) -> None:
    """Вернуть пару в состояние «не рассматривали».

    Характеристику детали **не удаляем**: размер существует независимо от того,
    привязан он к канону или нет.
    """
    mapping = _mapping_for(session, item, position)
    if mapping is not None:
        _drop_mapping(session, mapping)
    absence = _absence_for(session, item, position)
    if absence is not None:
        _drop_absence(session, absence)


def binding_state(
    session: Session, item: Item, group: CharacteristicGroup
) -> list[PositionState]:
    """Состояние каждой g-позиции группы для этой детали (порядок — по `g_index`)."""
    positions = sorted(group.positions, key=lambda position: position.g_index)

    linked = {
        mapping.g_position_id: mapping.characteristic.local_number
        for mapping in session.scalars(
            select(Mapping)
            .join(Characteristic, Mapping.characteristic_id == Characteristic.characteristic_id)
            .where(Characteristic.item_id == item.item_id)
        )
    }
    absent = {
        absence.g_position_id
        for absence in session.scalars(
            select(ItemPositionAbsent).where(ItemPositionAbsent.item_id == item.item_id)
        )
    }

    states: list[PositionState] = []
    for position in positions:
        if position.g_position_id in linked:
            states.append(
                PositionState(
                    position.g_position_id,
                    position.g_index,
                    "linked",
                    linked[position.g_position_id],
                )
            )
        elif position.g_position_id in absent:
            states.append(PositionState(position.g_position_id, position.g_index, "absent"))
        else:
            states.append(PositionState(position.g_position_id, position.g_index, "none"))
    return states


def is_complete(states: list[PositionState]) -> bool:
    """Все баллоны получили состояние — условие активности «Сохранить» (§4)."""
    return bool(states) and all(state.is_decided for state in states)


def items_by_position(session: Session, position: GPosition) -> list[Item]:
    """Детали, привязанные к позиции.

    Отметки «нет у детали» в выдачу **не попадают**: код 99 — не поисковый ключ,
    деталь по такой позиции в результат не входит (Session-03 §4).
    """
    return list(
        session.scalars(
            select(Item)
            .join(Characteristic, Characteristic.item_id == Item.item_id)
            .join(Mapping, Mapping.characteristic_id == Characteristic.characteristic_id)
            .where(Mapping.g_position_id == position.g_position_id)
            .order_by(Item.item_number)
        )
    )
