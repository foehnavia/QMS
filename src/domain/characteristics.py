"""Автосоздание не-CG размера (заметка Г наряда 0002).

Массовый случай: деталь есть, размера ещё нет. Тогда характеристика создаётся
**без формы, без CG и без маппинга** (`_overview.md` §6, `Characteristic.md`) —
оператора этим не беспокоят.

Боевая точка вызова — форма ввода отклонения (S4).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Characteristic, Item

from .errors import ValidationError


def get_or_create_characteristic(
    session: Session, item: Item, local_number: str
) -> tuple[Characteristic, bool]:
    """Вернуть размер `(item, local_number)`, создав при отсутствии.

    Возвращает `(характеристика, создана_ли)`. Идемпотентно: повторный вызов
    дублей не плодит (подстраховано `UNIQUE(item_id, local_number)`).
    """
    local_number = (local_number or "").strip()
    if not local_number:
        raise ValidationError("Local number is required.")

    existing = session.scalar(
        select(Characteristic)
        .where(Characteristic.item_id == item.item_id)
        .where(Characteristic.local_number == local_number)
    )
    if existing is not None:
        return existing, False

    characteristic = Characteristic(item=item, local_number=local_number)
    session.add(characteristic)
    session.flush()
    return characteristic, True
