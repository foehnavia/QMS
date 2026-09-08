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

С наряда `0032` замеряется и **карточка**: высоты её секций и ширины колонок
таблицы прецедентов. Повод тот же — «высоту раздаёт содержимое» проверяется
разницей между двумя состояниями кода, а не сегодняшним числом.

    python tools/grid_probe.py build/grid-before.json
    python tools/grid_probe.py build/grid-after.json
    python tools/grid_probe.py --diff build/grid-before.json build/grid-after.json

    python tools/grid_probe.py --card build/card-before.json [высота окна]
    python tools/grid_probe.py --diff build/card-before.json build/card-after.json
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



def measure_card(window_height: int = 960) -> dict:
    """Снять высоты секций карточки и сетку таблицы прецедентов.

    **Что именно меряется и почему это.** Наряд `0032` требует: высоту раздаёт
    содержимое, а растягивается ровно одна область. Оба утверждения проверяются
    только числами: «секция занимает свою высоту» — это высота коробки против
    высоты её содержимого, а «растягивается одна» — это то, как высоты меняются
    при росте окна. Поэтому снимаются высоты всех коробок диалога, а не одна.

    Данные — демонстрационные, той же сборкой, что у снимков: карточка на пустой
    базе не показала бы ни строк находок, ни прецедентов, а весь вопрос про них.
    """
    from PySide6.QtWidgets import QApplication, QGroupBox

    from screenshots import build_database  # noqa: PLC0415

    app = QApplication.instance() or QApplication([])

    from ui.card_dialog import CardDialog  # noqa: PLC0415
    from ui.kit import apply_theme, tokens  # noqa: PLC0415

    apply_theme(app)
    engine, _url, ids = build_database()
    # **Две** карточки, а не одна: критерий 2 наряда `0032` — про отклонение с
    # **одной** находкой, а демонстрационное текущее их несёт три. Мерить надо
    # то, о чём спрашивают, и обе разом — иначе сравнивать пришлось бы файлы,
    # снятые в разное время.
    return {
        "three_findings": _measure_one(engine, ids["current_id"], window_height),
        "one_finding": _measure_one(engine, ids["past_id"], window_height),
    }


def _measure_one(engine, deviation_id: int, window_height: int) -> dict:
    from PySide6.QtWidgets import QGroupBox  # noqa: PLC0415

    from ui.card_dialog import CardDialog  # noqa: PLC0415
    from ui.kit import tokens  # noqa: PLC0415

    card = CardDialog(engine, deviation_id)
    card.resize(tokens.DIALOG_FULL, window_height)
    _settle(card)

    tables = _precedent_tables(card)
    for table in tables:
        for row in range(table.rowCount() - 1, -1, -1):
            # Снизу вверх: раскрытие вставляет служебную строку и сдвигает всё,
            # что ниже.
            if not table.is_panel_row(row) and not _is_group_row(table, row):
                table.toggle_expansion(row)
    _settle(card)

    boxes = {
        box.title(): box.height() for box in card.findChildren(QGroupBox) if box.title()
    }
    return {
        "window": [card.width(), card.height()],
        "boxes": boxes,
        "findings_table": card.findings.height(),
        "findings_rows": card.findings.rowCount(),
        "inspections_table": card.inspections.height(),
        "inspections_visible": not card.inspections.isHidden(),
        "tabs": card.tabs.height(),
        "precedent_columns": _precedent_columns(tables),
        "precedent_sum": sum(_precedent_columns(tables).values()),
        "precedent_scrolls_sideways": _scrolls_sideways(tables),
        "tab_scrolls_sideways": _tab_scroll(card),
        "panel_header": _panel_header(tables),
    }



def _settle(widget) -> None:
    """Довести раскладку до той, что увидит оператор.

    Одного `activate()` мало, и это **замерено**: без прохода отрисовки полотно
    таблицы прецедентов отдавало 638 px вместо 1136 — вложенная в прокрутку
    вкладка своей ширины ещё не знала. Тот же приём, что в `screenshots.shoot`:
    активировать, дослать `resizeEvent`, прокрутить очередь и **нарисовать**.
    Без последнего шага замер описывает промежуточное состояние раскладки, а не
    экран (`CLAUDE.md` §9а: сверяй то, чем рисуют).
    """
    from PySide6.QtGui import QResizeEvent  # noqa: PLC0415
    from PySide6.QtWidgets import QApplication, QWidget  # noqa: PLC0415

    layout = widget.layout()
    if layout is not None:
        layout.activate()
    size = QWidget.size(widget)
    QApplication.sendEvent(widget, QResizeEvent(size, size))
    if layout is not None:
        layout.activate()
    QApplication.processEvents()
    widget.grab()
    QApplication.processEvents()

