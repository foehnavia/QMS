"""Миграции: накат на чистой БД, откат, накат поверх rev 0.1 (наряды 0001, 0003)."""

from __future__ import annotations

from alembic import command
from sqlalchemy import inspect, text

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


def _seed_rev01_rows(engine) -> None:
    """Минимальный набор строк rev 0.1: обычная привязка + старая отметка 99."""
    statements = (
        "INSERT INTO ref_connection_type (connection_type_id, name) VALUES (1, 'BSP')",
        "INSERT INTO ref_size (size_id, name) VALUES (1, '1/2\"')",
        "INSERT INTO item (item_id, item_number, connection_type_id, size_id)"
        " VALUES (1, 'P-0001', 1, 1)",
        "INSERT INTO characteristic (characteristic_id, item_id, local_number)"
        " VALUES (1, 1, '12')",
        "INSERT INTO characteristic (characteristic_id, item_id, local_number)"
        " VALUES (2, 1, '77')",
        "INSERT INTO characteristic_group (cg_id, name) VALUES (1, 'CG-A')",
        "INSERT INTO g_position (g_position_id, cg_id, g_index) VALUES (1, 1, 1)",
        # Обычная привязка — должна пережить миграцию нетронутой.
        "INSERT INTO mapping (mapping_id, characteristic_id, g_position_id, is_absent)"
        " VALUES (1, 1, 1, 0)",
        # Старый код 99: позиция не записана — конвертировать нечем.
        "INSERT INTO mapping (mapping_id, characteristic_id, g_position_id, is_absent)"
        " VALUES (2, 2, NULL, 1)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def test_upgrade_over_rev01_drops_unconvertible_code_99_rows(db_url: str, capsys) -> None:
    """Единственная ветка в репозитории, которая удаляет данные (ревью S3, п. 4).

    Флаг `is_absent` не хранил, какой именно позиции нет, поэтому такие строки
    нельзя перенести под `g_position_id NOT NULL` — они удаляются, и удаление
    должно быть громким. Обычные привязки при этом не задеты.
    """
    config = alembic_config(db_url)
    command.upgrade(config, "baseline")
    engine = create_db_engine(db_url)
    _seed_rev01_rows(engine)

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT mapping_id, characteristic_id, g_position_id FROM mapping")
        ).all()
    assert rows == [(1, 1, 1)]  # осталась только конвертируемая привязка
    assert "dropping 1 old code-99" in capsys.readouterr().out


def test_upgrade_over_rev01_keeps_bindings_when_there_is_nothing_to_drop(db_url: str) -> None:
    """Зеркало предыдущего: без строк 99 миграция ничего не удаляет и молчит."""
    config = alembic_config(db_url)
    command.upgrade(config, "baseline")
    engine = create_db_engine(db_url)
    _seed_rev01_rows(engine)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM mapping WHERE g_position_id IS NULL"))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM mapping")).scalar_one() == 1
