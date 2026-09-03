"""Заведение детали (`Item.md`, `_overview.md` §6).

Размеры детали при заведении **не сеются**: CG-размеры создаёт привязка к
канону (`mappings.bind` → `get_or_create_characteristic`), остальные — первое
отклонение, которое на них ссылается. Прежний `seed_cg_characteristics` был
вторым способом создать те же строки и требовал вводить номера **вслепую**, без
чертежа группы; он удалён нарядом 0018 (находка №13 прогона QMS-016).

Принадлежность детали к CG выводится через `characteristic → mapping →
g_position → cg` — отдельной Item↔CG таблицы нет (`decisions.md`, ревью S1).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Item

from .errors import DuplicateValue, ValidationError, ValueInUse


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


def update_item(
    session: Session,
    item: Item,
    *,
    item_number: str,
    connection_type,
    size,
    item_type=None,
) -> Item:
    """Править классификаторы детали и её номер.

    Номер правится **только здесь**, и вот почему функция вообще появилась:
    форма детали умела лишь создавать, поэтому опечатка в реальном каталожном
    номере лечилась перезаливкой базы. На прогоне это остановка на шаге 5
    (ревью наряда 0012, В-2).

    Гард уникальности тот же, что при создании, и проверяется он **против
    других** записей: сохранение детали с её собственным номером — не дубликат.

    Значений по умолчанию нет (конвенция `CLAUDE.md` §9): пропущенный аргумент
    стирал бы поле, выглядя как «это не трогаем». `item_type=None` — законное
    значение «тип не задан», а не пропуск.

    Что **не** меняется: размеры детали и их привязки. Номер детали — её имя,
    а не идентичность; идентичность держит `item_id`, на который ссылаются
    характеристики, и переименование их не задевает.
    """
    item_number = (item_number or "").strip()
    if not item_number:
        raise ValidationError("Item number is required.")
    if connection_type is None or size is None:
        raise ValidationError("Connection type and size class are required.")

    clash = session.scalar(
        select(Item).where(Item.item_number == item_number, Item.item_id != item.item_id)
    )
    if clash:
        raise DuplicateValue(f"Item “{item_number}” already exists in the database.")

    item.item_number = item_number
    item.item_type = item_type
    item.connection_type = connection_type
    item.size = size
    session.flush()
    return item


def discard_item(session: Session, item: Item) -> None:
    """Снять только что заведённую деталь вместе со всем, что за ней записано.

    Нужна одному сценарию — отказу от привязки на заведении (наряд 0018 §3.3).
    Деталь с назначенной группой не существует в базе с неполной привязкой, а
    диалог привязки пишет каждое действие сразу (ратификация S3, менять её
    наряд не разрешает). Поэтому «не заводить деталь» достигается не отложенной
    записью, а удалением записанного за этот сеанс.

    Каскады модели снимают всё связанное: размеры детали, их маппинги и отметки
    «нет у детали» (`Item.characteristics` и `Item.absent_positions` —
    `delete-orphan`, `Characteristic.mapping` — тоже).

    **Гард на чужие записи.** Функция откатывает только что созданное и не
    смеет тронуть деталь, на которую уже сослалась работа цеха: отклонение или
    находка. Это же условие держит дорогу открытой для Q-15 (перепривязка
    существующей детали со снимком состояния): её механика будет своя, а эта
    остаётся узкой.
    """
    if item.deviations:
        raise ValueInUse(
            f"Item “{item.item_number}” has {len(item.deviations)} deviation(s) — "
            "it is not a freshly created item and will not be discarded."
        )
    for characteristic in item.characteristics:
        if characteristic.findings:
            raise ValueInUse(
                f"Characteristic no. {characteristic.local_number} of item "
                f"“{item.item_number}” is referenced by findings — "
                "the item will not be discarded."
            )

    session.delete(item)
    session.flush()


def groups_of(item: Item) -> list[CharacteristicGroup]:
    """Группы детали — выводятся из маппингов её размеров, не из своей таблицы."""
    groups: dict[int, CharacteristicGroup] = {}
    for characteristic in item.characteristics:
        mapping = characteristic.mapping
        if mapping is not None and mapping.g_position is not None:
            group = mapping.g_position.cg
            groups[group.cg_id] = group
    return sorted(groups.values(), key=lambda group: group.name)
