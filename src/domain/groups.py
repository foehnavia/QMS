"""CharacteristicGroup / g-позиции — канон-слой; создание и правка CG.

Номинал и допуск живут **на g-позиции** и берутся с чертежа; на характеристику
детали они не копируются (`CharacteristicGroup.md`).

Здесь же чертёж группы (наряд 0003): он лежит в самой базе, чтобы она осталась
копируемой одним файлом.

**Координаты позиций код больше не пишет** (наряд 0014, QMS-016). Чертёж приходит
из конструкторского отдела уже размеченным — метки `G1…GN` стоят на выносках, —
и расставлять поверх картинки свои баллоны незачем. Колонки `x`/`y` остаются в
схеме незаполняемыми: сносить их ценой миграции не оправдано, а уже введённые
значения никто не трогает.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import (
    Characteristic,
    CharacteristicGroup,
    GPosition,
    ItemPositionAbsent,
    ItemRevision,
    Mapping,
)

from .errors import DuplicateValue, ValidationError, ValueInUse

#: Потолок размера чертежа — база остаётся копируемой одним файлом.
MAX_DRAWING_BYTES = 5 * 1024 * 1024

#: Сигнатуры допустимых форматов: проверяем содержимое, а не расширение —
#: переименованный `.png` не должен попасть в базу как картинка.
IMAGE_SIGNATURES = {
    "PNG": b"\x89PNG\r\n\x1a\n",
    "JPEG": b"\xff\xd8\xff",
}


@dataclass(frozen=True)
class GPositionSpec:
    """Строка ввода g-позиции: индекс и геометрия с чертежа.

    Номинал и допуски необязательны: позиция бывает допуском формы (соосность
    к базам), и номинала у неё нет вовсе (`CharacteristicGroup.md`, QMS-016).

    `tol_plus` / `tol_minus` — **верхнее и нижнее предельные отклонения** по
    ISO 286, каждое со своим знаком, а не «допуск вверх» и «допуск вниз» по
    модулю: у посадок с натягом оба уходят в плюс (`+0.05 / +0.02`). Отсюда и
    единственный инвариант пары — `_check_deviations`.
    """

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
        raise ValidationError("Group name cannot be empty.")
    if not positions:
        raise ValidationError("A group must have at least one g-position.")

    indexes = [spec.g_index for spec in positions]
    if any(index < 1 for index in indexes):
        raise ValidationError("The g-position index must be positive.")
    if len(set(indexes)) != len(indexes):
        raise DuplicateValue("The g-position indexes inside a group must not repeat.")
    if session.scalar(select(CharacteristicGroup).where(CharacteristicGroup.name == name)):
        raise DuplicateValue(f"Group “{name}” already exists.")
    for spec in positions:
        _check_deviations(spec)

    group = CharacteristicGroup(name=name)
    group.positions = [_position_from_spec(spec) for spec in sorted(positions, key=_by_index)]
    session.add(group)
    session.flush()
    return group


# --- Правка группы (наряд 0003) --------------------------------------------------


def _by_index(spec: GPositionSpec) -> int:
    return spec.g_index


def _deviation_text(value: float) -> str:
    """Отклонение для текста ошибки: минус канона, а не ASCII-дефис.

    Сообщение читает оператор в модальном окне — это интерфейс (`CLAUDE.md` §9),
    и минус в нём тот же, что в ячейке. Форматтер здесь свой на три строки:
    домен не зависит от `ui` (гард `test_ui_smoke`), а тянуть ради знака
    зависимость наоборот — плохой размен.
    """
    return f"{value:g}".replace("-", "−")


def _check_deviations(spec: GPositionSpec) -> GPositionSpec:
    """Единственный инвариант пары: **верхнее ≥ нижнего**, когда заданы оба.

    Проверки знака здесь нет и быть не должно: законны и `+/+` (посадка с
    натягом), и `−/−`, и `+/−`. Единственное, что нельзя, — поменять их местами:
    поле допуска с верхней границей ниже нижней не существует, а на экране такая
    пара выглядит правдоподобно (решение 2026-09-02, находка Р-2).

    Живёт в домене, а не в форме: путей ввода три — новая группа, редактор
    группы и правка позиции, — и инвариант, повторённый в каждом, разойдётся на
    первой же правке.
    """
    upper, lower = spec.tol_plus, spec.tol_minus
    if upper is not None and lower is not None and upper < lower:
        raise ValidationError(
            f"Position g{spec.g_index}: upper deviation {_deviation_text(upper)} is "
            f"below lower deviation {_deviation_text(lower)} — the two are swapped."
        )
    return spec


def _position_from_spec(spec: GPositionSpec) -> GPosition:
    """Новая позиция. `x`/`y` не задаются — они остаются пустыми (QMS-016)."""
    return GPosition(
        g_index=spec.g_index,
        nominal=spec.nominal,
        tol_plus=spec.tol_plus,
        tol_minus=spec.tol_minus,
    )


def update_group(session: Session, group: CharacteristicGroup, *, name: str) -> CharacteristicGroup:
    """Переименовать группу."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Group name cannot be empty.")
    if name != group.name and session.scalar(
        select(CharacteristicGroup).where(CharacteristicGroup.name == name)
    ):
        raise DuplicateValue(f"Group “{name}” already exists.")
    group.name = name
    session.flush()
    return group


