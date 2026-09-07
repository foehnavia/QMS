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

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import (
    OUTCOME,
    Characteristic,
    Deviation,
    Direction,
    Finding,
    GPosition,
    Inspection,
    Mapping,
    RefDeviationType,
    RefInspectionType,
    RefZone,
)

from .errors import InvariantViolation, ValidationError, ValueInUse
# Подпись «не привязан» берётся из поиска, а не заводится второй раз:
# одно значение — одно определение (`Search.md` v1.04).
from .precedents import CANON_UNBOUND


def ensure_finding_target(deviation: Deviation, characteristic: Characteristic) -> None:
    """Проверить, что размер принадлежит **ревизии** отклонения.

    Гард ужесточён с детали до ревизии (QMS-017): совпадения детали больше не
    достаточно. Размер `12` ревизии `A` и размер `12` ревизии `B` — две разные
    записи одной детали, и находка, севшая не на ту, читалась бы по чужому
    чертежу. Проверка ревизии проверяет и деталь: ревизия принадлежит одной
    детали, поэтому отдельного сравнения `item_id` не нужно.
    """
    if characteristic.revision_id != deviation.revision_id:
        if characteristic.revision.item_id != deviation.item_id:
            raise InvariantViolation(
                f"Characteristic no. {characteristic.local_number} belongs to another item — "
                f"it cannot carry a finding of deviation {deviation.dev_number}."
            )
        raise InvariantViolation(
            f"Characteristic no. {characteristic.local_number} belongs to revision "
            f"“{characteristic.revision.designation}”, while deviation "
            f"{deviation.dev_number} is raised against “{deviation.revision.designation}”."
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
    outcome: str | None = None,
) -> Finding:
    """Создать находку, проверив инвариант принадлежности и знак направления.

    `outcome` по умолчанию пуст: находки заводятся при регистрации, а суждение по
    размеру приходит позже (`Finding.md` rev 1.01). Это **не** послабление правила
    §9 о `update_*` — там умолчаний нет и не появляется; здесь умолчание выражает
    нормальное состояние новой записи, а не «поле не трогаем».
    """
    ensure_finding_target(deviation, characteristic)
    if direction not in Direction.ALL:
        raise ValidationError(
            f"Direction must be {Direction.PLUS} or {Direction.MINUS}."
        )
    outcome = check_outcome(outcome)

    finding = Finding(
        deviation=deviation,
        characteristic=characteristic,
        direction=direction,
        value=value,
        dimension_point=dimension_point,
        comment=comment,
        zone=zone,
        deviation_type=deviation_type,
        outcome=outcome,
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
    outcome: str | None,
) -> Finding:
    """Заменить измерительные поля находки **целиком** (правило S3).

    Значений по умолчанию нет намеренно: функция присваивает все поля
    безусловно, поэтому пропущенный аргумент стирал бы значение, а выглядел бы
    как «это поле не трогаем».

    Размер и отклонение не меняются: смена размера — это другая находка, а
    перенос в другое отклонение сломал бы инвариант принадлежности.

    **Точка 2 связывающего инварианта** (`Deviation.md` rev 1.03): исход нельзя
    перевести в `not_permitted`, пока отклонение стоит `approved`. Молча снять
    чужое решение нельзя — оно ушло в документ; отказ говорит, что сделать
    сначала.
    """
    if direction not in Direction.ALL:
        raise ValidationError(
            f"Direction must be {Direction.PLUS} or {Direction.MINUS}."
        )
    outcome = check_outcome(outcome)
    _refuse_to_void_a_decision(finding, outcome)

    finding.direction = direction
    finding.value = value
    finding.dimension_point = dimension_point
    finding.comment = comment
    finding.zone = zone
    finding.deviation_type = deviation_type
    finding.outcome = outcome
    session.flush()
    return finding


