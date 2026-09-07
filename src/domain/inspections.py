"""Исследование — задокументированное изучение влияния отклонения (наряд 0004).

Строка заводится **только** когда есть переиспользуемый письменный анализ
(`Inspection.md`): рутинная сверка с чертежом даёт находку и никакого
исследования. Отсюда обязательный непустой `protocol` — вся «наука» живёт в нём,
а не в полях.

`decision_insp` **независим** от `decision_dev`: исследование отвечает на вопрос
«можно ли принять это отклонение», а не «что делать с партией». `approval not
possible` на исследовании при `approved — use as is` на отклонении — валидная
комбинация, и никакой проверки, связывающей их, здесь нет и быть не должно.

Позиция трёхзначна и **необязательна** (`Inspection.md` rev 1.01, QMS-018): пусто
= «ещё не разбирали», `inconclusive` = «разобрали, однозначного ответа нет». Рядом
живёт `conclusion` — короткий вывод словами, тоже необязательный.

Привязка — к находке **и** к паре (Item, размер). Пара **выводится** через
находку (`finding → characteristic → item`); отдельных полей в схеме нет и не
нужно — зеркальный поиск строится запросом (`inspections_for`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.ids import next_insp_number
from db.models import DECISION_INSP, Characteristic, Finding, Inspection, Item, ItemRevision

from .errors import ValidationError

#: Предел короткого вывода — три-четыре предложения (`Inspection.md` rev 1.01).
CONCLUSION_LIMIT = 500


def create_inspection(
    session: Session,
    finding: Finding,
    *,
    inspection_type,
    decision_insp: str | None,
    conclusion: str | None,
    protocol: str | None,
    no_protocol: bool,
) -> Inspection:
    """Завести исследование на находке; отклонение выводится из неё."""
    if finding is None:
        raise ValidationError("An inspection is created on a finding — the finding is required.")

    _check_type(inspection_type)
    decision_insp = _check_position(decision_insp)
    conclusion = _check_conclusion(conclusion)
    protocol = _check_record(protocol, conclusion, no_protocol)

    # Номер — до создания объекта (`db.ids`): он NOT NULL, и незаполненный
    # Inspection в сессии сорвал бы автофлаш перед SELECT счётчика.
    inspection = Inspection(
        insp_number=next_insp_number(session),
        deviation=finding.deviation,
        finding=finding,
        type=inspection_type,
        decision_insp=decision_insp,
        conclusion=conclusion,
        protocol=protocol,
        no_protocol=bool(no_protocol),
    )
    session.add(inspection)
    session.flush()
    return inspection


def update_inspection(
    session: Session,
    inspection: Inspection,
    *,
    inspection_type,
    decision_insp: str | None,
    conclusion: str | None,
    protocol: str | None,
    no_protocol: bool,
) -> Inspection:
    """Заменить поля исследования **целиком** (правило S3).

    Находка не меняется: исследование адресовано конкретному размеру, перенос на
    другую находку — это другое исследование с другим номером.

    **Значений по умолчанию здесь нет и не появляется** (`CLAUDE.md` §9): поля
    заменяются целиком, и пропущенный аргумент стирал бы значение, выглядя как
    «это поле не трогаем». `decision_insp` и `conclusion` необязательны **по
    содержанию** (пусто — законное значение), но обязательны **по вызову**.
    """
    _check_type(inspection_type)
    decision_insp = _check_position(decision_insp)
    conclusion = _check_conclusion(conclusion)
    protocol = _check_record(protocol, conclusion, no_protocol)

    inspection.type = inspection_type
    inspection.decision_insp = decision_insp
    inspection.conclusion = conclusion
    inspection.protocol = protocol
    inspection.no_protocol = bool(no_protocol)
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

    Фильтруем по **обеим** половинам пары, хотя размер уже принадлежит ревизии,
    а та — детали: номер размера уникален только внутри ревизии
    (`Characteristic.md`), и «дим 12» двух разных деталей — разные размеры.
    Явная деталь в условии делает это видимым в коде и возвращает пусто, если
    пару собрали из чужих половин.

    Деталь проверяется **через ревизию размера** (QMS-017): своей колонки
    детали у размера больше нет, и путь к ней ровно один.
    """
    return list(
        session.scalars(
            select(Inspection)
            .join(Finding, Inspection.finding_id == Finding.finding_id)
            .join(
                Characteristic,
                Finding.characteristic_id == Characteristic.characteristic_id,
            )
            .join(ItemRevision, Characteristic.revision_id == ItemRevision.revision_id)
            .where(ItemRevision.item_id == item.item_id)
            .where(Characteristic.characteristic_id == characteristic.characteristic_id)
            .order_by(Inspection.insp_number)
        )
    )


def _check_type(inspection_type) -> None:
    if inspection_type is None:
        raise ValidationError(
            "Inspection type is required — pick a value from the reference list."
        )


def _check_position(decision_insp: str | None) -> str | None:
    """Позиция — пусто или одно из трёх (`Inspection.md` rev 1.01).

    Пусто нормализуется к `None`: «не заполнено» и «пустая строка из формы» —
    одно состояние, и хранить его двумя способами значило бы сравнивать позиции
    двумя способами.
    """
    cleaned = (decision_insp or "").strip()
    if not cleaned:
        return None
    if cleaned not in DECISION_INSP:
        raise ValidationError(
            f"The inspection result must be empty or one of: {', '.join(DECISION_INSP)}."
        )
    return cleaned


def _check_conclusion(conclusion: str | None) -> str | None:
    """Короткий вывод — пусто или не длиннее 500 знаков."""
    cleaned = (conclusion or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > CONCLUSION_LIMIT:
        raise ValidationError(
            f"The conclusion is a short summary of up to {CONCLUSION_LIMIT} characters "
            f"({len(cleaned)} given) — the full analysis belongs in the protocol file."
        )
    return cleaned


def _check_record(protocol: str | None, conclusion: str | None, no_protocol: bool) -> str | None:
    """Инвариант «файл ИЛИ вывод» — **человеческим текстом поверх схемы**.

    Тот же инвариант держит `CHECK` в `db.models` (`Inspection.md` rev 1.02), и
    держит его именно схема: форму обходят импортом, скриптом или следующим
    нарядом. Здесь он повторён не ради страховки, а ради **текста**: ограничение
    ловит любой путь записи и отвечает `IntegrityError`, а оператору надо сказать,
    чего именно не хватает.

    Три отказа — три разных нехватки:

    * признак снят, протокола нет → нужен файл (прежнее правило целиком);
    * признак поднят, вывода нет → вывод становится **всем содержимым** записи;
    * признак поднят, но путь введён → «файл есть, но он не нужен» смысла не имеет
      и третьим случаем не заводится.

    Существование файла по-прежнему **не проверяется** (решение 4 QMS-018).
    """
    cleaned = (protocol or "").strip()

    if not no_protocol:
        if not cleaned:
            raise ValidationError(
                "Protocol is required: an inspection is recorded only when a written, "
                "reusable analysis exists. If this verdict needs no document, tick "
                "“No protocol” and write the conclusion instead."
            )
        return cleaned

    if cleaned:
        raise ValidationError(
            "“No protocol” is set, so the protocol path must be empty — a record cannot "
            "both waive the document and point at one. Clear the path or untick the box."
        )
    if not (conclusion or "").strip():
        raise ValidationError(
            "An inspection without a protocol must carry a conclusion: it is then the "
            "whole content of the record, and a record that says nothing is invisible "
            "to the precedent search."
        )
    return None
