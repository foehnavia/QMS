"""Общие фикстуры: чистая БД под каждый тест.

Схема поднимается **той же baseline-миграцией Alembic**, что и в production —
так тесты проверяют миграцию, а не параллельный `create_all`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Qt должен узнать про offscreen до создания QApplication (заметка Е наряда 0002).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from db.models import GENERAL, Item, RefConnectionType, RefSize
from db.session import create_db_engine, make_session_factory
from seed.reference import ref, seed_reference

REPO_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(db_url: str) -> Config:
    """Конфиг Alembic, нацеленный на конкретную БД."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """URL временной SQLite-БД; `QMS_DB_URL` подменён, чтобы env.py смотрел сюда."""
    url = f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}"
    monkeypatch.setenv("QMS_DB_URL", url)
    return url


@pytest.fixture
def migrated_url(db_url: str) -> str:
    """Пустая БД со схемой, накатанной `alembic upgrade head`."""
    command.upgrade(alembic_config(db_url), "head")
    return db_url


@pytest.fixture
def engine(migrated_url: str) -> Iterator[Engine]:
    engine = create_db_engine(migrated_url)
    yield engine
    engine.dispose()


@contextmanager
def reopen(db_url: str) -> Iterator[Session]:
    """Сессия на новом соединении — чтение идёт из файла, не из identity map."""
    engine = create_db_engine(db_url)
    try:
        with make_session_factory(engine)() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = make_session_factory(engine)
    with factory() as session:
        yield session


@pytest.fixture
def seeded_session(session: Session) -> Session:
    """Сессия на БД с засеянными справочниками."""
    seed_reference(session)
    session.commit()
    return session


@pytest.fixture(scope="session")
def qt_app():
    """Единственный `QApplication` на прогон — LTR-шасси, как в боевом запуске.

    Направление данных живёт на уровне ячейки и поля (`ui.common`), поэтому
    приложению остаётся только шасси (наряд 0007, §4).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    yield app
    app.processEvents()


def make_png(width: int = 16, height: int = 12, color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """Настоящий PNG без Qt — для проверок чертежа в домене и в UI."""
    import struct
    import zlib

    signature = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
    raw = b"".join(bytes([0]) + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_item(session: Session, item_number: str) -> Item:
    """Деталь на `General`-дефолтах — минимум для тестов связей."""
    item = Item(
        item_number=item_number,
        connection_type=ref(session, RefConnectionType, GENERAL),
        size=ref(session, RefSize, GENERAL),
    )
    session.add(item)
    session.flush()
    return item


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[str]]:
    """Считать SQL-запросы, ушедшие в базу внутри блока (наряд 0005, критерий 8).

    Возвращает список текстов запросов — по нему видно не только «сколько», но и
    «какие», что превращает провал теста на `N+1` в готовый диагноз. Слушатель
    снимается в `finally`: висящий подписчик исказил бы соседние тесты.
    """
    from sqlalchemy import event

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)