def check_outcome(outcome: str | None) -> str | None:
    """Исход находки — пусто или одно из двух (`Finding.md` rev 1.01).

    Пусто нормализуется к `None`: «не решено» и «пустая строка из формы» — одно
    состояние, и хранить его двумя способами значило бы сравнивать исходы двумя
    способами (тот же довод, что у позиции исследования в QMS-018).
    """
    cleaned = (outcome or "").strip()
    if not cleaned:
        return None
    if cleaned not in OUTCOME:
        raise ValidationError(
            f"The finding outcome must be empty or one of: {', '.join(OUTCOME)}."
        )
    return cleaned


def _refuse_to_void_a_decision(finding: Finding, outcome: str | None) -> None:
    """Точка 2 инварианта: `not_permitted` под одобренным отклонением — отказ.

    Проверяется **переход**, а не состояние: находка, уже стоящая
    `not_permitted` под `approved`, могла попасть туда только в обход домена, и
    запирать её правку значило бы запирать единственный выход из этого положения.
    """
    if outcome != "not_permitted":
        return
    if finding.outcome == "not_permitted":
        return
    deviation = finding.deviation
    if deviation is not None and deviation.decision_dev == "approved":
        raise InvariantViolation(
            f"Deviation {deviation.dev_number} stands “approved — use as is”, and that "
            "outcome requires every finding to be permitted. Withdraw the decision on "
            "the deviation first, then mark this dimension as not permitted."
        )


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
            f"This is the only finding of deviation {deviation.dev_number}. "
            "A deviation must keep at least one — delete the deviation as a whole."
        )

    used = inspection_count(session, finding)
    if used:
        raise ValueInUse(
            f"The finding on characteristic no. {finding.characteristic.local_number} "
            f"carries inspections: {used} — delete them first."
        )

    # Через коллекцию владельца (`delete-orphan`): `session.delete` оставил бы
    # `deviation.findings` со ссылкой на удалённую строку — граф в памяти
    # разошёлся бы с базой (урок наряда 0003).
    deviation.findings.remove(finding)
    session.flush()


# --- Уровень находки в списке отклонений (наряд 0028, QMS-018) -------------------


@dataclass(frozen=True)
class FindingRow:
    """Находка так, как её показывают пилюля свёрнутой строки и панель раскрытия.

    Отдельно от `Finding` потому, что экран рисует не запись, а **сводку**:
    подпись канона живёт в другой таблице, а число исследований — агрегат.
    Тащить ради них ORM-объект значило бы ходить в базу на каждую строку.
    """

    finding_id: int
    deviation_id: int
    #: Местный номер размера на чертеже — то, что оператор читает как «дим 19».
    local_number: str
    #: `gN` либо `CANON_UNBOUND`. Третьего состояния, «размер ещё не заведён»,
    #: здесь быть не может: находка без размера не существует.
    canon: str
    direction: str
    value: float | None
    zone: str | None
    deviation_type: str | None
    #: Сколько исследований висит на находке. Признак наличия, **не суждение**:
    #: значок мензурки в пилюле ставится по нему и от исхода не зависит.
    inspections: int
    #: Исход находки: `permitted` · `not_permitted` · `None` («ещё не решали»).
    #: Именно он показывается пилюлей и колонкой раскрытия (QMS-025).
    outcome: str | None


