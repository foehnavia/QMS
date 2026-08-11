"""Точка входа MIS-QMS.

    python src/app.py                 # или: python -m app  (при запуске из src/)

Запуск подготавливает БД к работе: накатывает схему baseline-миграцией, если
её ещё нет, и досеивает справочники (идемпотентно). Новых миграций приложение
не создаёт — схема заморожена на rev 0.1.

Наряд 0002 / QMS-012.
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

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from sqlalchemy import Engine, inspect  # noqa: E402

from db.models import ALL_TABLES  # noqa: E402
from db.session import create_db_engine, default_db_url, session_scope  # noqa: E402
from seed.reference import seed_reference  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

REPO_ROOT = SRC.parent


def prepare_database(engine: Engine) -> None:
    """Накатить схему, если её нет, и досеять справочники."""
    if not set(ALL_TABLES) <= set(inspect(engine).get_table_names()):
        from alembic import command
        from alembic.config import Config

        config = Config(str(REPO_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", str(engine.url))
        print("Схема не найдена — накатываю baseline-миграцию…")
        command.upgrade(config, "head")

    with session_scope(engine) as session:
        inserted = sum(seed_reference(session).values())
    if inserted:
        print(f"Справочники: досеяно значений — {inserted}")


def main(argv: list[str] | None = None) -> int:
    url = default_db_url()
    engine = create_db_engine(url)
    print(f"База: {url}")
    prepare_database(engine)

    app = QApplication(argv if argv is not None else sys.argv)
    # RTL из коробки: иврит — основной язык данных (`architecture.md` §3).
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    window = MainWindow(engine)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
