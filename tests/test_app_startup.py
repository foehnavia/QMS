"""Подготовка базы при запуске приложения (`app.prepare_database`)."""

from __future__ import annotations

from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app import prepare_database
from conftest import alembic_config
from db.models import ALL_TABLES, REFERENCE_MODELS
from db.session import create_db_engine, make_session_factory


def _revision(engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_empty_database_gets_the_whole_schema(db_url: str) -> None:
    engine = create_db_engine(db_url)
    prepare_database(engine)

    assert set(ALL_TABLES) <= set(inspect(engine).get_table_names())
    with make_session_factory(engine)() as session:
        assert all(session.query(model).count() for model in REFERENCE_MODELS)
    engine.dispose()


def test_stale_revision_is_upgraded(db_url: str) -> None:
    """Сверка идёт по ревизии: миграция без новых таблиц тоже должна накатиться."""
    command.upgrade(alembic_config(db_url), "baseline")
    engine = create_db_engine(db_url)
    assert _revision(engine) == "baseline"

    prepare_database(engine)

    assert _revision(engine) == "rev02"
    engine.dispose()


def test_prepared_database_is_left_alone(db_url: str) -> None:
    engine = create_db_engine(db_url)
    prepare_database(engine)
    revision = _revision(engine)

    prepare_database(engine)  # идемпотентно: ни миграций, ни дублей в справочниках

    assert _revision(engine) == revision
    with make_session_factory(engine)() as session:
        names = [row.name for row in session.query(REFERENCE_MODELS[1])]
        assert len(names) == len(set(names))
    engine.dispose()
