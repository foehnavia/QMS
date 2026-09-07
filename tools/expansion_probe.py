"""Раскрытие списка отклонений кликом — **на нативной платформе** (доводка 2 наряда 0028).

Живёт здесь, а не в тестах, по `CLAUDE.md` §9а.13: свойство, которое проверяется,
на платформе прогона не воспроизводится. Под offscreen колебание пересчёта
центрирования затухает, под нативной — уходит в неограниченную рекурсию, и
процесс умирает без питоновской трассы. Тест под offscreen был бы зелёным на
сломанном коде.

Запускается **отдельным процессом** намеренно: падение на уровне Qt/C++ унесло бы
прогон целиком, а здесь оно всего лишь код возврата.

    python tools/expansion_probe.py

    0 — клик по стрелке раскрыл запись, повторный свернул, процесс жив;
    иное — воспроизведён стоп-дефект (на сломанном коде процесс умирает молча).

Своя временная база в `build/`: ни `app.sqlite`, ни база прогона не трогаются.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Платформа — нативная, и это весь смысл файла.
os.environ.pop("QT_QPA_PLATFORM", None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

DB = REPO_ROOT / "build" / "expansion-probe.sqlite"


def build_database():
    """Две записи по одной детали, у каждой две находки."""
    from db.models import Direction, RefConnectionType, RefSize
    from db.session import create_db_engine, session_scope
    from domain.characteristics import get_or_create_characteristic
    from domain.deviations import register
    from domain.findings import make_finding
    from domain.items import create_item
    from domain.revisions import current_revision
    from seed.reference import ref, seed_reference

    if DB.exists():
        DB.unlink()
    DB.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{DB.as_posix()}"
    os.environ["QMS_DB_URL"] = url

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_db_engine(url)
    with session_scope(engine) as session:
        seed_reference(session)
        item = create_item(
            session,
            item_number="C1-08375A",
            connection_type=ref(session, RefConnectionType, "C1"),
            size=ref(session, RefSize, "SP"),
            revision="A",
        )
        revision = current_revision(item)
        for wo in ("W26007336", "W26007201"):
            deviation = register(session, item=item, wo=wo, quantity=5, date=date.today())
            for number in ("12", "19"):
                characteristic, _ = get_or_create_characteristic(session, revision, number)
                make_finding(
                    session, deviation, characteristic, direction=Direction.PLUS, value=0.08
                )
    return engine


def click_expander(view, row: int) -> None:
    """Клик мышью по стрелке — **через приложение**, а не вызовом слота (§9а.6)."""
    from ui.deviation_view import COLUMNS

    table = view.table
    index = table.model().index(row, COLUMNS.index(""))
    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        table.visualRect(index).center(),
    )
    QApplication.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication([])

    from ui import kit
    from ui.deviation_view import DeviationView

    kit.apply_theme(app)
    engine = build_database()

    view = DeviationView(engine)
    view.resize(kit.tokens.WINDOW_MIN_WIDTH, kit.tokens.WINDOW_MIN_HEIGHT)
    # **Показываем.** У скрытого виджета `resizeEvent` не приходит вовсе, и ветка,
    # в которой жил дефект, не исполняется (`CLAUDE.md` §9а.5).
    view.show()
    QApplication.processEvents()

    table = view.table
    print(f"  строк до клика: {table.rowCount()}, отступ полотна: {table._margin}", flush=True)

    click_expander(view, 0)
    print(f"  клик 1: раскрыто {view.expanded()}, строк {table.rowCount()}", flush=True)
    if len(view.expanded()) != 1:
        print("  ОТКАЗ: клик по стрелке не раскрыл запись", flush=True)
        return 1

    # Вторая запись при уже раскрытой первой — путь проходит по служебной строке.
    second = next(
        row
        for row in range(table.rowCount())
        if not view.is_panel_row(row) and view._deviation_at(row) not in view.expanded()
    )
    click_expander(view, second)
    print(f"  клик 2: раскрыто {view.expanded()}, строк {table.rowCount()}", flush=True)
    if len(view.expanded()) != 2:
        print("  ОТКАЗ: вторая запись не раскрылась", flush=True)
        return 1

    click_expander(view, 0)
    print(f"  клик 3 (сворачивание): раскрыто {view.expanded()}", flush=True)
    if len(view.expanded()) != 1:
        print("  ОТКАЗ: повторный клик не свернул запись", flush=True)
        return 1

    # Сходимость пересчёта — то самое свойство, которого нет под offscreen.
    from ui.kit.widgets import centring_margin

    if centring_margin(table) != table._margin:
        print(
            f"  ОТКАЗ: пересчёт не имеет неподвижной точки — "
            f"применён {table._margin}, пересчитан {centring_margin(table)}",
            flush=True,
        )
        return 1

    for _ in range(5):
        QApplication.processEvents()

    print("  ОК: три клика пережиты, пересчёт сходится", flush=True)
    view.close()
    engine.dispose()
    return 0


if __name__ == "__main__":
    print("expansion probe (нативная платформа):")
    raise SystemExit(main())
