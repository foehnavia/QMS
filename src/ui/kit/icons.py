"""Иконки разделов — векторные, по §5 канона.

Канон §5: контурный SVG, штрих 1.7 px на сетке 24, скруглённые концы и стыки,
один стиль на всё приложение. **Ни эмодзи, ни глифов дингбатов**: они не
перекрашиваются, не масштабируются вместе со шкалой шрифта и на каждой машине
рисуются по-своему.

Цвет — часть состояния, а не часть файла: иконка раздела на ленте бывает
приглушённой, белой у текущего и приглушённой у недоступного. Поэтому SVG
собирается строкой под нужный цвет и растрируется на месте; кэш не нужен —
иконок пять, и пересобираются они только при смене раздела.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import tokens as t

#: Контуры на сетке 24 — по одному на раздел. Ровно то, что называет раздел:
#: отклонение — лист с записью, деталь — тело вращения, группа — слои общего
#: канона, справочник — книга, поиск — лупа.
PATHS = {
    "deviations": ("M6 3.5h9l4 4V20a1 1 0 01-1 1H6a1 1 0 01-1-1V4.5a1 1 0 011-1z", "M15 3.5V8h4", "M8.5 13h7", "M8.5 16.5h4.5"),
    "items": ("M12 3l7.5 4.2v9.6L12 21l-7.5-4.2V7.2z", "M4.5 7.2L12 11.5l7.5-4.3", "M12 11.5V21"),
    "groups": ("M12 3.2l8 4.3-8 4.3-8-4.3z", "M4 12l8 4.3 8-4.3", "M4 16.4l8 4.3 8-4.3"),
    "reference": ("M5 4.5h9a3 3 0 013 3V20H8a3 3 0 01-3-3z", "M17 7.5h2v12h-2", "M8.5 9h6", "M8.5 12.5h4"),
    "search": ("M11 18a7 7 0 100-14 7 7 0 000 14z", "M16.2 16.2L21 21"),
}

#: Порядок сетки и штрих — из канона §5, не из головы.
GRID = 24
STROKE = 1.7


def svg(name: str, colour: str) -> str:
    """Разметка иконки нужного цвета. Отдельно от растра — её удобно проверять."""
    paths = "".join(f'<path d="{d}"/>' for d in PATHS[name])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" '
        f'fill="none" stroke="{colour}" stroke-width="{STROKE}" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


def icon(name: str, colour: str, size: int = 16) -> QIcon:
    """Иконка раздела как `QIcon` — размер по канону §3 (16 в навигации)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(QByteArray(svg(name, colour).encode("utf-8"))).render(painter)
    painter.end()
    return QIcon(pixmap)


def nav_icon(name: str, *, active: bool, enabled: bool = True) -> QIcon:
    """Иконка ленты под состояние раздела: текущий, обычный, недоступный."""
    colour = t.RIBBON_TEXT if active else t.RIBBON_MUTED
    return icon(name, colour if enabled else t.RIBBON_MUTED)