def add_position(session: Session, group: CharacteristicGroup, spec: GPositionSpec) -> GPosition:
    """Добавить g-позицию в существующую группу."""
    if spec.g_index < 1:
        raise ValidationError("The g-position index must be positive.")
    if any(position.g_index == spec.g_index for position in group.positions):
        raise DuplicateValue(f"Position g{spec.g_index} already exists in this group.")
    _check_deviations(spec)

    position = _position_from_spec(spec)
    position.cg = group
    session.add(position)
    session.flush()
    return position


def update_position(
    session: Session,
    position: GPosition,
    *,
    nominal: float | None,
    tol_plus: float | None,
    tol_minus: float | None,
) -> GPosition:
    """Заменить геометрию позиции — **целиком**.

    Значений по умолчанию намеренно нет: функция присваивает все поля
    безусловно, поэтому пропущенный аргумент стирал бы старое значение, а
    выглядел бы как «это поле не трогаем». Вызывающий передаёт всё состояние
    позиции — в том числе то, что не менял.

    `x`/`y` в этот перечень больше не входят и здесь **не трогаются вовсе**
    (QMS-016): новые позиции живут без координат, а координаты, заведённые до
    решения, переживают правку геометрии нетронутыми.

    Индекс позиции здесь не меняется: на него ссылаются привязки всех деталей,
    и тихая перенумерация переклеила бы ярлыки под готовыми привязками.
    """
    _check_deviations(
        GPositionSpec(position.g_index, nominal, tol_plus, tol_minus)
    )
    position.nominal = nominal
    position.tol_plus = tol_plus
    position.tol_minus = tol_minus
    session.flush()
    return position


def revisions_of_group(session: Session, group: CharacteristicGroup) -> list[ItemRevision]:
    """Ревизии, привязанные к группе хоть одной позицией — поверх всех выпусков."""
    return list(
        session.scalars(
            select(ItemRevision)
            .join(Characteristic, Characteristic.revision_id == ItemRevision.revision_id)
            .join(Mapping, Mapping.characteristic_id == Characteristic.characteristic_id)
            .join(GPosition, GPosition.g_position_id == Mapping.g_position_id)
            .where(GPosition.cg_id == group.cg_id)
            .distinct()
        )
    )


