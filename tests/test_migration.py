"""Миграции: накат на чистой БД, откат, накат поверх rev 0.1 (наряды 0001, 0003)."""

from __future__ import annotations

from alembic import command
from sqlalchemy import inspect

from conftest import alembic_config
from db.models import ALL_TABLES
from db.session import create_db_engine


def test_upgrade_head_creates_all_tables(migrated_url: str) -> None:
    tables = set(inspect(create_db_engine(migrated_url)).get_table_names())
    assert len(ALL_TABLES) == 15
    assert set(ALL_TABLES) <= tables
    # Кроме схемы модели в БД только служебная таблица версий Alembic.
    assert tables - set(ALL_TABLES) == {"alembic_version"}


def test_downgrade_base_rolls_back_cleanly(migrated_url: str) -> None:
    command.downgrade(alembic_config(migrated_url), "base")

    tables = set(inspect(create_db_engine(migrated_url)).get_table_names())
    assert tables & set(ALL_TABLES) == set()


def test_upgrade_downgrade_upgrade_is_repeatable(migrated_url: str) -> None:
    config = alembic_config(migrated_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    tables = set(inspect(create_db_engine(migrated_url)).get_table_names())
    assert set(ALL_TABLES) <= tables
