"""Гард инварианта «находка ∈ деталь отклонения» (наряд 0002, п. 7).

Схемой в SQLite это не выражается: FK ведут от находки к отклонению и к
характеристике по отдельности, а их согласованность — межтабличное правило.
Композитный FK и дублирование `item_id` в `finding` отвергнуты на ревью S1
(денормализация + правка §5), поэтому проверка живёт здесь.

UI находок появляется в S4 — он обязан создавать находки через `make_finding`,
а не конструировать `Finding` напрямую.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Characteristic, Deviation, Direction, Finding

from .errors import InvariantViolation, ValidationError


def ensure_finding_target(deviation: Deviation, characteristic: Characteristic) -> None:
    """Проверить, что размер принадлежит детали отклонения."""
    if characteristic.item_id != deviation.item_id:
        raise InvariantViolation(
            f"Размер №{characteristic.local_number} принадлежит другой детали — "
            f"находку к отклонению {deviation.dev_number} привязать нельзя."
        )


def make_finding(
    session: Session,
    deviation: Deviation,
    characteristic: Characteristic,
    *,
    direction: str,
    value: float | None = None,
    dimension_point: int | None = None,
    comment: str | None = None,
    zone=None,
    deviation_type=None,
) -> Finding:
    """Создать находку, проверив инвариант принадлежности и знак направления."""
    ensure_finding_target(deviation, characteristic)
    if direction not in Direction.ALL:
        raise ValidationError(
            f"Направление должно быть {Direction.PLUS} или {Direction.MINUS}."
        )

    finding = Finding(
        deviation=deviation,
        characteristic=characteristic,
        direction=direction,
        value=value,
        dimension_point=dimension_point,
        comment=comment,
        zone=zone,
        deviation_type=deviation_type,
    )
    session.add(finding)
    session.flush()
    return finding
