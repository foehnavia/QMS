"""Заведение детали и сид CG-размеров (`Item.md`, `_overview.md` §6).

При заведении детали сеются **только CG-размеры**; остальные создаются
автоматически при первом отклонении, которое на них ссылается
(`characteristics.get_or_create_characteristic`).

Принадлежность детали к CG выводится через `characteristic → mapping →
g_position → cg` — отдельной Item↔CG таблицы нет (`decisions.md`, ревью S1).
"""

from __future__ import annotations

from typing import Mapping as MappingType

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Characteristic, CharacteristicGroup, Item, Mapping

from .errors import DuplicateValue, ValidationError


def list_items(session: Session) -> list[Item]:
    return list(session.scalars(select(Item).order_by(Item.item_number)))


def create_item(
    session: Session,
    *,
    item_number: str,
    connection_type,
    size,
    item_type=None,
) -> Item:
    """Создать деталь. `connection_type`/`size` обязательны (дефолт — `General`)."""
    item_number = (item_number or "").strip()
    if not item_number:
        raise ValidationError("Item number is required.")
    if connection_type is None or size is None:
        raise ValidationError("Connection type and size class are required.")
    if session.scalar(select(Item).where(Item.item_number == item_number)):
        raise DuplicateValue(f"Item “{item_number}” already exists in the database.")

    item = Item(
        item_number=item_number,
        item_type=item_type,
        connection_type=connection_type,
        size=size,
    )
    session.add(item)
    session.flush()
    return item


def seed_cg_characteristics(
    session: Session,
    item: Item,
    group: CharacteristicGroup,
    local_numbers: MappingType[int, str],
) -> list[Characteristic]:
    """Засеять деталь размерами группы и смаппить их на её g-позиции.

    Номер размера задаётся **явно на каждую g-позицию** — он берётся с чертежа
    детали и с `g_index` совпадает редко, поэтому автоподстановка закрепляла бы
    в базе неверный номер (решение Cowork по заметке Б наряда 0002).

    Маппинг создаётся сразу — ранняя привязка к канону (R2). Геометрия остаётся
    на `g_position` и на характеристику не копируется.
    """
    numbers = dict(local_numbers or {})

    cleaned: dict[int, str] = {}
    for position in group.positions:
        local = (numbers.get(position.g_index) or "").strip()
        if not local:
            raise ValidationError(
                f"No local number given for position g{position.g_index}."
            )
        cleaned[position.g_index] = local

    if len(set(cleaned.values())) != len(cleaned):
        raise DuplicateValue("Local numbers inside one item must not repeat.")

    existing = {char.local_number for char in item.characteristics}
    clash = existing & set(cleaned.values())
    if clash:
        raise DuplicateValue(
            f"The item already has characteristics numbered: {', '.join(sorted(clash))}."
        )

    created: list[Characteristic] = []
    for position in sorted(group.positions, key=lambda p: p.g_index):
        characteristic = Characteristic(item=item, local_number=cleaned[position.g_index])
        session.add(characteristic)
        session.add(Mapping(characteristic=characteristic, g_position=position))
        created.append(characteristic)
    session.flush()
    return created


def groups_of(item: Item) -> list[CharacteristicGroup]:
    """Группы детали — выводятся из маппингов её размеров, не из своей таблицы."""
    groups: dict[int, CharacteristicGroup] = {}
    for characteristic in item.characteristics:
        mapping = characteristic.mapping
        if mapping is not None and mapping.g_position is not None:
            group = mapping.g_position.cg
            groups[group.cg_id] = group
    return sorted(groups.values(), key=lambda group: group.name)
