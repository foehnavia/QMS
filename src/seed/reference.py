"""Идемпотентный сид справочников (`docs/model/reference/reference-data.md`).

Стартовые наборы — то, к чему системе надо «прицепиться» на старте; остальное
справочное наполнение приходит по ходу обработки отклонений (оператор заводит
недостающее и продолжает — это штатный путь, не исключение).

Повторный прогон дублей не плодит: вставляются только отсутствующие имена.
"""

from __future__ import annotations

from sqlalchemy import select

from domain.reference import capitalised
from sqlalchemy.orm import Session

from db.models import (
    GENERAL,
    RefConnectionType,
    RefDeviationType,
    RefInspectionType,
    RefItemType,
    RefSize,
    RefZone,
)

#: Стартовые значения справочников. Порядок — как в `REFERENCE_MODELS`.
REFERENCE_SEED: dict[type, tuple[str, ...]] = {
    # Примеры; расширяется администратором.
    RefItemType: ("implant", "abutment", "drill"),
    # `General` — дефолт: деталь заводится, когда специфика ещё не важна.
    RefConnectionType: ("C1", "V3", "IntHex", "LYNX", GENERAL),
    RefSize: ("NP", "SP", "WP", GENERAL),
    # Зона — мягкий поисковый ярлык, наполняется оператором; здесь 2 примера.
    RefZone: ("thread", "cutting edge"),
    RefDeviationType: (
        "thread burr",
        "thread length",
        "inner diameter",
        "cutting-edge width",
        "angle",
    ),
    # Три типа, а не два (`reference/reference-data.md` rev 1.01, QMS-024):
    # `Tolerances review` — названный случай вердикта, который чертёж решает сам,
    # и в паре с `No protocol` он законен. Стартовый набор без него заставлял
    # первое же такое отклонение ждать значения, вписанного руками.
    RefInspectionType: (
        "Solidworks assembly",
        "Implantation torque test",
        "Tolerances review",
    ),
}


def seed_reference(session: Session) -> dict[str, int]:
    """Досеять недостающие значения справочников. Возвращает {таблица: вставлено}."""
    inserted: dict[str, int] = {}
    for model, names in REFERENCE_SEED.items():
        # Сверка **без учёта регистра** — это и была причина близнецов (наряд
        # 0021): сид сравнивал имена точно, поэтому при каждом запуске
        # дописывал `Thread burr` рядом с уже лежащим `thread burr`. Регистр
        # различием не считается ни для оператора, ни для поиска.
        existing = {name.casefold() for name in session.scalars(select(model.name))}
        names = [capitalised(name) for name in names]
        missing = [name for name in names if name.casefold() not in existing]
        session.add_all([model(name=name) for name in missing])
        inserted[model.__tablename__] = len(missing)
    session.flush()
    return inserted


def ref(session: Session, model: type, name: str):
    """Справочная строка по имени (KeyError, если значения нет).

    Точка доступа к `General`-дефолтам: `ref(session, RefSize, GENERAL)`.
    """
    obj = session.scalar(select(model).where(model.name == name))
    if obj is None:
        # Регистр перестал быть различием (находка №6): значение хранится с
        # заглавной, а зовут его как написано в каноне и в тестах. Искать
        # точным совпадением значило бы требовать помнить, как оно записано.
        lowered = name.casefold()
        obj = next(
            (
                value
                for value in session.scalars(select(model))
                if value.name.casefold() == lowered
            ),
            None,
        )
    if obj is None:
        raise KeyError(f"{model.__tablename__}: no value {name!r}")
    return obj
