"""Поиск прецедентов — главный deliverable Этапа 1 (наряд 0005).

Инженер, заведя отклонение, должен сразу увидеть: случалось ли такое раньше, что
тогда решили и как обосновали (`DeviationCard.md`, шаг 6 процесса). Отсюда два
уровня (`Search.md`):

* **L1 — точный.** По паре «деталь + размер» (`precedents_same_dimension`) и, если
  размер привязан к канону, по g-позиции — она же ловит **другие детали** в том же
  конструктивном месте (`precedents_same_position`).
* **L2 — описательный.** Автоматической выдачи **больше нет** (наряд 0022, ревизия
  ратификации S5). Описательный прецедент — не строка, которую система показывает
  сама, а **результат поиска**, который инженер собирает под конкретный случай из
  нескольких параметров сразу: по одному признаку в выдачу попадает половина базы.
  Машинерия этого поиска строится отдельной задачей (Q-14); здесь её нет вовсе.

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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import (
    Characteristic,
    CharacteristicGroup,
    Deviation,
    Finding,
    GPosition,
    Inspection,
    Item,
    ItemRevision,
    Mapping,
    RefDeviationType,
    RefZone,
)

#: Чем совпал прецедент — читается в UI как заголовок секции.
#: Значения описательного уровня (`zone`, `type`, `zone+type`) сняты вместе с
#: автоматической выдачей: ранжировать нечего, пока запрос не собран человеком.
Match = Literal["dimension", "position"]

#: Состояния размера в каноне. Достижимых ровно три, и «нет у детали (99)» среди
#: них нет по построению: код 99 отмечает g-позицию, которой у детали **нет**, а
#: находка всегда про размер, который у детали **есть** (ратифицировано в S4).
CANON_UNBOUND = "not bound"
CANON_NEW = "not created yet"


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
    revision_id: int
    revision: str
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
    #: Совпадение найдено в другой ревизии, чем та, из которой смотрят.
    #: Отсеивать такие строки нельзя никогда — только помечать (`Search.md`).
    other_revision: bool = False

    @property
    def is_canon_bound(self) -> bool:
        """За номером стоит g-позиция.

        Не-канонный размер выдача помечает знаком `!`: совпадение держится на
        одном локальном номере, а номер принадлежит чертежу — в другой ревизии
        за ним может стоять другой размер. У канонного размера пометки нет: он
        разрешается через маппинг своей ревизии и верен сам собой.
        """
        return self.g_label is not None


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
            ItemRevision.revision_id,
            ItemRevision.designation.label("revision"),
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
        # Ревизия берётся у **размера**, а не у отклонения: инвариант держит их
        # равными, но источник истины один — тот, которому размер принадлежит.
        .join(ItemRevision, Characteristic.revision_id == ItemRevision.revision_id)
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


def _row(record, match: Match, *, reference_revision_id: int | None = None) -> PrecedentRow:
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
        revision_id=record.revision_id,
        revision=record.revision,
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
        other_revision=(
            reference_revision_id is not None
            and record.revision_id != reference_revision_id
        ),
        match=match,
    )


def _fresh_first(query):
    """Свежие сверху; номер — устойчивый доразбор внутри одного дня."""
    return query.order_by(Deviation.date.desc(), Deviation.dev_number.desc())


def _exclude(query, *, exclude_deviation=None, exclude_characteristics=None):
    """Убрать из выдачи отклонение и размеры, показанные соседней секцией.

    Исключение принимает **набор**, а не один размер, и это не обобщение впрок.
    Соседняя секция ищет по локальному номеру **во всех ревизиях детали**, значит
    и показать может несколько размеров — по одному на ревизию. Исключи один —
    и при неподвижном номере тот же прецедент придёт дважды.
    """
    if exclude_deviation is not None:
        query = query.where(Deviation.deviation_id != exclude_deviation.deviation_id)
    if exclude_characteristics:
        ids = [item.characteristic_id for item in exclude_characteristics]
        query = query.where(Finding.characteristic_id.not_in(ids))
    return query


# --- L1 — точный поиск -----------------------------------------------------------


def precedents_same_dimension(
    session: Session,
    characteristic: Characteristic,
    *,
    exclude_deviation: Deviation | None = None,
) -> list[PrecedentRow]:
    """L1a — та же деталь, тот же номер размера, **по всем её ревизиям**.

    Самое сильное совпадение: тот же физический размер той же детали. Прямой
    путь ищет по номеру, а номер принадлежит чертежу — поэтому поиск идёт по
    всем ревизиям детали, а каждая строка выдачи несёт ревизию своего
    совпадения (QMS-017). Совпадение из другой ревизии **не отсеивается
    никогда** — только помечается: отсев прятал бы ровно тот прецедент, ради
    которого карточку и открывают.

    Оборотная сторона названа в каноне и принята: если локальный номер между
    ревизиями переехал, прецедент по нему не найдётся — его поднимают руками.
    Ленивая перепривязка (решение 9) в Этап 1 не входит.
    """
    query, _ = _base_query()
    query = (
        query.where(ItemRevision.item_id == characteristic.revision.item_id)
        .where(Characteristic.local_number == characteristic.local_number)
    )
    query = _exclude(query, exclude_deviation=exclude_deviation)
    return [
        _row(record, "dimension", reference_revision_id=characteristic.revision_id)
        for record in session.execute(_fresh_first(query))
    ]


def _same_number_everywhere(session: Session, characteristic: Characteristic):
    """Размеры этой детали под тем же локальным номером — во всех её ревизиях.

    Ровно то, что отдаёт секция по номеру. Держится одной функцией, чтобы
    «показанное» и «исключённое» не разъехались: разъедутся — на экране появится
    либо дубль, либо дыра, и оба видны только глазом.
    """
    return list(
        session.scalars(
            select(Characteristic)
            .join(ItemRevision, Characteristic.revision_id == ItemRevision.revision_id)
            .where(ItemRevision.item_id == characteristic.revision.item_id)
            .where(Characteristic.local_number == characteristic.local_number)
        )
    )


def precedents_same_position(
    session: Session,
    characteristic: Characteristic,
    *,
    exclude_deviation: Deviation | None = None,
) -> list[PrecedentRow]:
    """L1b — совпадения по **той же канонической позиции**: чужие детали и
    другие ревизии своей.

    Ради этого канон и заведён: одинаковое конструктивное место сравнимо, хотя
    локальные номера у деталей разные (`CharacteristicGroup.md`). Если размер к
    канону не привязан, выдача пуста **без ошибки**: штатное состояние, о котором
    UI говорит словами.

    **Своя деталь больше не выбрасывается** (QMS-017, доводка после прогона).
    Прежнее исключение `item_id != ...` было верным ровно до ревизий: пока у
    детали один набор размеров, «та же деталь и та же g-позиция» означало «тот же
    локальный номер», и соседняя секция такой прецедент уже показывала. Ревизия
    ломает это следование — одна и та же деталь достаёт ту же g-позицию **другим**
    номером, — и прецедент проваливался между секциями: по номеру не находился
    (номер переехал), по канону выбрасывался (деталь своя).

    Секции делятся по **тому, как совпало**, а не по тому, чья деталь. Поэтому
    исключается не деталь, а ровно то, что показала соседняя секция: размеры этой
    детали с тем же локальным номером, во всех её ревизиях. Не переезжал номер —
    прецедент придёт по номеру и сюда не попадёт; переехал — придёт сюда.

    Канонный путь разрешается через маппинг **той ревизии, которой принадлежит
    размер**: маппинг висит на размере, размер — на ревизии, поэтому своей колонки
    ревизии маппингу не понадобилось.
    """
    mapping = characteristic.mapping
    if mapping is None:
        return []

    query, _ = _base_query()
    query = query.where(Mapping.g_position_id == mapping.g_position_id)
    query = _exclude(
        query,
        exclude_deviation=exclude_deviation,
        exclude_characteristics=_same_number_everywhere(session, characteristic),
    )
    return [
        _row(record, "position", reference_revision_id=characteristic.revision_id)
        for record in session.execute(_fresh_first(query))
    ]


# --- L2 — описательный поиск: снят (наряд 0022) ----------------------------------
#
# `precedents_descriptive` удалён вместе с автоматической выдачей. Всё, на чём он
# стоял, осталось на месте и обслуживает L1: `_base_query` (строка выдачи одним
# запросом), `_row`, `_fresh_first`, `_exclude`. `_exclude` сохраняет и параметр
# `exclude_characteristic`, которым пользовался только описательный уровень, —
# «не показывать размер, уже показанный соседней секцией» понадобится любому
# поиску с несколькими выдачами, а восстанавливать его дороже, чем сохранить.
#
# Понадобился он через четыре наряда: QMS-017 (доводка) снял исключение по детали
# и заменил его именно этим — исключением показанного соседней секцией. Механизм
# расширен до набора: секция по номеру отдаёт по размеру на ревизию.


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
    session: Session, revision, local_numbers: Sequence[str]
) -> dict[str, str]:
    """То же по номерам размеров **ревизии** — для формы, где размера может ещё не быть.

    Два запроса независимо от числа строк: сперва характеристики ревизии, затем
    их состояние канона. Ключ — номер размера, значение — одно из трёх
    достижимых состояний.

    Читается **в пределах выбранной ревизии** (QMS-017): номер, которого в ней
    нет, честно получает `not created yet` — на этом ответе форма отклонения и
    строит пометку «not in this revision». Смена ревизии в форме поэтому ничего
    не пересчитывает: меняется не номер, а то, против чего он читается.
    """
    wanted = {(number or "").strip() for number in local_numbers if (number or "").strip()}
    if revision is None or not wanted:
        return {}

    existing = {
        characteristic.local_number: characteristic
        for characteristic in session.scalars(
            select(Characteristic)
            .where(Characteristic.revision_id == revision.revision_id)
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
