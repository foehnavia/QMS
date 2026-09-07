"""Миграции: накат на чистой БД, откат, накат поверх rev 0.1 (наряды 0001, 0003)."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from conftest import alembic_config
from db.models import ALL_TABLES
from db.session import create_db_engine


def test_upgrade_head_creates_all_tables(migrated_url: str) -> None:
    tables = set(inspect(create_db_engine(migrated_url)).get_table_names())
    # 16 = 15 таблиц схемы 0.2 + `item_revision` (QMS-017, миграция rev03).
    assert len(ALL_TABLES) == 16
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


# --- rev04: вывод исследования трёхзначен и необязателен (QMS-018, наряд 0027) ----


def _seed_rev03_inspections(engine) -> None:
    """Строки со **старыми** значениями вывода — их и переносит rev04.

    Заводятся сырым SQL на схеме `rev03`: пройти через доменный слой нельзя, он
    уже знает только новые значения, и тест миграции проверял бы тогда не
    миграцию, а самого себя.
    """
    statements = (
        "INSERT INTO ref_connection_type (connection_type_id, name) VALUES (1, 'BSP')",
        "INSERT INTO ref_size (size_id, name) VALUES (1, '1/2\"')",
        "INSERT INTO ref_inspection_type (inspection_type_id, name)"
        " VALUES (1, 'Solidworks assembly')",
        "INSERT INTO item (item_id, item_number, connection_type_id, size_id)"
        " VALUES (1, 'P-0001', 1, 1)",
        "INSERT INTO item_revision (revision_id, item_id, designation, seq, is_current)"
        " VALUES (1, 1, 'A', 1, 1)",
        "INSERT INTO characteristic (characteristic_id, revision_id, local_number)"
        " VALUES (1, 1, '12')",
        "INSERT INTO deviation (deviation_id, dev_number, item_id, revision_id, wo,"
        " quantity, date, decision_date, explanation)"
        " VALUES (1, 'DEV-260907-001', 1, 1, 'W1', 3, '2026-09-07',"
        " '2026-09-07 08:00:00', '')",
        "INSERT INTO finding (finding_id, deviation_id, characteristic_id, direction)"
        " VALUES (1, 1, 1, '+')",
        "INSERT INTO inspection (inspection_id, insp_number, deviation_id, finding_id,"
        " type_id, decision_insp, protocol)"
        " VALUES (1, 'INSP-260907-001', 1, 1, 1, 'approved', 'a.docx')",
        "INSERT INTO inspection (inspection_id, insp_number, deviation_id, finding_id,"
        " type_id, decision_insp, protocol)"
        " VALUES (2, 'INSP-260907-002', 1, 1, 1, 'not_approved', 'b.docx')",
        "INSERT INTO inspection (inspection_id, insp_number, deviation_id, finding_id,"
        " type_id, decision_insp, protocol)"
        " VALUES (3, 'INSP-260907-003', 1, 1, 1, 'approved', 'c.docx')",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def test_rev04_carries_the_old_outcome_values_over(db_url: str) -> None:
    """Критерий 6 наряда `0027`: `approved` -> `approval_possible`,
    `not_approved` -> `approval_not_possible`; число строк не меняется.

    Правило `docs/decisions.md`, QMS-018 решение 1: значения переименованы, а не
    переосмыслены, — поэтому перенос обязан быть полным и без потерь.
    """
    config = alembic_config(db_url)
    command.upgrade(config, "rev03")
    engine = create_db_engine(db_url)
    _seed_rev03_inspections(engine)

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT inspection_id, decision_insp FROM inspection ORDER BY inspection_id")
        ).all()

    assert rows == [
        (1, "approval_possible"),
        (2, "approval_not_possible"),
        (3, "approval_possible"),
    ]


def test_rev04_adds_the_conclusion_empty_and_lets_the_outcome_be_empty(db_url: str) -> None:
    """Новое поле появляется пустым, а вывод становится необязательным.

    Правило `docs/model/Inspection.md` rev 1.01: «Empty means "not assessed yet"
    and is a legitimate state». Пустое значение проверяется **записью** — схема,
    в которой колонка объявлена nullable, но CHECK его не пропускает, выглядела
    бы правильной и не работала.
    """
    config = alembic_config(db_url)
    command.upgrade(config, "rev03")
    engine = create_db_engine(db_url)
    _seed_rev03_inspections(engine)

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM inspection WHERE conclusion IS NOT NULL")
        ).scalar_one() == 0
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE inspection SET decision_insp = NULL, conclusion = 'read later'"
                " WHERE inspection_id = 1"
            )
        )
        connection.execute(
            text("UPDATE inspection SET decision_insp = 'inconclusive' WHERE inspection_id = 2")
        )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT decision_insp, conclusion FROM inspection WHERE inspection_id = 1")
        ).one() == (None, "read later")


def test_rev04_still_refuses_a_value_outside_the_canon(db_url: str) -> None:
    """Обратная сторона: список стал длиннее, но списком быть не перестал.

    Без этой проверки «nullable + новые значения» невозможно отличить от
    «констрейнт потерялся при пересборке таблицы» — а на SQLite пересборка это
    ровно то, чем batch-режим и является.
    """
    config = alembic_config(db_url)
    command.upgrade(config, "rev03")
    engine = create_db_engine(db_url)
    _seed_rev03_inspections(engine)

    command.upgrade(config, "head")

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE inspection SET decision_insp = 'approved' WHERE inspection_id = 1")
            )


def test_rev04_downgrade_converts_back_and_drops_what_has_no_polar_equivalent(
    db_url: str, capsys
) -> None:
    """Критерий 6 наряда: откат описан и работает.

    Старая колонка `NOT NULL` и полярна, поэтому `inconclusive` и пустое перенести
    назад нечем: обратный перенос означал бы **выдумать вердикт**, а вердикт идёт
    в выходной документ. Такие строки удаляются, и удаление громкое — тот же
    приём, что у rev02 с неконвертируемыми отметками кода 99.
    """
    config = alembic_config(db_url)
    command.upgrade(config, "rev03")
    engine = create_db_engine(db_url)
    _seed_rev03_inspections(engine)
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE inspection SET decision_insp = NULL WHERE inspection_id = 2")
        )
        connection.execute(
            text("UPDATE inspection SET decision_insp = 'inconclusive' WHERE inspection_id = 3")
        )

    command.downgrade(config, "rev03")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT inspection_id, decision_insp FROM inspection ORDER BY inspection_id")
        ).all()
        columns = {c["name"] for c in inspect(engine).get_columns("inspection")}
    assert rows == [(1, "approved")]
    assert "conclusion" not in columns
    assert "dropping 2 inspection row(s)" in capsys.readouterr().out


def test_rev04_downgrade_is_silent_when_every_row_is_polar(db_url: str, capsys) -> None:
    """Зеркало предыдущего: терять нечего — миграция ничего не удаляет и молчит."""
    config = alembic_config(db_url)
    command.upgrade(config, "rev03")
    engine = create_db_engine(db_url)
    _seed_rev03_inspections(engine)
    command.upgrade(config, "head")
    capsys.readouterr()

    command.downgrade(config, "rev03")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM inspection")).scalar_one() == 3
    assert "dropping" not in capsys.readouterr().out


def test_rev04_adds_a_column_not_a_table(migrated_url: str) -> None:
    """Критерий 9 наряда: перечень таблиц схемы не изменился.

    `ALL_TABLES` сторожит `test_upgrade_head_creates_all_tables` выше; здесь
    проверяется вторая половина утверждения — что поля действительно добавлены.
    """
    columns = {c["name"] for c in inspect(create_db_engine(migrated_url)).get_columns("inspection")}

    assert {"decision_insp", "conclusion", "protocol"} <= columns
    assert len(ALL_TABLES) == 16
