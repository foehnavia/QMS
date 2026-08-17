"""Поиск прецедентов — главный deliverable Этапа 1 (наряд 0005).

Инженер, заведя отклонение, должен сразу увидеть: случалось ли такое раньше, что
тогда решили и как обосновали (`DeviationCard.md`, шаг 6 процесса). Отсюда два
уровня (`Search.md`):

* **L1 — точный.** По паре «деталь + размер» (`precedents_same_dimension`) и, если
  размер привязан к канону, по g-позиции — она же ловит **другие детали** в том же
  конструктивном месте (`precedents_same_position`).
* **L2 — описательный.** По зоне и типу отклонения (`precedents_descriptive`),
  когда точных совпадений нет.

Три правила, общие для всех выдач:

1. **Единица выдачи — отклонение целиком**, даже если совпал один размер
   (`Search.md`). Строка выдачи несёт и поля находки, по которой совпало, и
   решение с обоснованием — ради них прецедент и смотрят.
2. **Только решённые отклонения.** Нерешённое подсказать нечего: прецедент
   существует ради готового решения и обоснования (решение Cowork 3).
3. **Код 99 — не поисковый ключ.** Деталь, у которой позиция помечена «нет у
   детали», в выдачу по позиции не попадает: `item_position_absent` в запросах
   не участвует вовсе (`CharacteristicGroup.md`; так же устроен
   `mappings.items_by_position`).

Схема не менялась: всё выражается запросами поверх rev 0.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from typing import Iterable, Literal, Sequence

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from db.models import (
    Characteristic,
    CharacteristicGroup,
    Deviation,
    Finding,
    GPosition,
    Inspection,
    Item,
    Mapping,
    RefDeviationType,
    RefZone,
)

#: Чем совпал прецедент — читается в UI как заголовок секции или колонка.
Match = Literal["dimension", "position", "zone+type", "zone", "type"]

#: Состояния размера в каноне. Достижимых ровно три, и «нет у детали (99)» среди
#: них нет по построению: код 99 отмечает g-позицию, которой у детали **нет**, а
#: находка всегда про размер, который у детали **есть** (ратифицировано в S4).
CANON_UNBOUND = "не привязан"
CANON_NEW = "размер ещё не заведён"


@dataclass(frozen=True)
class PrecedentRow:
    """Строка выдачи прецедентов — всё, что рисует таблица, одним запросом.

    Образец — `deviations.DeviationRow`: счётчик исследований считается
    агрегатом, а не обходом коллекций, иначе список прецедентов упирается в
    `N+1` ровно там, где строк больше всего.
    """

    deviation_id: int
    dev_number: str
    date: date_type
    item_id: int
    item_number: str
    wo: str
    quantity: int
    local_number: str
    g_label: str | None
    direction: str
    value: float | None
    dimension_point: int | None
    zone: str | None
    deviation_type: str | None
    decision: str
    explanation: str
    decision_date: datetime | None
    inspection_count: int
    match: Match


def _inspection_counts():
    """Подзапрос «сколько исследований на находке»."""
    return (
        select(Inspection.finding_id.label("finding_id"), func.count().label("n"))
        .group_by(Inspection.finding_id)
        .subquery()
    )


def _base_query():
    """Один запрос на всю строку: находка + отклонение + деталь + канон + метки.

    Канон, зона, тип и счётчик исследований подтягиваются **внешними**
    соединениями: находка без привязки, без зоны и без исследований — штатное
    состояние, а не отсутствие строки.
    """
    inspections = _inspection_counts()
    query = (
        select(
            Deviation.deviation_id,
            Deviation.dev_number,
            Deviation.date,
            Item.item_id,
            Item.item_number,
            Deviation.wo,
            Deviation.quantity,
            Characteristic.local_number,
            CharacteristicGroup.name.label("cg_name"),
            GPosition.g_index,
            Finding.direction,
            Finding.value,
            Finding.dimension_point,
            RefZone.name.label("zone_name"),
            RefDeviationType.name.label("type_name"),
            Finding.zone_id,
            Finding.deviation_type_id,
            Deviation.decision_dev,
            Deviation.explanation,
            Deviation.decision_date,
            func.coalesce(inspections.c.n, 0).label("inspections"),
        )
        .select_from(Finding)
        .join(Deviation, Finding.deviation_id == Deviation.deviation_id)
        .join(Item, Deviation.item_id == Item.item_id)
        .join(Characteristic, Finding.characteristic_id == Characteristic.characteristic_id)
        .outerjoin(Mapping, Mapping.characteristic_id == Characteristic.characteristic_id)
        .outerjoin(GPosition, Mapping.g_position_id == GPosition.g_position_id)
        .outerjoin(CharacteristicGroup, GPosition.cg_id == CharacteristicGroup.cg_id)
        .outerjoin(RefZone, Finding.zone_id == RefZone.zone_id)
        .outerjoin(
            RefDeviationType,
            Finding.deviation_type_id == RefDeviationType.deviation_type_id,
        )
        .outerjoin(inspections, inspections.c.finding_id == Finding.finding_id)
        # Правило 2: прецедент без решения ничего не подсказывает.
        .where(Deviation.decision_dev.is_not(None))
    )
    return query, inspections


def _row(record, match: Match) -> PrecedentRow:
    g_label = (
        f"{record.cg_name} · g{record.g_index}"
        if record.cg_name is not None and record.g_index is not None
        else None
    )
    return PrecedentRow(
        deviation_id=record.deviation_id,
        dev_number=record.dev_number,
        date=record.date,
        item_id=record.item_id,
        item_number=record.item_number,
        wo=record.wo,
        quantity=record.quantity,
        local_number=record.local_number,
        g_label=g_label,
        direction=record.direction,
        value=record.value,
        dimension_point=record.dimension_point,
        zone=record.zone_name,
        deviation_type=record.type_name,
        decision=record.decision_dev,
        explanation=record.explanation,
        decision_date=record.decision_date,
        inspection_count=record.inspections,
        match=match,
    )


def _fresh_first(query):
    """Свежие сверху; номер — устойчивый доразбор внутри одного дня."""
    return query.order_by(Deviation.date.desc(), Deviation.dev_number.desc())


def _exclude(query, *, exclude_deviation=None, exclude_characteristic=None):
    if exclude_deviation is not None:
        query = query.where(Deviation.deviation_id != exclude_deviation.deviation_id)
    if exclude_characteristic is not None:
        query = query.where(
            Finding.characteristic_id != exclude_characteristic.characteristic_id
        )
    return query


# --- L1 — точный поиск -----------------------------------------------------------


def precedents_same_dimension(
    session: Session,
    characteristic: Characteristic,
    *,
    exclude_deviation: Deviation | None = None,
) -> list[PrecedentRow]:
    """L1a — та же деталь, тот же номер размера.

    Самое сильное совпадение: тот же физический размер той же детали.
    """
    query, _ = _base_query()
    query = query.where(Finding.characteristic_id == characteristic.characteristic_id)
    query = _exclude(query, exclude_deviation=exclude_deviation)
    return [_row(record, "dimension") for record in session.execute(_fresh_first(query))]


def precedents_same_position(
    session: Session,
    characteristic: Characteristic,
    *,
    exclude_deviation: Deviation | None = None,
) -> list[PrecedentRow]:
    """L1b — **другие детали**, привязанные к той же g-позиции.

    Ради этого канон и заведён: одинаковое конструктивное место у разных деталей
    сравнимо, хотя локальные номера размеров у них разные
    (`CharacteristicGroup.md`).

    Своя деталь исключена — она уже показана в L1a, и дублировать её значит
    дважды предъявить один прецедент. Если размер к канону не привязан, выдача
    пуста **без ошибки**: это штатное состояние, о котором UI говорит словами.
    """
    mapping = characteristic.mapping
    if mapping is None:
        return []

    query, _ = _base_query()
    query = (
        query.where(Mapping.g_position_id == mapping.g_position_id)
        .where(Characteristic.item_id != characteristic.item_id)
    )
    query = _exclude(query, exclude_deviation=exclude_deviation)
    return [_row(record, "position") for record in session.execute(_fresh_first(query))]


# --- L2 — описательный поиск ------------------------------------------------------


def precedents_descriptive(
    session: Session,
    *,
    zone=None,
    deviation_type=None,
    exclude_deviation: Deviation | None = None,
    exclude_characteristic: Characteristic | None = None,
) -> list[PrecedentRow]:
    """L2 — похожие случаи по зоне **или** типу отклонения.

    Условие намеренно `OR`, а не `AND`: L2 работает там, где точных совпадений
    нет, и сужать его до полного совпадения обеих меток значит выключить.
    Совпавшие по обоим стоят выше — сила совпадения видна порядком.

    `exclude_characteristic` убирает из выдачи тот размер, что уже показан в L1:
    вкладки не должны повторять друг друга.
    """
    if zone is None and deviation_type is None:
        # Ни одной метки — искать не по чему. Пусто, а не «всё подряд».
        return []

    conditions = []
    if zone is not None:
        conditions.append(Finding.zone_id == zone.zone_id)
    if deviation_type is not None:
        conditions.append(Finding.deviation_type_id == deviation_type.deviation_type_id)

    query, _ = _base_query()
    query = query.where(or_(*conditions))
    query = _exclude(
        query,
        exclude_deviation=exclude_deviation,
        exclude_characteristic=exclude_characteristic,
    )

    if zone is not None and deviation_type is not None:
        rank = case((and_(*conditions), 0), else_=1)
    else:
        rank = case((conditions[0], 0), else_=1)
    query = query.order_by(rank, Deviation.date.desc(), Deviation.dev_number.desc())

    zone_id = zone.zone_id if zone is not None else None
    type_id = deviation_type.deviation_type_id if deviation_type is not None else None

    # Единица выдачи — **отклонение целиком**, даже когда совпал один размер
    # (`Search.md`). Запрос идёт по находкам, поэтому отклонение с двумя
    # размерами в одной зоне вернулось бы двумя строками с одним номером, а
    # счётчик «похожих» считал бы находки вместо случаев. Сворачиваем по
    # отклонению, оставляя **сильнейшее** совпадение: строки уже упорядочены
    # рангом, значит первая встреченная и есть сильнейшая.
    #
    # В L1a и L1b свёртка не нужна по построению: там на отклонение приходится
    # ровно одна подходящая находка — один размер даёт одну находку, а на
    # g-позицию у детали идёт ровно один размер (правило «1 баллон = 1 размер»).
    seen: dict[int, PrecedentRow] = {}
    for record in session.execute(query):
        hit_zone = zone_id is not None and record.zone_id == zone_id
        hit_type = type_id is not None and record.deviation_type_id == type_id
        match: Match = (
            "zone+type" if hit_zone and hit_type else "zone" if hit_zone else "type"
        )
        if record.deviation_id not in seen:
            seen[record.deviation_id] = _row(record, match)
    return list(seen.values())


# --- Пакетное состояние канона (снятие N+1 из S4) ---------------------------------


def canon_labels(
    session: Session, characteristics: Iterable[Characteristic]
) -> dict[int, str]:
    """Состояние канона для набора размеров — **один** запрос на набор.

    Заменяет построчный `ui.finding_dialog.canon_state`, который открывал
    сессию на каждую строку (`docs/specs/deviation-entry.md` §8). Ключ —
    `characteristic_id`, значение — `«gN»` либо «не привязан».

    Третье состояние, «размер ещё не заведён», сюда не попадает по определению:
    у него нет характеристики, о которой можно спросить. Для строк формы, где
    размер может быть ещё не создан, есть `canon_labels_for_item`.
    """
    ids = [c.characteristic_id for c in characteristics if c is not None]
    if not ids:
        return {}

    bound = session.execute(
        select(Mapping.characteristic_id, GPosition.g_index)
        .join(GPosition, Mapping.g_position_id == GPosition.g_position_id)
        .where(Mapping.characteristic_id.in_(ids))
    )
    labels = {row.characteristic_id: f"g{row.g_index}" for row in bound}
    return {key: labels.get(key, CANON_UNBOUND) for key in ids}


def canon_labels_for_item(
    session: Session, item: Item, local_numbers: Sequence[str]
) -> dict[str, str]:
    """То же по номерам размеров детали — для формы, где размера может ещё не быть.

    Два запроса независимо от числа строк: сперва характеристики детали, затем
    их состояние канона. Ключ — номер размера, значение — одно из трёх
    достижимых состояний.
    """
    wanted = {(number or "").strip() for number in local_numbers if (number or "").strip()}
    if item is None or not wanted:
        return {}

    existing = {
        characteristic.local_number: characteristic
        for characteristic in session.scalars(
            select(Characteristic)
            .where(Characteristic.item_id == item.item_id)
            .where(Characteristic.local_number.in_(wanted))
        )
    }
    labels = canon_labels(session, existing.values())
    return {
        number: (
            labels.get(existing[number].characteristic_id, CANON_UNBOUND)
            if number in existing
            else CANON_NEW
        )
        for number in wanted
    }
