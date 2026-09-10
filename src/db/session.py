"""Подключение к SQLite: движок, `PRAGMA foreign_keys=ON`, фабрика сессий.

Источник истины — файл `app.sqlite` **рядом с приложением** (`architecture.md` §4):
в корне репо при запуске из исходников и рядом с `.exe` под сборкой. Где именно —
отвечает `paths.work_root()`, и отвечает **в момент вызова**, а не при импорте:
под заморозкой корень известен только на старте процесса.

URL перекрывается переменной окружения `QMS_DB_URL` (используется тестами и
Alembic-миграциями на временной БД) — это официальный способ увести базу в другое
место, и он не изменился.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from paths import work_root

#: Имя рабочего файла базы. Одно на все режимы запуска: оператор ищет его глазами.
DB_FILE_NAME = "app.sqlite"

ENV_DB_URL = "QMS_DB_URL"


def default_db_path() -> Path:
    """Путь к рабочей базе — **функция**, а не константа модуля.

    Константа вычислилась бы при импорте, а под однофайловой сборкой это
    происходит внутри каталога распаковки: база легла бы во временную папку и
    исчезла бы вместе с ней при выходе (наряд `0040` §1).
    """
    return work_root() / DB_FILE_NAME


def default_db_url() -> str:
    """URL БД: `QMS_DB_URL`, иначе `app.sqlite` рядом с приложением."""
    return os.environ.get(ENV_DB_URL) or f"sqlite:///{default_db_path()}"


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
