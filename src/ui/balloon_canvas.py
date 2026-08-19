"""Холст с чертежом и баллонами `g1…gN` — общий для редактора CG и привязки.

Координаты баллонов **нормализованы 0..1** относительно картинки, поэтому при
смене размера окна и при замене чертежа на скан другого разрешения баллоны
остаются на тех же местах чертежа (заметка А наряда 0003).

Группа без чертежа обязана работать: баллоны раскладываются сеткой, всё
остальное — как обычно.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .common import iso

#: Режимы: перетаскивание баллонов (редактор CG) и выбор баллона (привязка).
MODE_EDIT = "edit"
MODE_SELECT = "select"

BALLOON_RADIUS = 16
MARGIN = 12

#: Раскраска состояний. `linked` — ярко-зелёный (Session-03 §4).
COLORS = {
    "neutral": (QColor("#f5f5f5"), QColor("#5c5c5c")),
    "linked": (QColor("#43a047"), QColor("#1b5e20")),
    "absent": (QColor("#9e9e9e"), QColor("#424242")),
}


@dataclass
class Balloon:
    """Баллон на холсте. `x`/`y` = None — позиция ещё не задана, идёт в сетку."""

    g_index: int
    x: float | None = None
    y: float | None = None
    state: str = "neutral"
    label: str | None = None


class BalloonCanvas(QWidget):
    """Чертёж + баллоны. Сигналит о перетаскивании и о клике."""

    balloonMoved = Signal(int, float, float)  # g_index, x, y
    balloonClicked = Signal(int)  # g_index

    def __init__(self, mode: str = MODE_SELECT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._pixmap: QPixmap | None = None
        self._balloons: list[Balloon] = []
        self._dragging: int | None = None
        self._selected: int | None = None
        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)

    # --- содержимое ------------------------------------------------------------

    def set_drawing(self, data: bytes | None) -> bool:
        """Показать чертёж. Возвращает False, если картинка не читается Qt."""
        if not data:
            self._pixmap = None
            self.update()
            return True
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._pixmap = None
            self.update()
            return False
        self._pixmap = pixmap
        self.update()
        return True

    def set_balloons(self, balloons: list[Balloon]) -> None:
        self._balloons = balloons
        if self._selected is not None and all(b.g_index != self._selected for b in balloons):
            self._selected = None
        self.update()

    @property
    def balloons(self) -> list[Balloon]:
        return self._balloons

    @property
    def selected(self) -> int | None:
        return self._selected

    def select(self, g_index: int | None) -> None:
        self._selected = g_index
        self.update()

    # --- геометрия -------------------------------------------------------------

    def image_rect(self) -> QRectF:
        """Прямоугольник картинки внутри виджета (вписан, пропорции сохранены)."""
        area = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        if self._pixmap is None or self._pixmap.isNull():
            return area

        scale = min(area.width() / self._pixmap.width(), area.height() / self._pixmap.height())
        width = self._pixmap.width() * scale
        height = self._pixmap.height() * scale
        return QRectF(
            area.left() + (area.width() - width) / 2,
            area.top() + (area.height() - height) / 2,
            width,
            height,
        )

    def _grid_slot(self, index: int) -> tuple[float, float]:
        """Место в сетке для баллона без координат."""
        total = max(len(self._balloons), 1)
        columns = max(int(ceil(sqrt(total))), 1)
        rows = max(int(ceil(total / columns)), 1)
        column, row = index % columns, index // columns
        return (column + 0.5) / columns, (row + 0.5) / rows

    def _point_of(self, index: int, balloon: Balloon) -> QPointF:
        x, y = (balloon.x, balloon.y)
        if x is None or y is None:
            x, y = self._grid_slot(index)
        rect = self.image_rect()
        return QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height())

    def _normalize(self, point: QPointF) -> tuple[float, float]:
        rect = self.image_rect()
        x = (point.x() - rect.left()) / rect.width() if rect.width() else 0.0
        y = (point.y() - rect.top()) / rect.height() if rect.height() else 0.0
        return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)

    def _hit(self, point: QPointF) -> int | None:
        """Баллон под курсором (сверху вниз по порядку отрисовки)."""
        for index in reversed(range(len(self._balloons))):
            centre = self._point_of(index, self._balloons[index])
            if (centre - point).manhattanLength() <= BALLOON_RADIUS * 1.6:
                return index
        return None

    # --- отрисовка -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.image_rect()

        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
        else:
            painter.fillRect(rect, QColor("#fafafa"))
            painter.setPen(QPen(QColor("#bdbdbd"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
            painter.setPen(QColor("#9e9e9e"))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter, "No drawing loaded — balloons laid out in a grid"
            )

        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)

        for index, balloon in enumerate(self._balloons):
            centre = self._point_of(index, balloon)
            fill, border = COLORS.get(balloon.state, COLORS["neutral"])
            selected = balloon.g_index == self._selected

            painter.setBrush(fill)
            painter.setPen(QPen(border, 3 if selected else 2))
            painter.drawEllipse(centre, BALLOON_RADIUS, BALLOON_RADIUS)

            painter.setPen(QColor("#ffffff") if balloon.state != "neutral" else QColor("#212121"))
            box = QRectF(
                centre.x() - BALLOON_RADIUS,
                centre.y() - BALLOON_RADIUS,
                BALLOON_RADIUS * 2,
                BALLOON_RADIUS * 2,
            )
            # изолят: подпись LTR внутри RTL-окна (заметка Г)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, iso(f"g{balloon.g_index}"))

            if balloon.label:
                painter.setPen(QColor("#1b5e20"))
                caption = QRectF(
                    centre.x() - 60, centre.y() + BALLOON_RADIUS + 2, 120, 18
                )
                painter.drawText(caption, Qt.AlignmentFlag.AlignCenter, iso(f"#{balloon.label}"))

        painter.end()

    # --- мышь ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        index = self._hit(QPointF(event.position()))
        if index is None:
            return
        balloon = self._balloons[index]
        self._selected = balloon.g_index
        if self._mode == MODE_EDIT:
            self._dragging = index
        self.update()
        self.balloonClicked.emit(balloon.g_index)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if self._dragging is None:
            return
        balloon = self._balloons[self._dragging]
        balloon.x, balloon.y = self._normalize(QPointF(event.position()))
        self.update()
        self.balloonMoved.emit(balloon.g_index, balloon.x, balloon.y)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        self._dragging = None
