"""CharacteristicGroup / g-позиции — канон-слой; создание CG «на лету» (R3).

Номинал и допуск живут **на g-позиции** и берутся с чертежа; на характеристику
детали они не копируются (`CharacteristicGroup.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CharacteristicGroup, GPosition

from .errors import DuplicateValue, ValidationError


@dataclass(frozen=True)
class GPositionSpec:
    """Строка ввода g-позиции: индекс + геометрия с чертежа."""

    g_index: int
    nominal: float | None = None
    tol_plus: float | None = None
    tol_minus: float | None = None


def list_groups(session: Session) -> list[CharacteristicGroup]:
    return list(session.scalars(select(CharacteristicGroup).order_by(CharacteristicGroup.name)))


def create_group(
    session: Session, name: str, positions: Sequence[GPositionSpec]
) -> CharacteristicGroup:
    """Создать CG с набором g-позиций (R3 — можно прямо при заведении детали)."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Название группы не может быть пустым.")
    if not positions:
        raise ValidationError("У группы должна быть хотя бы одна g-позиция.")

    indexes = [spec.g_index for spec in positions]
    if any(index < 1 for index in indexes):
        raise ValidationError("Индекс g-позиции должен быть положительным.")
    if len(set(indexes)) != len(indexes):
        raise DuplicateValue("Индексы g-позиций внутри группы не должны повторяться.")
    if session.scalar(select(CharacteristicGroup).where(CharacteristicGroup.name == name)):
        raise DuplicateValue(f"Группа «{name}» уже есть.")

    group = CharacteristicGroup(name=name)
    group.positions = [
        GPosition(
            g_index=spec.g_index,
            nominal=spec.nominal,
            tol_plus=spec.tol_plus,
            tol_minus=spec.tol_minus,
        )
        for spec in sorted(positions, key=lambda spec: spec.g_index)
    ]
    session.add(group)
    session.flush()
    return group
