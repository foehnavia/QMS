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

from sqlalchemy import func, select, update
from sqlalchemy.orm import InstrumentedAttribute, Session

from db.models import (
    GENERAL,
    REFERENCE_MODELS,
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


def find_value(session: Session, model: type, name: str):
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


def _identity(value) -> int:
    """Первичный ключ значения справочника — у каждого списка он свой по имени."""
    from sqlalchemy import inspect as sa_inspect

    column = sa_inspect(type(value)).primary_key[0].name
    return getattr(value, column)


def merge_values(session: Session, model: type, keep, drop) -> int:
    """Свести два значения одного справочника в одно. Возвращает число перевешенных.

    Зачем доменной операцией, а не разовым скриптом (§4.1 наряда 0021): то же
    самое понадобится при импорте `.xlsx` на S6, где регистр придёт из чужой
    таблицы, и «свести близнецов» станет штатной работой, а не уборкой.

    Что делает: все записи, ссылающиеся на `drop`, перевешиваются на `keep`,
    после чего `drop` удаляется — уже без ссылок, поэтому штатный гард
    «занятое значение не удаляется» не мешает.

    **Почему это не порча данных.** Ссылка на справочник — это ссылка на
    *значение*, а не на строку: `Thread burr` и `thread burr` для оператора
    одно и то же, и именно их раздельность ломала поиск прецедентов (тип
    отклонения — один из двух ключей L2).
    """
    if keep is drop or keep.name == drop.name:
        raise ValidationError("Merging a value into itself makes no sense.")
    if not isinstance(keep, model) or not isinstance(drop, model):
        raise ValidationError("Both values must belong to the same reference list.")

    # Карта зависимостей держит **колонки ключей**, а не связи, поэтому
    # перевешиваем идентификатором: так же, как их и хранит база.
    keep_id, drop_id = _identity(keep), _identity(drop)

    moved = 0
    for owner, attribute in REFERENCE_DEPENDENTS[model]:
        # Обновлением, а не присваиванием полю: у владельца есть **связь** на
        # то же значение, и она авторитетнее ключа — сессия возвращала ссылку
        # обратно на близнеца при сохранении. После массового обновления
        # объекты в памяти устарели, поэтому их сбрасываем.
        result = session.execute(
            update(owner).where(attribute == drop_id).values({attribute.key: keep_id})
        )
        moved += result.rowcount or 0
    session.expire_all()

    session.delete(drop)
    session.flush()
    return moved


def normalise_case(session: Session, model: type) -> list[tuple[str, str, int]]:
    """Привести регистр списка к правилу «первая буква заглавная».

    Возвращает список `(выжившее, снятое, перевешено)` — то, что уходит в отчёт
    оператору: это его данные, и он должен видеть, что с ними сделали.

    Две ветки, и различать их обязательно (§3 наряда 0021):

    * близнец существует — значения **сводятся** `merge_values`, выживает форма
      с заглавной;
    * близнеца нет — значение **переименовывается**. Не добавляется: добавление
      и породило бы ровно тех близнецов, которых мы убираем.
    """
    report: list[tuple[str, str, int]] = []
    for value in list(session.scalars(select(model))):
        fixed = capitalised(value.name)
        if fixed == value.name:
            continue
        # Близнеца ищем **среди других**: `find_value` вернула бы саму
        # нормализуемую строку — её имя отличается от искомого лишь регистром,
        # и ветка ушла бы в переименование при живом близнеце.
        lowered = fixed.casefold()
        twin = next(
            (
                other
                for other in session.scalars(select(model))
                if other is not value and other.name.casefold() == lowered
            ),
            None,
        )
        if twin is not None:
            keep, drop = (twin, value) if twin.name == fixed else (value, twin)
            moved = merge_values(session, model, keep, drop)
            report.append((keep.name, drop.name, moved))
        else:
            value.name = fixed
            report.append((fixed, value.name, 0))
    session.flush()
    return report


def normalise_all(session: Session) -> dict[str, list[tuple[str, str, int]]]:
    """Привести регистр во **всех** шести списках. Отчёт по каждому."""
    return {
        model.__tablename__: normalise_case(session, model)
        for model in REFERENCE_MODELS
    }


def add_value(session: Session, model: type, name: str):
    """Добавить значение. Дубль — понятной ошибкой, не `IntegrityError`."""
    name = capitalised(_clean_name(name))
    if find_value(session, model, name) is not None:
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
    found = find_value(session, model, capitalised(_clean_name(name)))
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
    clash = find_value(session, model, new_name)
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