def findings_for_deviations(
    session: Session, deviation_ids: Sequence[int]
) -> dict[int, list[FindingRow]]:
    """Находки нескольких отклонений — **один** запрос на весь экран.

    Решение 7 QMS-018: пакетных запросов на экран два — отклонения и находки
    всех видимых строк вместе с числом исследований у каждой находки. Запрет,
    который за этим стоит, — «ни одного запроса на строку и ни одного на
    находку». Поэтому подпись канона и счётчик исследований приезжают **этим
    же** запросом, левыми соединениями, а не вызовами `canon_labels` и
    `inspection_counts`: те, при всей своей пакетности, дали бы третий и
    четвёртый запрос.

    Ключ — `deviation_id`; отклонение без находок в ответе есть, с **пустым**
    списком, а не пропуском: экран обязан отличать «находок нет» от «не спросили».
    """
    ids = [int(value) for value in deviation_ids]
    if not ids:
        return {}

    counts = (
        select(Inspection.finding_id.label("finding_id"), func.count().label("n"))
        .group_by(Inspection.finding_id)
        .subquery()
    )

    query = (
        select(
            Finding.finding_id,
            Finding.deviation_id,
            Characteristic.local_number,
            GPosition.g_index,
            Finding.direction,
            Finding.value,
            RefZone.name,
            RefDeviationType.name,
            func.coalesce(counts.c.n, 0),
            Finding.outcome,
        )
        .join(Characteristic, Finding.characteristic_id == Characteristic.characteristic_id)
        .outerjoin(Mapping, Mapping.characteristic_id == Characteristic.characteristic_id)
        .outerjoin(GPosition, Mapping.g_position_id == GPosition.g_position_id)
        .outerjoin(RefZone, Finding.zone_id == RefZone.zone_id)
        .outerjoin(
            RefDeviationType,
            Finding.deviation_type_id == RefDeviationType.deviation_type_id,
        )
        .outerjoin(counts, counts.c.finding_id == Finding.finding_id)
        .where(Finding.deviation_id.in_(ids))
        # Порядок здесь только **устойчивый**, а не читательский: номер размера
        # строка, и «10» текстом встаёт перед «9». Числовой ключ живёт в
        # `ui.common.dimension_sort_key`, и сортирует экран — домену незачем
        # заводить его второй раз ради порядка, который нужен одному экрану.
        .order_by(Finding.deviation_id, Finding.finding_id)
    )

    grouped: dict[int, list[FindingRow]] = {key: [] for key in ids}
    for row in session.execute(query):
        grouped[row[1]].append(
            FindingRow(
                finding_id=row[0],
                deviation_id=row[1],
                local_number=row[2],
                canon=CANON_UNBOUND if row[3] is None else f"g{row[3]}",
                direction=row[4],
                value=row[5],
                zone=row[6],
                deviation_type=row[7],
                inspections=row[8],
                outcome=row[9],
            )
        )
    return grouped


# --- Уровень исследования в панели раскрытия (наряд 0028 §4.2, §5.3) --------------


@dataclass(frozen=True)
class InspectionRow:
    """Исследование так, как его показывает ячейка `Inspections` панели.

    В ячейке — **тип**; короткий вывод в 340 px не помещается и живёт в подсказке
    (§4.2 наряда `0028`), поэтому он здесь есть, но отдельной колонкой не
    становится. Позиции у исследования больше нет вовсе (`Inspection.md` rev 1.03).
    """

    inspection_id: int
    finding_id: int
    #: Вид исследования из справочника (`Solidworks assembly`, …).
    type_name: str
    conclusion: str | None


def inspections_of_deviation(
    session: Session, deviation_id: int
) -> dict[int, list[InspectionRow]]:
    """Исследования одного отклонения, разложенные по находкам — **один** запрос.

    Ленивый: зовётся на **раскрытие** записи, а не на отрисовку экрана
    (решение 7 QMS-018). Свёрнутой строке от исследования нужен один признак —
    «есть или нет», — и он уже приехал счётчиком в `FindingRow.inspections`.

    Ключ — `finding_id`; находки без исследований в ответе **нет**: пустое
    состояние ячейки рисует экран, и словарь, набитый пустыми списками, только
    заставил бы его различать два одинаковых ответа.
    """
    query = (
        select(
            Inspection.inspection_id,
            Inspection.finding_id,
            RefInspectionType.name,
            Inspection.conclusion,
        )
        .join(
            RefInspectionType,
            Inspection.type_id == RefInspectionType.inspection_type_id,
        )
        .where(Inspection.deviation_id == deviation_id)
        .order_by(Inspection.finding_id, Inspection.insp_number)
    )

    grouped: dict[int, list[InspectionRow]] = {}
    for row in session.execute(query):
        grouped.setdefault(row[1], []).append(
            InspectionRow(
                inspection_id=row[0],
                finding_id=row[1],
                type_name=row[2],
                conclusion=row[3],
            )
        )
    return grouped
