"""Точка входа MIS-QMS.

    python src/app.py                 # или: python -m app  (при запуске из src/)

Запуск подготавливает БД к работе: доводит схему до head миграциями Alembic,
если ревизия отстала, и досеивает справочники (идемпотентно). Новых миграций
приложение не создаёт.

Наряды 0002 / QMS-012, 0003 / QMS-013.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Локаль целевой машины — cp1255 (иврит): без этого печать иврита и кириллицы
# в консоль падает с UnicodeEncodeError (INFRASTRUCTURE §8, наряд 0001).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication  # noqa: E402
from sqlalchemy import Engine  # noqa: E402

from db.session import create_db_engine, default_db_url, session_scope  # noqa: E402
from seed.reference import seed_reference  # noqa: E402
from ui.kit import apply_theme  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

REPO_ROOT = SRC.parent


def prepare_database(engine: Engine) -> None:
    """Довести схему до head и досеять справочники.

    Сверяем **ревизию Alembic**, а не набор таблиц: миграция, которая добавляет
    только колонку, по таблицам неотличима от актуальной схемы, и приложение
    молча работало бы на устаревшей базе.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))

    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()

    if current != head:
        print(f"Schema: {current or 'empty'} -> {head}, applying migrations...")
        command.upgrade(config, "head")

    with session_scope(engine) as session:
        inserted = sum(seed_reference(session).values())
    if inserted:
        print(f"Reference data: values inserted - {inserted}")


def main(argv: list[str] | None = None) -> int:
    url = default_db_url()
    engine = create_db_engine(url)
    print(f"Database: {url}")
    prepare_database(engine)

    app = QApplication(argv if argv is not None else sys.argv)
    # Одевание приложения — одной строкой и один раз (наряд 0011): шасси LTR,
    # явная светлая палитра, шрифтовой стек и стиль из токенов канона.
    #
    # Шасси LTR (наряд 0007, `architecture.md` §3): направление **данных** живёт
    # на уровне ячейки и поля (`ui.kit.direction`), а не на уровне приложения —
    # глобальный RTL склеивал два разных вопроса и породил класс дефектов S2-S5.
    # Палитра ставится явно: тёмный режим Windows иначе перекрашивает экраны в
    # то, чего никто не проектировал (канон §0).
    apply_theme(app)

    window = MainWindow(engine)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
