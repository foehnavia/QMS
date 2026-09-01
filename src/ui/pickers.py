"""Мелкие выборщики: «какую деталь» / «какую группу» — общие для разделов.

Выбор идёт через `kit.pick` — модальный диалог со строкой отбора (решение В-6).
Прежний `QInputDialog.getItem(..., editable=False)` давал выпадающий список без
отбора вовсе: на производственных данных `pick_item` перечисляет **все** детали,
и выбирать один каталожный номер вида `MF5-10375A-N` из трёхсот прокруткой — не
экономия, а дефект эргономики, который прогон вскрыл бы на шаге 5.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget
from sqlalchemy import Engine

from db.models import Item
from db.session import session_scope
from domain.groups import list_groups
from domain.items import groups_of

from .kit import pick


def pick_item(parent: QWidget | None, items: list[tuple[int, str]]) -> int | None:
    """Выбрать деталь из списка `(item_id, item_number)`."""
    return pick(parent, "Pick an item", "Item:", list(items))


def pick_group(parent: QWidget | None, groups: list[tuple[int, str]]) -> int | None:
    """Выбрать группу характеристик из списка `(cg_id, name)`."""
    return pick(
        parent, "Pick a characteristic group", "Characteristic group:", list(groups)
    )


def choose_cg_for_item(parent: QWidget | None, engine: Engine, item_id: int) -> int | None:
    """Какую группу открывать для привязки этой детали к канону.

    Одна своя группа — открываем её без вопросов; иначе даём выбрать. У детали
    группы может ещё не быть: привязка и заводит первую связь, поэтому в этом
    случае предлагаем любую существующую (`Item.md`, ревью S3 п. 7).

    Общая для раздела «Детали» и «ранних кнопок» формы отклонения (R2) — чтобы
    два входа в один и тот же `MappingDialog` не разъехались поведением.
    """
    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        own = [(group.cg_id, group.name) for group in groups_of(item)]
        everything = [(group.cg_id, group.name) for group in list_groups(session)]

    if len(own) == 1:
        return own[0][0]

    choices = own or everything
    if not choices:
        QMessageBox.information(
            parent,
            "No groups",
            "Create a characteristic group first — section “Characteristic groups”.",
        )
        return None
    return pick_group(parent, choices)
