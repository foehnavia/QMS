"""Идемпотентный сид справочников (`docs/model/reference/reference-data.md`).

Стартовые наборы — то, к чему системе надо «прицепиться» на старте; остальное
справочное наполнение приходит по ходу обработки отклонений (оператор заводит
недостающее и продолжает — это штатный путь, не исключение).

Повторный прогон дублей не плодит: вставляются только отсутствующие имена.
"""

from __future__ import annotations

from sqlalchemy import select
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
    RefInspectionType: ("Solidworks assembly", "Implantation torque test"),
}


def seed_reference(session: Session) -> dict[str, int]:
    """Досеять недостающие значения справочников. Возвращает {таблица: вставлено}."""
    inserted: dict[str, int] = {}
    for model, names in REFERENCE_SEED.items():
        existing = set(session.scalars(select(model.name)).all())
        missing = [name for name in names if name not in existing]
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
        raise KeyError(f"{model.__tablename__}: no value {name!r}")
    return obj
