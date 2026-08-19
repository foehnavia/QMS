"""Стенд смешанных строк — критерий 6 наряда 0007 (QMS-016).

Точное правило для ивритско-английско-числовой ячейки наряд намеренно **не
задаёт**: ратификация S5 («изолят один — вокруг собранной строки») выведена на
однородной строке `− 0.05` и на смешанной ячейке не проверялась. Стенд ставит
рядом три способа собрать одну и ту же ячейку и показывает их живьём:

* **raw** — строка как есть; направление ячейке даёт делегат (`DirectionalDelegate`);
* **iso** — один изолят вокруг всей собранной строки (правило S5 дословно);
* **joined** — каждый самостоятельный токен в своём изоляте (`ui.common.joined`).

Запуск (нативная платформа, окна на экран не всплывают):

    python tools/bidi_stand.py            # снимки в build/screens/
    python tools/bidi_stand.py --show     # то же, но окно видно глазами

Снимок делается **без** `show()`: раскладку доводит `layout().activate()`.
Offscreen для снимков непригоден — база шрифтов пуста, иврит выходит «тофу»
(`CLAUDE.md` §9).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.common import LTR, base_direction, bind_direction, directional, iso, joined  # noqa: E402

OUT = REPO_ROOT / "build" / "screens"

#: Корпус стенда — **реальные по форме** значения из производственного оборота:
#: ивритский текст, английский технический термин, число со знаком, хвостовая
#: пунктуация и скобки. Отдельные значения не sensitive (`CLAUDE.md` §6);
#: собранного документа здесь нет и быть не может.
#:
#: Каждая строка — `(что это, токены ячейки)`. Токены — то, из чего ячейку
#: собирает наш код; для `raw` и `iso` они склеиваются через « · ».
CORPUS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("zone (Hebrew only)", ("אזור הברגה",)),
    ("deviation type (Hebrew only)", ("זיז בהברגה",)),
    ("Hebrew + English term", ("אזור הברגה", "thread burr")),
    ("Hebrew + term + value", ("אזור הברגה", "thread burr", "− 0.05")),
    ("Hebrew + item + WO", ("סטייה בקוטר", "C1-08375A", "WO W26007336")),
    ("characteristic + g-position", ("12", "g5")),
    ("English + Hebrew tail", ("thread length", "מדיד")),
    ("Hebrew with trailing dot", ("נמדד בשלוש נקודות.",)),
    ("Hebrew with parentheses", ("נמדד בשלוש נקודות (12, 19, 23)",)),
    ("Hebrew + signed value + unit", ("חריגה מעל MAX", "− 0.05 mm")),
    ("Hebrew + diameter", ("קוטר פנימי", "⌀ 3.75", "+0.02 / −0.05")),
    ("mixed sentence", ('אין השפעה על ההרכבה — נבדק ב-Solidworks assembly, 0.05 מ"מ',)),
    ("numbers only", ("19.08.2026",)),
    ("signed value only", ("− 0.05",)),
)

TABLE_COLUMNS = ("case", "raw", "iso(whole)", "joined(tokens)", "base")

#: Отдельный сюжет — **атомарный** токен, внутри которого сильных символов нет.
#: На нём выведена ратификация S5: два изолята подряд остаются двумя runs и в
#: RTL-контексте раскладываются справа налево. Держим рядом с корпусом, чтобы
#: «один изолят» и «изолят на токен» не путались между собой.
ATOMIC_COLUMNS = ("case", "two isolates (wrong)", "one isolate (S5)", "neighbour")

ATOMIC: tuple[tuple[str, str, str], ...] = (
    ("signed value", "−", "0.05"),
    ("tolerance pair", "+0.02", "/ −0.05"),
    ("diameter", "⌀", "3.75"),
)


def _direction_name(text: str) -> str:
    return "LTR" if base_direction(text) == LTR else "RTL"


def build_table() -> QTableWidget:
    """Три способа собрать ячейку — рядом, в одной таблице с делегатом."""
    table = QTableWidget(len(CORPUS), len(TABLE_COLUMNS))
    table.setHorizontalHeaderLabels(TABLE_COLUMNS)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    # Колонка «case» и колонка «base» — служебные, английские: их держим LTR,
    # чтобы подпись строки не переворачивалась вслед за образцом.
    directional(table, numeric_columns=(0, 4))

    for row, (case, tokens) in enumerate(CORPUS):
        plain = " · ".join(tokens)
        values = (case, plain, iso(plain), joined(*tokens), _direction_name(plain))
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))

    table.resizeRowsToContents()
    return table


def build_atomic_table() -> QTableWidget:
    """Атомарный токен: один изолят против двух подряд, рядом с ивритским соседом."""
    table = QTableWidget(len(ATOMIC), len(ATOMIC_COLUMNS))
    table.setHorizontalHeaderLabels(ATOMIC_COLUMNS)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    directional(table, numeric_columns=(0,))

    for row, (case, left, right) in enumerate(ATOMIC):
        # Сосед-иврит в той же ячейке — иначе RTL-контекста нет и оба варианта
        # выглядят одинаково: дефект S5 виден только рядом с ивритом.
        neighbour = "אזור הברגה"
        two = f"{neighbour} {iso(left)}{iso(right)}"
        one = f"{neighbour} {iso(f'{left} {right}')}"
        for column, value in enumerate((case, two, one, neighbour)):
            table.setItem(row, column, QTableWidgetItem(value))

    table.resizeRowsToContents()
    return table


def build_editors() -> QGroupBox:
    """Те же строки в редакторах: направление следует за содержимым."""
    box = QGroupBox("Editors — direction follows the content (bind_direction)")
    form = QFormLayout(box)

    hebrew = bind_direction(QLineEdit())
    hebrew.setText("אזור הברגה")
    latin = bind_direction(QLineEdit())
    latin.setText("thread burr")
    mixed = bind_direction(QPlainTextEdit())
    mixed.setPlainText('אין השפעה על ההרכבה — נבדק ב-Solidworks assembly, 0.05 מ"מ')
    mixed.setFixedHeight(60)
    latin_first = bind_direction(QPlainTextEdit())
    latin_first.setPlainText("Solidworks assembly — אין השפעה על ההרכבה, 0.05 mm")
    latin_first.setFixedHeight(60)

    form.addRow("Hebrew value:", hebrew)
    form.addRow("Latin value:", latin)
    form.addRow("Hebrew-first free text:", mixed)
    form.addRow("Latin-first free text:", latin_first)
    return box


def build_stand() -> QWidget:
    stand = QWidget()
    stand.setWindowTitle("MIS-QMS — bidi stand (QMS-016 / naryad 0007)")
    stand.resize(1400, 1080)

    caption = QLabel(
        "Mixed Hebrew + English + numeric cells. Compare the three columns: "
        "the rule for a mixed cell is read off this stand, not guessed."
    )
    caption.setWordWrap(True)

    atomic_caption = QLabel(
        "Atomic token (no strong character inside) next to Hebrew — the S5 case."
    )
    atomic_caption.setWordWrap(True)

    layout = QVBoxLayout(stand)
    layout.addWidget(caption)
    layout.addWidget(build_table(), 1)
    layout.addWidget(atomic_caption)
    layout.addWidget(build_atomic_table())
    layout.addWidget(build_editors())
    return stand


def shoot(widget: QWidget, name: str) -> Path:
    """Снять виджет в PNG. Без `show()` — раскладку доводит `activate()`."""
    OUT.mkdir(parents=True, exist_ok=True)
    widget.layout().activate()
    path = OUT / f"{name}.png"
    widget.grab().save(str(path))
    return path


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    app = QApplication.instance() or QApplication([])
    # Шасси LTR — как в боевом запуске (`app.py`).
    app.setLayoutDirection(LTR)

    stand = build_stand()
    if "--show" in argv:
        stand.show()
        return app.exec()

    print(f"bidi stand -> {shoot(stand, 'bidi-stand')}")
    for case, tokens in CORPUS:
        plain = " · ".join(tokens)
        print(f"  {_direction_name(plain):3s}  {case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
