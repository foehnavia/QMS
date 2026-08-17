"""Находка — гард инварианта «находка ∈ деталь отклонения» и правка (0002, 0004).

Схемой в SQLite инвариант не выражается: FK ведут от находки к отклонению и к
характеристике по отдельности, а их согласованность — межтабличное правило.
Композитный FK и дублирование `item_id` в `finding` отвергнуты на ревью S1
(денормализация + правка §5), поэтому проверка живёт здесь.

`make_finding` — **единственная** точка создания находки: UI обязан звать её, а
не конструировать `Finding` напрямую. Гард держится AST-проверкой по `src/ui/**`
(критерий приёмки 3 наряда 0004).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Characteristic, Deviation, Direction, Finding, Inspection

from .errors import InvariantViolation, ValidationError, ValueInUse


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


def update_finding(
    session: Session,
    finding: Finding,
    *,
    direction: str,
    value: float | None,
    dimension_point: int | None,
    comment: str | None,
    zone,
    deviation_type,
) -> Finding:
    """Заменить измерительные поля находки **целиком** (правило S3).

    Значений по умолчанию нет намеренно: функция присваивает все поля
    безусловно, поэтому пропущенный аргумент стирал бы значение, а выглядел бы
    как «это поле не трогаем».

    Размер и отклонение не меняются: смена размера — это другая находка, а
    перенос в другое отклонение сломал бы инвариант принадлежности.
    """
    if direction not in Direction.ALL:
        raise ValidationError(
            f"Направление должно быть {Direction.PLUS} или {Direction.MINUS}."
        )

    finding.direction = direction
    finding.value = value
    finding.dimension_point = dimension_point
    finding.comment = comment
    finding.zone = zone
    finding.deviation_type = deviation_type
    session.flush()
    return finding


def inspection_count(session: Session, finding: Finding) -> int:
    """Сколько исследований висит на находке (одна находка — один вопрос)."""
    return session.scalar(
        select(func.count())
        .select_from(Inspection)
        .where(Inspection.finding_id == finding.finding_id)
    )


def inspection_counts(session: Session, findings) -> dict[int, int]:
    """То же по набору находок — **один** запрос на набор.

    Пакетный близнец `inspection_count`: таблица находок рисует счётчик в каждой
    строке, и построчный вопрос превращал бы её в `N+1` (наряд 0005, критерий 8).
    Находки без исследований в результате есть — со значением `0`, а не пропуском.
    """
    ids = [finding.finding_id for finding in findings if finding is not None]
    if not ids:
        return {}

    counted = dict(
        session.execute(
            select(Inspection.finding_id, func.count())
            .where(Inspection.finding_id.in_(ids))
            .group_by(Inspection.finding_id)
        ).all()
    )
    return {finding_id: counted.get(finding_id, 0) for finding_id in ids}


def remove_finding(session: Session, finding: Finding) -> None:
    """Удалить находку. Две блокировки, обе — инварианты канона.

    * **Последняя не удаляется:** у отклонения находок `1..N` (`Deviation.md`).
      Отклонение без размера невидимо для поиска прецедентов, то есть бесполезно
      — удалять надо отклонение целиком, а не выхолащивать его.
    * **Находка с исследованием не удаляется:** исследование привязано к ней и к
      паре (Item, размер) (`Inspection.md`), без находки оно теряет адрес.
    """
    deviation = finding.deviation
    if len(deviation.findings) <= 1:
        raise InvariantViolation(
            f"Это единственная находка отклонения {deviation.dev_number}. "
            "У отклонения должна остаться хотя бы одна — удалите отклонение целиком."
        )

    used = inspection_count(session, finding)
    if used:
        raise ValueInUse(
            f"На находке по размеру №{finding.characteristic.local_number} "
            f"висит исследований: {used} — сначала удалите их."
        )

    # Через коллекцию владельца (`delete-orphan`): `session.delete` оставил бы
    # `deviation.findings` со ссылкой на удалённую строку — граф в памяти
    # разошёлся бы с базой (урок наряда 0003).
    deviation.findings.remove(finding)
    session.flush()
