"""CharacteristicGroup / g-позиции — канон-слой; создание и правка CG.

Номинал и допуск живут **на g-позиции** и берутся с чертежа; на характеристику
детали они не копируются (`CharacteristicGroup.md`).

Здесь же чертёж группы и координаты баллонов (наряд 0003): чертёж лежит в базе,
координаты нормализованы 0..1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import CharacteristicGroup, GPosition, ItemPositionAbsent, Mapping

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
    """Строка ввода g-позиции: индекс, геометрия с чертежа и место баллона."""

    g_index: int
    nominal: float | None = None
    tol_plus: float | None = None
    tol_minus: float | None = None
    x: float | None = None
    y: float | None = None


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
    group.positions = [_position_from_spec(spec) for spec in sorted(positions, key=_by_index)]
    session.add(group)
    session.flush()
    return group


# --- Правка группы (наряд 0003) --------------------------------------------------


def _by_index(spec: GPositionSpec) -> int:
    return spec.g_index


def _check_coordinate(value: float | None, axis: str) -> float | None:
    """Координаты нормализованы 0..1 — иначе баллон уедет за пределы чертежа."""
    if value is None:
        return None
    if not 0.0 <= value <= 1.0:
        raise ValidationError(f"Координата {axis} должна быть в диапазоне 0..1, получено {value}.")
    return float(value)


def _position_from_spec(spec: GPositionSpec) -> GPosition:
    return GPosition(
        g_index=spec.g_index,
        nominal=spec.nominal,
        tol_plus=spec.tol_plus,
        tol_minus=spec.tol_minus,
        x=_check_coordinate(spec.x, "x"),
        y=_check_coordinate(spec.y, "y"),
    )


def update_group(session: Session, group: CharacteristicGroup, *, name: str) -> CharacteristicGroup:
    """Переименовать группу."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Название группы не может быть пустым.")
    if name != group.name and session.scalar(
        select(CharacteristicGroup).where(CharacteristicGroup.name == name)
    ):
        raise DuplicateValue(f"Группа «{name}» уже есть.")
    group.name = name
    session.flush()
    return group


def add_position(session: Session, group: CharacteristicGroup, spec: GPositionSpec) -> GPosition:
    """Добавить g-позицию в существующую группу."""
    if spec.g_index < 1:
        raise ValidationError("Индекс g-позиции должен быть положительным.")
    if any(position.g_index == spec.g_index for position in group.positions):
        raise DuplicateValue(f"Позиция g{spec.g_index} в группе уже есть.")

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
    x: float | None,
    y: float | None,
) -> GPosition:
    """Заменить геометрию и место баллона — **целиком**.

    Значений по умолчанию намеренно нет: функция присваивает все поля
    безусловно, поэтому пропущенный аргумент стирал бы старое значение, а
    выглядел бы как «это поле не трогаем». Вызывающий передаёт всё состояние
    позиции — в том числе то, что не менял.

    Индекс позиции здесь не меняется: на него ссылаются привязки всех деталей,
    и тихая перенумерация переклеила бы ярлыки под готовыми привязками.
    """
    position.nominal = nominal
    position.tol_plus = tol_plus
    position.tol_minus = tol_minus
    position.x = _check_coordinate(x, "x")
    position.y = _check_coordinate(y, "y")
    session.flush()
    return position


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
            f"Позиция g{position.g_index} используется в {used} записях "
            "(привязки размеров или отметки «нет у детали») — сначала снимите их."
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

    Координаты позиций при снятии и замене чертежа **сохраняются** (заметка Б
    наряда 0003): оператор поправит баллоны перетаскиванием, а не расставит заново.
    """
    if data is None:
        group.drawing = None
        group.drawing_name = None
        session.flush()
        return group

    if len(data) > MAX_DRAWING_BYTES:
        raise ValidationError(
            f"Чертёж больше {MAX_DRAWING_BYTES // (1024 * 1024)} МБ "
            f"({len(data) / (1024 * 1024):.1f} МБ) — сожмите файл или уменьшите разрешение."
        )
    if detect_image_format(data) is None:
        raise ValidationError("Чертёж должен быть картинкой PNG или JPEG.")

    group.drawing = data
    group.drawing_name = (name or "").strip() or None
    session.flush()
    return group
