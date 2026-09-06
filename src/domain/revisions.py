"""Ревизии чертежа детали (`Item.md` → Revision, QMS-017).

Ревизия — свойство **чертежа**, а не наших данных: конструкторский отдел
перевыпускает чертёж на любое изменение, и новый выпуск несёт следующее
обозначение. Номер детали при этом остаётся одной записью.

Обозначение вводится **как выпущено** и не разбирается: `A`, `B`, `A1` — строка.
Порядок хранится отдельным полем `seq`, потому что система обязана уметь назвать
«предыдущую», а алфавитный порядок на обозначении не гарантирован.

Заводится ревизия двумя способами и только ими: первая — вместе с деталью
(`items.create_item`), последующие — **клонированием** предыдущей. Клон и есть
главная механика наряда: ревизия, где сдвинулся один допуск, и ревизия, где
переехали все номера, обязаны стоить оператору одного и того же действия.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Characteristic, Item, ItemPositionAbsent, ItemRevision, Mapping

from .errors import DuplicateValue, ValidationError


def list_revisions(item: Item) -> list[ItemRevision]:
    """Ревизии детали в порядке выпуска (по `seq`, не по обозначению)."""
    return sorted(item.revisions, key=lambda revision: revision.seq)


def current_revision(item: Item) -> ItemRevision | None:
    """Действующая ревизия детали. `None` только у детали без ревизий вообще."""
    for revision in item.revisions:
        if revision.is_current:
            return revision
    return None


def previous_revision(revision: ItemRevision) -> ItemRevision | None:
    """Предыдущая по `seq` — та, с которой клонируют.

    Именно ради этого вопроса `seq` и хранится явно: по обозначению ответить
    нельзя, `A1` после `B` — законная пара.
    """
    earlier = [other for other in revision.item.revisions if other.seq < revision.seq]
    return max(earlier, key=lambda other: other.seq) if earlier else None


def _validate_designation(item: Item, designation: str, *, exclude=None) -> str:
    designation = (designation or "").strip()
    if not designation:
        raise ValidationError("Revision designation is required.")
    for existing in item.revisions:
        if existing is exclude:
            continue
        if existing.designation.casefold() == designation.casefold():
            raise DuplicateValue(
                f"Item “{item.item_number}” already has revision “{existing.designation}”."
            )
    return designation


def create_revision(
    session: Session, item: Item, *, designation: str, make_current: bool = True
) -> ItemRevision:
    """Завести ревизию детали пустой — без размеров и без привязок.

    Точка вызова одна: заведение детали. Последующие ревизии заводятся
    `clone_revision` — пустая ревизия у детали, у которой уже есть размеры,
    означала бы, что оператор вводит их заново, а это ровно то, чего наряд
    требует избежать.
    """
    designation = _validate_designation(item, designation)
    seq = 1 + max((other.seq for other in item.revisions), default=0)

    if make_current:
        for other in item.revisions:
            other.is_current = False

    revision = ItemRevision(
        item=item, designation=designation, seq=seq, is_current=make_current
    )
    session.add(revision)
    session.flush()
    return revision


def set_current(session: Session, revision: ItemRevision) -> ItemRevision:
    """Сделать ревизию действующей, сняв признак с прежней.

    Признак снимается **до** установки: частичный уникальный индекс не терпит
    двух действующих ни на мгновение, и обратный порядок падал бы на flush.
    """
    for other in revision.item.revisions:
        if other is not revision:
            other.is_current = False
    session.flush()
    revision.is_current = True
    session.flush()
    return revision


def clone_revision(
    session: Session, item: Item, from_revision: ItemRevision, *, designation: str
) -> ItemRevision:
    """Создать ревизию копией прежней и сделать её действующей.

    Копируется всё, чем ревизия владеет: локальные номера размеров, их привязки
    к g-позициям и строки кода 99. Оператор потом правит только изменившееся.

    **Прежняя ревизия не меняется ничем.** Это не пожелание, а условие: на неё
    ссылаются уже записанные отклонения и находки, и клон обязан быть операцией
    добавления, а не переноса. Копируются значения, а не строки: новые размеры —
    новые `characteristic_id`, поэтому находки прежней ревизии остаются при своих.

    `state_depending` (спящий self-FK) **не копируется**: он живёт внутри одной
    ревизии, и перенос ссылки на размер прежней ревизии связал бы два чертежа —
    это другое отношение (`Characteristic.md`).
    """
    if from_revision.item_id != item.item_id:
        raise ValidationError("The source revision belongs to a different item.")
    designation = _validate_designation(item, designation)

    clone = create_revision(session, item, designation=designation, make_current=True)

    for source in from_revision.characteristics:
        copy = Characteristic(revision=clone, local_number=source.local_number)
        session.add(copy)
        session.flush()
        if source.mapping is not None:
            session.add(
                Mapping(characteristic=copy, g_position_id=source.mapping.g_position_id)
            )

    for absence in from_revision.absent_positions:
        session.add(
            ItemPositionAbsent(revision=clone, g_position_id=absence.g_position_id)
        )

    session.flush()
    return clone


def rename_revision(session: Session, revision: ItemRevision, *, designation: str):
    """Править обозначение — опечатка в выпуске лечится здесь, а не перезаливкой.

    Тот же повод, по которому у детали появился `update_item` (ревью наряда 0012,
    В-2): обозначение вводится руками, значит будет введено неверно.
    """
    revision.designation = _validate_designation(revision.item, designation, exclude=revision)
    session.flush()
    return revision


def characteristic_by_number(revision: ItemRevision, local_number: str):
    """Размер по локальному номеру **внутри ревизии**; `None` — «нет в этой ревизии».

    На этом же ответе держится пометка формы отклонения «not in this revision»:
    номер введён, ревизия выбрана, размера под ним нет.
    """
    local_number = (local_number or "").strip()
    if not local_number:
        return None
    return next(
        (
            characteristic
            for characteristic in revision.characteristics
            if characteristic.local_number == local_number
        ),
        None,
    )


def revisions_with_number(item: Item, local_number: str) -> list[ItemRevision]:
    """Ревизии детали, в которых есть такой локальный номер.

    Прямой путь прецедентов (`precedents.py`) ищет по всем ревизиям детали и
    обязан вернуть ревизию каждого совпадения — выдача помечает ею строку.
    """
    return [
        revision
        for revision in list_revisions(item)
        if characteristic_by_number(revision, local_number) is not None
    ]


def current_revisions_of_items(session: Session, item_ids) -> list[ItemRevision]:
    """Действующие ревизии перечисленных деталей.

    Нужна `groups.py`: добавленная g-позиция требует ответа **только от
    действующих** ревизий; прошлые остаются без ответа — их чертёж выпущен и
    больше не меняется (ратификация 7).
    """
    item_ids = list(item_ids)
    if not item_ids:
        return []
    return list(
        session.scalars(
            select(ItemRevision)
            .where(ItemRevision.item_id.in_(item_ids))
            .where(ItemRevision.is_current.is_(True))
        )
    )
