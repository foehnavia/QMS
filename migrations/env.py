"""Окружение Alembic для MIS-QMS.

URL БД берётся из `db.session.default_db_url()` (переменная `QMS_DB_URL`, иначе
`app.sqlite` в корне репо) — так `alembic.ini` не хранит путь и тесты могут
поднимать миграции на временной БД.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, event, pool

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from db.base import Base  # noqa: E402
from db.session import default_db_url  # noqa: E402
import db.models  # noqa: E402,F401  - регистрация моделей в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", default_db_url())

target_metadata = Base.metadata


def _sqlite_disable_foreign_keys(dbapi_connection, connection_record) -> None:
    """На время миграции FK выключены.

    batch-режим пересоздаёт таблицу через DROP + CREATE, а на неё ссылаются
    другие таблицы — при включённых FK такой DROP падает с «FOREIGN KEY
    constraint failed». Приложение включает FK обратно на своих соединениях
    (`db.session`), а целостность после миграции проверяется `foreign_key_check`.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
    finally:
        cursor.close()


def run_migrations_offline() -> None:
    """Миграции в offline-режиме — генерация SQL без соединения."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Миграции с живым соединением."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    sqlite = connectable.dialect.name == "sqlite"
    if sqlite:
        # Выключать FK нужно **на самом соединении при его открытии**: если сделать
        # это через `exec_driver_sql` после connect(), стартует неявная транзакция,
        # Alembic перестаёт владеть коммитом и миграция молча откатывается.
        event.listen(connectable, "connect", _sqlite_disable_foreign_keys)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite не умеет ALTER — правки схемы идут через batch.
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    if sqlite:
        # Страховка: миграция не должна оставить висячих ссылок, пока FK молчали.
        # Проверяем на отдельном соединении — уже после коммита.
        event.remove(connectable, "connect", _sqlite_disable_foreign_keys)
        with connectable.connect() as connection:
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Миграция оставила висячие внешние ключи: {violations}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