def revisions_awaiting_answer(
    session: Session, group: CharacteristicGroup
) -> list[ItemRevision]:
    """Действующие ревизии группы, у которых какая-то позиция осталась без ответа.

    Добавленная в группу g-позиция требует ответа — привязки или кода 99 — **только
    от действующих ревизий** (QMS-017, ратификация 7). Прошлые остаются без ответа
    навсегда: их чертёж выпущен и больше не меняется, а вопрос «есть ли эта позиция
    на чертеже `A`» после выхода `B` никто не задаёт и задавать не будет.

    Третьего состояния не заводится: «без ответа» — это **отсутствие строки**, а не
    значение. Заведи его — и пришлось бы отвечать, чем «ещё не спросили» отличается
    от «спросили и не ответили», а на чертеже такого различия нет.
    """
    positions = {position.g_position_id for position in group.positions}
    if not positions:
        return []

    awaiting = []
    for revision in revisions_of_group(session, group):
        if not revision.is_current:
            continue
        answered = {
            mapping.g_position_id
            for characteristic in revision.characteristics
            if (mapping := characteristic.mapping) is not None
        } | {absence.g_position_id for absence in revision.absent_positions}
        if positions - answered:
            awaiting.append(revision)
    return awaiting


def has_no_current_items(session: Session, group: CharacteristicGroup) -> bool:
    """Признак «нет деталей в действующей ревизии» — вычисляемый, не колонка.

    Группа может опустеть незаметно: все детали перевыпущены, и ни одна новая
    ревизия к этой группе не привязана. Признак **выводится запросом** и флагом не
    хранится (ратификация 8) — хранимый пришлось бы поддерживать при каждом клоне,
    каждой привязке и каждой смене действующей ревизии, то есть в трёх местах,
    расходящихся молча.

    Показ этого признака в интерфейсе в наряд `0024` не входит (объявлено §«не
    входит»); данных для него достаточно в любой момент.
    """
    return not any(
        revision.is_current for revision in revisions_of_group(session, group)
    )


def position_usage(session: Session, position: GPosition) -> int:
    """Сколько записей держит позицию: привязки + отметки «нет у детали»."""
    mapped = session.scalar(
        select(func.count()).select_from(Mapping).where(Mapping.g_position_id == position.g_position_id)
    )
    absent = session.scalar(
        select(func.count())
        .select_from(ItemPositionAbsent)
        .where(ItemPositionAbsent.g_position_id == position.g_position_id)
    )
    return mapped + absent


def remove_position(session: Session, position: GPosition) -> None:
    """Удалить свободную позицию; занятую — заблокировать (образец S2)."""
    used = position_usage(session, position)
    if used:
        raise ValueInUse(
            f"Position g{position.g_index} is used by {used} records "
            "(characteristic mappings or “absent from item” marks) — clear them first."
        )
    # Через коллекцию группы: `delete-orphan` удалит строку и уберёт позицию из
    # уже загруженного графа — иначе вызывающий код видит удалённую позицию.
    position.cg.positions.remove(position)
    session.flush()


# --- Чертёж группы ---------------------------------------------------------------


def detect_image_format(data: bytes) -> str | None:
    """Формат по сигнатуре файла (не по расширению)."""
    for name, signature in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            return name
    return None


def set_drawing(
    session: Session, group: CharacteristicGroup, data: bytes | None, name: str | None
) -> CharacteristicGroup:
    """Положить чертёж в группу или снять его (`data=None`).

    Позиции при снятии и замене чертежа не трогаются — ни их геометрия, ни
    оставшиеся от прежней механики координаты: чертёж это картинка рядом с
    таблицей, а не источник её содержимого.
    """
    if data is None:
        group.drawing = None
        group.drawing_name = None
        session.flush()
        return group

    if len(data) > MAX_DRAWING_BYTES:
        raise ValidationError(
            f"The drawing is larger than {MAX_DRAWING_BYTES // (1024 * 1024)} MB "
            f"({len(data) / (1024 * 1024):.1f} MB) — compress it or lower the resolution."
        )
    if detect_image_format(data) is None:
        raise ValidationError("The drawing must be a PNG or JPEG image.")

    group.drawing = data
    group.drawing_name = (name or "").strip() or None
    session.flush()
    return group
