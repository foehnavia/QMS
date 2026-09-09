"""Ввод номера через **настоящий редактор ячейки** и `Done` — на нативной платформе.

Часть (в) доказательства наряда `0039`. Живёт здесь, а не в тестах, по двум
причинам сразу:

* `CLAUDE.md` §9а.13 — свойство проверяется там, где воспроизводится: путь
  «клик → набор → Enter → Done» идёт через делегат и диспетчеризацию, и мерить
  его надо на настоящей платформе, а не под offscreen;
* `CLAUDE.md` §9а.14 — дефект, который **убивает процесс**, красного теста не
  даёт: он уносит весь прогон. Отдельный процесс превращает смерть в код
  возврата и печатает **число**, по которому старое и новое состояние
  сравнимы.

Что считается: сколько раз таблица была **пересобрана внутри эмиссии**
`itemChanged` — то есть сколько вызовов `setRowCount` / `setItem` случилось,
пока обработчик сигнала ещё на стеке. На исправленном коде обязан быть **0**.

    python tools/mapping_probe.py

    0 — пересборок внутри эмиссии нет, номер записан, процесс жив;
    1 — пересборки есть (их число напечатано) либо запись не состоялась;
    смерть процесса без вывода — воспроизведён сам дефект.

Своя временная база в `build/`: ни `app.sqlite`, ни база прогона не трогаются.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Платформа — нативная, и это половина смысла файла.
os.environ.pop("QT_QPA_PLATFORM", None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

DB = REPO_ROOT / "build" / "mapping-probe.sqlite"


def _database():
    """Своя база с одной деталью, одной группой и тремя позициями."""
    if DB.exists():
        DB.unlink()
    DB.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{DB.as_posix()}"
    os.environ["QMS_DB_URL"] = url

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    from db.models import Item, ItemRevision, RefConnectionType, RefSize
    from db.session import create_db_engine, session_scope
    from domain.groups import GPositionSpec, create_group
    from domain.mappings import bind, mark_absent
    from domain.reference import GENERAL, ensure_value
    from domain.revisions import current_revision

    engine = create_db_engine(url)
    with session_scope(engine) as session:
        group = create_group(
            session,
            "Implant_Con_375_C1",
            (GPositionSpec(1, 3.75, 0.05, -0.05), GPositionSpec(2, 2.0), GPositionSpec(3)),
        )
        item = Item(
            item_number="C1-08375A",
            connection_type=ensure_value(session, RefConnectionType, GENERAL),
            size=ensure_value(session, RefSize, GENERAL),
        )
        session.add(item)
        session.flush()
        session.add(ItemRevision(item=item, designation="A", seq=1, is_current=True))
        session.flush()
        revision = current_revision(item)
        positions = sorted(group.positions, key=lambda p: p.g_index)
        # Две позиции решены заранее: остаётся одна, и `Done` обязана закрыть окно.
        bind(session, revision, positions[1], "19")
        mark_absent(session, revision, positions[2])
        ids = (item.item_id, group.cg_id)
    return engine, ids


def main() -> int:
    app = QApplication.instance() or QApplication([])
    from ui import kit
    from ui.mapping_dialog import LOCAL_NUMBER, MappingDialog

    kit.apply_theme(app)
    engine, (item_id, cg_id) = _database()

    dialog = MappingDialog(engine, item_id, cg_id)
    dialog.show()
    QApplication.processEvents()
    table = dialog.table

    # Считаем пересборки, случившиеся **пока обработчик на стеке**.
    inside: list[str] = []
    depth = {"in_slot": 0}
    original_set_item = table.setItem
    original_set_row_count = table.setRowCount

    def counted(name, original):
        def wrapper(*args):
            if depth["in_slot"]:
                inside.append(name)
            return original(*args)

        return wrapper

    table.setItem = counted("setItem", original_set_item)
    table.setRowCount = counted("setRowCount", original_set_row_count)

    def enter(_item):
        depth["in_slot"] += 1

    def leave(_item):
        depth["in_slot"] -= 1

    # Слоты-скобки вокруг боевого: первый подключён раньше него, второй позже,
    # поэтому счётчик поднят ровно на время обработчика.
    table.itemChanged.disconnect(dialog._on_edit)
    table.itemChanged.connect(enter)
    table.itemChanged.connect(dialog._on_edit)
    table.itemChanged.connect(leave)

    index = table.model().index(0, LOCAL_NUMBER)
    table.setCurrentIndex(index)
    table.edit(index)
    QApplication.processEvents()

    editor = table.viewport().focusWidget()
    if editor is None:
        print("  ОТКАЗ: редактор ячейки не открылся — зонд до кода не дошёл", flush=True)
        return 1

    QTest.keyClicks(editor, "12")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()

    dialog.finish()
    for _ in range(5):
        QApplication.processEvents()

    print(f"  пересборок внутри эмиссии: {len(inside)}  {inside or ''}", flush=True)

    from db.models import CharacteristicGroup, Item
    from db.session import session_scope
    from domain.mappings import binding_state
    from domain.revisions import current_revision

    with session_scope(engine) as session:
        states = binding_state(
            session,
            current_revision(session.get(Item, item_id)),
            session.get(CharacteristicGroup, cg_id),
        )
    bound = states[0].state == "linked" and states[0].local_number == "12"
    print(f"  привязка записана: {bound}  (состояние {states[0].state!r}, "
          f"номер {states[0].local_number!r})", flush=True)

    table.setItem = original_set_item
    table.setRowCount = original_set_row_count
    dialog.close()
    engine.dispose()

    if inside:
        print("  ОТКАЗ: таблица пересобрана внутри эмиссии своего сигнала", flush=True)
        return 1
    if not bound:
        print("  ОТКАЗ: номер, набранный в редакторе, не записан", flush=True)
        return 1
    print("  ОК: пересборок нет, номер записан, процесс жив", flush=True)
    return 0


if __name__ == "__main__":
    print("mapping probe (нативная платформа):")
    raise SystemExit(main())
