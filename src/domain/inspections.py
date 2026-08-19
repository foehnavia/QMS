"""Исследование — задокументированное изучение влияния отклонения (наряд 0004).

Строка заводится **только** когда есть переиспользуемый письменный анализ
(`Inspection.md`): рутинная сверка с чертежом даёт находку и никакого
исследования. Отсюда обязательный непустой `protocol` — вся «наука» живёт в нём,
а не в полях.

`decision_insp` **независим** от `decision_dev`: исследование отвечает на вопрос
«можно ли принять это отклонение», а не «что делать с партией». Одобренное
исследование при отклонённом отклонении — валидная комбинация, и никакой
проверки, связывающей их, здесь нет и быть не должно.

Привязка — к находке **и** к паре (Item, размер). Пара **выводится** через
находку (`finding → characteristic → item`); отдельных полей в схеме нет и не
нужно — зеркальный поиск строится запросом (`inspections_for`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.ids import next_insp_number
from db.models import DECISION_INSP, Characteristic, Finding, Inspection, Item

from .errors import ValidationError


def create_inspection(
    session: Session,
    finding: Finding,
    *,
    inspection_type,
    decision_insp: str,
    protocol: str,
) -> Inspection:
    """Завести исследование на находке; отклонение выводится из неё."""
    if finding is None:
        raise ValidationError("An inspection is created on a finding — the finding is required.")

    _check_type(inspection_type)
    _check_verdict(decision_insp)
    protocol = _check_protocol(protocol)

    # Номер — до создания объекта (`db.ids`): он NOT NULL, и незаполненный
    # Inspection в сессии сорвал бы автофлаш перед SELECT счётчика.
    inspection = Inspection(
        insp_number=next_insp_number(session),
        deviation=finding.deviation,
        finding=finding,
        type=inspection_type,
        decision_insp=decision_insp,
        protocol=protocol,
    )
    session.add(inspection)
    session.flush()
    return inspection


def update_inspection(
    session: Session,
    inspection: Inspection,
    *,
    inspection_type,
    decision_insp: str,
    protocol: str,
) -> Inspection:
    """Заменить поля исследования **целиком** (правило S3).

    Находка не меняется: исследование адресовано конкретному размеру, перенос на
    другую находку — это другое исследование с другим номером.
    """
    _check_type(inspection_type)
    _check_verdict(decision_insp)
    protocol = _check_protocol(protocol)

    inspection.type = inspection_type
    inspection.decision_insp = decision_insp
    inspection.protocol = protocol
    session.flush()
    return inspection


def remove_inspection(session: Session, inspection: Inspection) -> None:
    """Удалить исследование.

    Через коллекцию отклонения (`delete-orphan`) — иначе `deviation.inspections`
    и `finding.inspections` остались бы со ссылкой на удалённую строку.
    """
    inspection.deviation.inspections.remove(inspection)
    session.flush()


def inspections_for(
    session: Session, item: Item, characteristic: Characteristic
) -> list[Inspection]:
    """Зеркальный поиск: все исследования по паре (Item, размер).

    Фильтруем по **обеим** половинам пары, хотя размер уже принадлежит детали:
    номер размера уникален только внутри детали (`Characteristic.md`), и «дим 12»
    двух разных деталей — разные размеры. Явная деталь в условии делает это
    видимым в коде и возвращает пусто, если пару собрали из чужих половин.
    """
    return list(
        session.scalars(
            select(Inspection)
            .join(Finding, Inspection.finding_id == Finding.finding_id)
            .join(
                Characteristic,
                Finding.characteristic_id == Characteristic.characteristic_id,
            )
            .where(Characteristic.item_id == item.item_id)
            .where(Characteristic.characteristic_id == characteristic.characteristic_id)
            .order_by(Inspection.insp_number)
        )
    )


def _check_type(inspection_type) -> None:
    if inspection_type is None:
        raise ValidationError(
            "Inspection type is required — pick a value from the reference list."
        )


def _check_verdict(decision_insp: str) -> None:
    if decision_insp not in DECISION_INSP:
        raise ValidationError(
            f"The inspection verdict must be one of: {', '.join(DECISION_INSP)}."
        )


def _check_protocol(protocol: str) -> str:
    cleaned = (protocol or "").strip()
    if not cleaned:
        raise ValidationError(
            "Protocol is required: an inspection is recorded only when a written, "
            "reusable analysis exists."
        )
    return cleaned