def _precedent_tables(card) -> list:
    """Таблицы прецедентов карточки — сколько бы их ни было.

    Список, а не пара имён: наряд `0032` сливает две в одну, и замер обязан
    сниматься одинаково до и после — иначе сравнивать будет нечего.
    """
    from ui.card_dialog import PrecedentTable  # noqa: PLC0415

    return [t for t in card.findChildren(PrecedentTable)]


def _is_group_row(table, row: int) -> bool:
    checker = getattr(table, "is_group_row", None)
    return bool(checker(row)) if checker else False


def _precedent_columns(tables) -> dict:
    for table in tables:
        return {
            table.horizontalHeaderItem(index).text() or f"#{index}": table.columnWidth(index)
            for index in range(table.columnCount())
        }
    return {}



def _tab_scroll(card) -> dict:
    """Прокручивается ли вбок **вкладка** прецедентов.

    Меряется отдельно от таблиц, и это не педантизм: до наряда `0032` вбок ехала
    именно вкладка. Таблица объявляла 1448 px, прокрутка вкладки послушно давала
    ей эту ширину и ездила сама, а у самой таблицы полосы не было вовсе —
    замер по таблицам показывал бы «всё хорошо» на экране, который оператор
    таскал вбок руками. Сверяй то, чем рисуют (`CLAUDE.md` §9а).
    """
    area = card.tabs.widget(0)
    content = getattr(area, "widget", None)
    if content is None or not hasattr(area, "viewport"):
        return {}
    # **Геометрия, а не состояние полосы.** Полоса под offscreen не наблюдаема
    # честно: `isVisible` у ребёнка непоказанного окна ложно всегда (§9а.5), а
    # `isHidden` истинно только у явно спрятанного. Зато ширины — величины, и
    # содержимое шире полотна и есть «едет вбок», чем бы Qt это ни рисовал.
    inner = content().width() if content() is not None else 0
    view = area.viewport().width()
    return {"content": inner, "viewport": view, "overflow": max(inner - view, 0)}

def _scrolls_sideways(tables) -> int:
    """Сколько колонок таблицы ушло за правый край. Ноль — не прокручивается.

    Спрашиваем **саму полосу**, а не сравниваем сумму с полотном: полотно тут не
    независимая величина — `kit` центрирует колонки, подгоняя отступы полотна под
    их сумму, и сравнение двух подогнанных друг под друга чисел всегда сходится.
    Замерено: при сумме 1448 сравнение говорило «шире на 312», при 1103 —
    «уже на 1», и оба раза это было одно и то же наблюдение ни о чём.
    """
    # **`maximum` здесь считается в колонках, а не в пикселях** — у `QTableView`
    # режим прокрутки по элементам, и полоса меряет, сколько колонок ушло за
    # правый край. Это и оказалось единственной честной величиной: состояние
    # самой полосы под offscreen не наблюдаемо (`isVisible` у ребёнка
    # непоказанного окна ложно всегда — §9а.5; `isHidden` истинно только у явно
    # спрятанного), а сравнение суммы колонок с полотном не значит ничего:
    # `kit` центрирует колонки, подгоняя отступы полотна под их сумму, и два
    # подогнанных друг под друга числа сходятся при любой ширине.
    #
    # Замерено на обоих состояниях: до наряда `0032` — 7 и 4 колонки за краем,
    # после — ноль.
    return max(
        (table.horizontalScrollBar().maximum() for table in tables), default=0
    )


def _panel_header(tables) -> dict:
    """Оформление шапки раскрытой панели — то, что §4 наряда меняет."""
    for table in tables:
        for row in range(table.rowCount()):
            panel = table.panel_at(row)
            if panel is not None:
                header = panel.horizontalHeader()
                return {
                    "height": header.height(),
                    "object": panel.objectName(),
                }
    return {}

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

    if len(argv) >= 3 and argv[1] == "--card":
        target = Path(argv[2])
        height = int(argv[3]) if len(argv) > 3 else 960
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot = measure_card(height)
        target.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"-> {target}")
        for case, values in snapshot.items():
            print(f"   [{case}]")
            for key in ("window", "findings_rows", "findings_table",
                        "inspections_table", "inspections_visible", "tabs",
                        "precedent_sum", "precedent_scrolls_sideways",
                        "tab_scrolls_sideways"):
                print(f"     {key}: {values[key]}")
            for name, height in values["boxes"].items():
                print(f"     box {name[:44]!r}: {height}")
        return 0

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
