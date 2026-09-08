"""Замер сетки экрана отклонений: ширины колонок и высоты строк — в JSON.

**Зачем инструмент, а не тест.** Наряд `0031` переносит `FindingsPanel` и её
обслугу из `deviation_view.py` в `common.py` и требует доказать, что список
отклонений не изменился **ни на пиксель** — «замером, а не утверждением»
(критерий 5). Утверждение здесь и правда ничего не стоит: механический перенос
выглядит безобидно ровно до той минуты, когда выясняется, что вместе с именем
уехало значение токена или порядок инициализации.

Замер снимается **до** правки и **после**, и сравниваются два файла. Тест такого
не умеет по построению: он знает только сегодняшнее состояние, а вопрос здесь —
о разнице между двумя состояниями кода.

Платформа — нативная, как и у `screenshots.py`: под offscreen шрифт моноширинный,
и колонка, которую считает `QFontMetrics` (`Revision`), дала бы там другое число
(`CLAUDE.md` §9а.8).

    python tools/grid_probe.py build/grid-before.json
    python tools/grid_probe.py build/grid-after.json
    python tools/grid_probe.py --diff build/grid-before.json build/grid-after.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def measure(window_width: int = 1920) -> dict:
    """Снять сетку и высоты строк списка отклонений на демо-данных.

    Данные — те же, что у снимков: своя временная база, посеянная
    `tools.screenshots`, чтобы замер брался с реальных строк, а не с пустой
    таблицы, где высоты не с чего считать.
    """
    from PySide6.QtWidgets import QApplication

    from screenshots import build_database  # noqa: PLC0415 — путь настроен выше

    app = QApplication.instance() or QApplication([])

    from ui.deviation_view import COLUMNS, DeviationView  # noqa: PLC0415
    from ui.kit import apply_theme  # noqa: PLC0415

    apply_theme(app)
    engine, _url, _ids = build_database()
    view = DeviationView(engine)
    view.resize(window_width, 900)
    view.layout().activate()
    view.apply_grid()

    # Раскрыть **всё**, что раскрывается: высоты служебных строк и есть главное,
    # что может уехать при переносе панели.
    for deviation_id in list(_deviation_ids(view)):
        _expand(view, deviation_id)
    view.layout().activate()

    table = view.table
    return {
        "window_width": window_width,
        "columns": {
            name: table.columnWidth(index) for index, name in enumerate(COLUMNS)
        },
        "row_heights": [table.rowHeight(row) for row in range(table.rowCount())],
        "panel_rows": [
            row for row in range(table.rowCount()) if view.panel_at(row) is not None
        ],
        "panel_heights": [
            view.panel_at(row).height()
            for row in range(table.rowCount())
            if view.panel_at(row) is not None
        ],
        "panel_columns": _panel_columns(view),
    }


def _deviation_ids(view) -> list[int]:
    from ui.deviation_view import COLUMNS, DEVIATION_ROLE  # noqa: PLC0415

    column = COLUMNS.index("Number")
    ids = []
    for row in range(view.table.rowCount()):
        cell = view.table.item(row, column)
        if cell is not None and cell.data(DEVIATION_ROLE) is not None:
            ids.append(cell.data(DEVIATION_ROLE))
    return ids


def _expand(view, deviation_id: int) -> None:
    """Раскрыть по идентификатору: номера строк едут после каждого раскрытия."""
    from ui.deviation_view import COLUMNS, DEVIATION_ROLE  # noqa: PLC0415

    column = COLUMNS.index("Number")
    for row in range(view.table.rowCount()):
        cell = view.table.item(row, column)
        if cell is not None and cell.data(DEVIATION_ROLE) == deviation_id:
            view.toggle_expansion(row)
            return


def _panel_columns(view) -> dict[str, int]:
    """Ширины колонок первой попавшейся панели — они у всех одни."""
    for row in range(view.table.rowCount()):
        panel = view.panel_at(row)
        if panel is not None:
            return {
                panel.horizontalHeaderItem(index).text(): panel.columnWidth(index)
                for index in range(panel.columnCount())
            }
    return {}


def diff(before: Path, after: Path) -> int:
    """Сравнить два замера. Возврат 0 — совпали, 1 — нет."""
    left = json.loads(before.read_text(encoding="utf-8"))
    right = json.loads(after.read_text(encoding="utf-8"))

    if left == right:
        print(f"СОВПАЛО: {before.name} == {after.name}")
        print(f"  колонок: {len(left['columns'])}, строк: {len(left['row_heights'])}, "
              f"панелей: {len(left['panel_heights'])}")
        return 0

    print(f"РАЗОШЛОСЬ: {before.name} != {after.name}")
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            print(f"  {key}:\n    было: {left.get(key)}\n    стало: {right.get(key)}")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "--diff":
        return diff(Path(argv[2]), Path(argv[3]))

    target = Path(argv[1]) if len(argv) > 1 else REPO / "build" / "grid.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = measure()
    target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {target}")
    print(f"   колонок: {len(snapshot['columns'])}, строк: {len(snapshot['row_heights'])}, "
          f"панелей: {len(snapshot['panel_heights'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
