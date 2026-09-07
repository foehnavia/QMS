"""Критерий приёмки 5 — сид идемпотентен, `General`-дефолты на месте."""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import GENERAL, REFERENCE_MODELS, RefConnectionType, RefSize
from seed.reference import REFERENCE_SEED, ref, seed_reference


def _counts(session: Session) -> dict[str, int]:
    return {model.__tablename__: session.query(model).count() for model in REFERENCE_MODELS}


def test_seed_fills_the_starting_sets(session: Session) -> None:
    inserted = seed_reference(session)
    session.commit()

    # Сид кладёт значения в том же виде, что и ручной ввод: первая буква
    # заглавная, аббревиатуры нетронуты (находка №6). Сверяем с приведёнными,
    # а не с сырым списком — иначе тест требовал бы от сида разнобоя.
    from domain.reference import capitalised

    for model, names in REFERENCE_SEED.items():
        assert inserted[model.__tablename__] == len(names)
        assert {row.name for row in session.query(model)} == {
            capitalised(name) for name in names
        }


def test_seed_is_idempotent(session: Session) -> None:
    seed_reference(session)
    session.commit()
    before = _counts(session)

    inserted = seed_reference(session)
    session.commit()

    assert _counts(session) == before
    assert set(inserted.values()) == {0}


def test_seed_tops_up_a_partially_filled_reference(session: Session) -> None:
    """Оператор мог завести значение сам — сид досеивает недостающее, не дублируя."""
    session.add(RefSize(name="NP"))
    session.commit()

    inserted = seed_reference(session)
    session.commit()

    assert inserted["ref_size"] == len(REFERENCE_SEED[RefSize]) - 1
    names = [row.name for row in session.query(RefSize)]
    assert len(names) == len(set(names)) == len(REFERENCE_SEED[RefSize])


def test_general_defaults_exist(session: Session) -> None:
    seed_reference(session)
    session.commit()

    assert ref(session, RefConnectionType, GENERAL).name == GENERAL
    assert ref(session, RefSize, GENERAL).name == GENERAL


def test_the_starting_set_of_inspection_types_names_all_three(session: Session) -> None:
    """Правило `docs/model/reference/reference-data.md` rev 1.01: стартовый набор
    типов исследования — **`Solidworks assembly`, `Implantation torque test`,
    `Tolerances review`**.

    Значения названы здесь **дословно**, а не выведены из `REFERENCE_SEED`:
    тест, сверяющий сид с самим сидом, зелен при любом его содержимом и не
    сторожит ничего (`CLAUDE.md` §9а.9 — тест, разделяющий с кодом ту самую
    величину, которую проверяет). Именно поэтому пропажу `Tolerances review`
    прогон бы не заметил: `test_seed_fills_the_starting_sets` выше сравнивает
    набор с ним же.

    Третий тип въехал в набор с QMS-024: в паре с `No protocol` это названный
    случай вердикта, который чертёж решает сам, и набор без него заставлял первое
    же такое отклонение ждать значения, вписанного руками.
    """
    from db.models import RefInspectionType

    seed_reference(session)
    session.commit()

    assert {row.name for row in session.query(RefInspectionType)} == {
        "Solidworks assembly",
        "Implantation torque test",
        "Tolerances review",
    }


def test_a_fresh_database_carries_those_three_and_nothing_else(migrated_url: str) -> None:
    """Критерий доводки: **новая пустая база несёт три типа**.

    Отдельно от предыдущего потому, что тот работает на сессии, уже поднятой
    фикстурой; здесь база создаётся миграциями с нуля — тем же путём, каким она
    появляется у оператора.
    """
    from db.models import RefInspectionType
    from db.session import create_db_engine, make_session_factory

    engine = create_db_engine(migrated_url)
    with make_session_factory(engine)() as fresh:
        seed_reference(fresh)
        fresh.commit()
        names = {row.name for row in fresh.query(RefInspectionType)}
    engine.dispose()

    assert names == {
        "Solidworks assembly",
        "Implantation torque test",
        "Tolerances review",
    }
