"""Подключение к SQLite: движок, `PRAGMA foreign_keys=ON`, фабрика сессий.

Источник истины — файл `app.sqlite` в корне репо (`architecture.md` §4).
URL перекрывается переменной окружения `QMS_DB_URL` (используется тестами и
Alembic-миграциями на временной БД).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

#: Корень репозитория (src/db/session.py → src/db → src → repo).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: БД по умолчанию — источник истины.
DEFAULT_DB_PATH = REPO_ROOT / "app.sqlite"

ENV_DB_URL = "QMS_DB_URL"


def default_db_url() -> str:
    """URL БД: `QMS_DB_URL`, иначе `app.sqlite` в корне репо."""
    return os.environ.get(ENV_DB_URL) or f"sqlite:///{DEFAULT_DB_PATH}"


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """SQLite по умолчанию не проверяет FK — включаем на каждом соединении."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Движок к SQLite с включёнными внешними ключами."""
    return create_engine(url or default_db_url(), echo=echo)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Сессия с commit при успехе и rollback при исключении."""
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
