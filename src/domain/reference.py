"""CRUD справочников с защитой (заметка В наряда 0002).

Две защиты:

* **FK-занятое значение не удаляется** — блокируем и говорим, сколько записей
  ссылается. Каскад здесь был бы порчей данных: справочник — контролируемый
  словарь, а не владелец записей.
* **`General` в `connection_type`/`size` — структурный дефолт** (`Item.md`):
  на него опирается заведение детали, когда специфика ещё не важна. Не
  удаляется и не переименовывается.

Остальное наполнение справочников — рабочий путь оператора
(`reference/reference-data.md`), поэтому добавление ничем не ограничено.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from db.models import (
    GENERAL,
    Finding,
    Inspection,
    Item,
    RefConnectionType,
    RefDeviationType,
    RefInspectionType,
    RefItemType,
    RefSize,
    RefZone,
)

from .errors import DuplicateValue, ProtectedValue, ValidationError, ValueInUse

#: Кто ссылается на справочник — источник проверки «значение занято».
REFERENCE_DEPENDENTS: dict[type, tuple[tuple[type, InstrumentedAttribute], ...]] = {
    RefItemType: ((Item, Item.item_type_id),),
    RefConnectionType: ((Item, Item.connection_type_id),),
    RefSize: ((Item, Item.size_id),),
    RefZone: ((Finding, Finding.zone_id),),
    RefDeviationType: ((Finding, Finding.deviation_type_id),),
    RefInspectionType: ((Inspection, Inspection.type_id),),
}

#: Структурные дефолты — переименованию и удалению не подлежат.
PROTECTED_NAMES: dict[type, frozenset[str]] = {
    RefConnectionType: frozenset({GENERAL}),
    RefSize: frozenset({GENERAL}),
}

#: Человеческие имена справочников для UI и сообщений.
REFERENCE_TITLES: dict[type, str] = {
    RefItemType: "Item type",
    RefConnectionType: "Connection type",
    RefSize: "Size class",
    RefZone: "Zone",
    RefDeviationType: "Deviation type",
    RefInspectionType: "Inspection type",
}


def _pk(model: type) -> InstrumentedAttribute:
    return getattr(model, model.__mapper__.primary_key[0].name)


def _clean_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("The name cannot be empty.")
    return cleaned


def is_protected(model: type, name: str) -> bool:
    return name in PROTECTED_NAMES.get(model, frozenset())


def list_values(session: Session, model: type) -> list:
    """Значения справочника по алфавиту."""
    return list(session.scalars(select(model).order_by(model.name)))


def usage_count(session: Session, model: type, value) -> int:
    """Сколько записей ссылается на значение."""
    value_id = getattr(value, model.__mapper__.primary_key[0].name)
    total = 0
    for dependent, column in REFERENCE_DEPENDENTS[model]:
        total += session.scalar(
            select(func.count()).select_from(dependent).where(column == value_id)
        )
    return total


def _existing(session: Session, model: type, name: str):
    """Значение с таким именем **без учёта регистра**.

    Регистронезависимо потому, что регистр перестал быть различием (находка
    №6): раз `thread root` сохраняется как `Thread root`, то `THREAD ROOT` —
    то же значение, а не второе. Прежняя точная сверка пропускала двойников
    ровно с этого дня.
    """
    lowered = (name or "").casefold()
    for value in session.scalars(select(model)):
        if value.name.casefold() == lowered:
            return value
    return None


def capitalised(name: str) -> str:
    """Первая буква заглавная — но аббревиатуру не трогаем (находка №6).

    `thread root` набирают строчными, и в списке рядом с `Solidworks assembly`
    это читается как разнобой, а не как значение. Правило узкое: меняется
    **только первый символ**, и только если строка не выглядит аббревиатурой —
    `NP`, `C1`, `IntHex` остаются собой.
    """
    name = (name or "").strip()
    if not name:
        return name
    head = name.split()[0]
    looks_like_abbreviation = sum(1 for ch in head if ch.isupper()) > 1 or head.isupper()
    if looks_like_abbreviation:
        return name
    return name[0].upper() + name[1:]


def normalise_case(session: Session, model: type) -> int:
    """Привести регистр уже заведённых значений. Возвращает число правок."""
    changed = 0
    for value in session.scalars(select(model)):
        fixed = capitalised(value.name)
        if fixed != value.name and not session.scalar(
            select(model).where(model.name == fixed)
        ):
            value.name = fixed
            changed += 1
    if changed:
        session.flush()
    return changed


def add_value(session: Session, model: type, name: str):
    """Добавить значение. Дубль — понятной ошибкой, не `IntegrityError`."""
    name = capitalised(_clean_name(name))
    if _existing(session, model, name) is not None:
        raise DuplicateValue(f"“{name}” already exists in this reference list.")
    value = model(name=name)
    session.add(value)
    session.flush()
    return value


def ensure_value(session: Session, model: type, name: str):
    """Значение справочника: найти или завести. Регистр значением не считается.

    Заводилось это четырьмя одинаковыми помощниками по тестам и инструментам, и
    все четыре искали **точным** совпадением. С приведением регистра (находка
    №6) такой поиск перестал находить засеянное, а `add_value` следом честно
    отбивал дубль. Одна функция вместо четырёх копий закрывает и это.
    """
    found = _existing(session, model, capitalised(_clean_name(name)))
    return found if found is not None else add_value(session, model, name)


def rename_value(session: Session, model: type, value, new_name: str):
    """Переименовать значение; структурный дефолт защищён."""
    new_name = capitalised(_clean_name(new_name))
    if is_protected(model, value.name):
        raise ProtectedValue(
            f"“{value.name}” is a structural default of the reference list — cannot be renamed."
        )
    if new_name == value.name:
        return value
    clash = _existing(session, model, new_name)
    if clash is not None and clash is not value:
        raise DuplicateValue(f"“{new_name}” already exists in this reference list.")
    value.name = new_name
    session.flush()
    return value


def delete_value(session: Session, model: type, value) -> None:
    """Удалить значение; занятое по FK и структурный дефолт — не удаляются."""
    if is_protected(model, value.name):
        raise ProtectedValue(f"“{value.name}” is a structural default of the reference list — cannot be deleted.")
    used = usage_count(session, model, value)
    if used:
        raise ValueInUse(
            f"“{value.name}” is used by {used} records — reassign them first."
        )
    session.delete(value)
    session.flush()
