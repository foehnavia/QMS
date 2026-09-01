"""Бейдж состояния решения — пилюля канона §1.

Два правила, которые здесь не украшение:

* **Контурная пилюля ровно одна** — «решения ещё нет». Четыре исхода это
  принятые факты и читаются заливкой; незалитая форма читается как незакрытое
  дело при взгляде вниз по столбцу.
* **Цвет никогда не несёт смысл один.** Слово стоит в пилюле всегда, поэтому
  колонка переживает монохромную печать и читателя с дальтонизмом.

Рисуется делегатом, а не размеченным текстом: `QTableWidgetItem` не умеет ни
скруглений, ни точки, а вставлять в ячейку виджет значит завести по виджету на
строку — на списке в тысячу отклонений это заметно.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QLabel, QStyledItemDelegate, QWidget

from . import tokens as t
from .direction import LTR

#: Роль, под которой ячейка несёт **код** исхода (`approved`, … или `None`).
#: Подпись в `DisplayRole` человеческая и переводится, код — нет.
DECISION_ROLE = Qt.ItemDataRole.UserRole + 1


def _pen_and_brush(code: str | None) -> tuple[str | None, str, str]:
    return t.DECISION_COLOURS.get(code, t.DECISION_COLOURS[None])


class DecisionPillDelegate(QStyledItemDelegate):
    """Рисует подпись исхода пилюлей. Вешается на **одну** колонку таблицы.

    Ставится через `setItemDelegateForColumn`, поверх общего делегата
    направления: колонка исхода английская и всегда LTR, спорить им не о чем.
    """

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 — имя от Qt
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        code = index.data(DECISION_ROLE)
        background, foreground, dot = _pen_and_brush(code)

        style_option = option
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style_option.direction = LTR
        widget = style_option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(style.ControlElement.CE_ItemViewItem, style_option, painter, widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        font = QFont(option.font)
        font.setPointSizeF(t.SIZE_PILL)
        font.setWeight(QFont.Weight(t.WEIGHT_PILL))
        painter.setFont(font)

        metrics = painter.fontMetrics()
        label_width = metrics.horizontalAdvance(text)
        width = label_width + t.PAD_CELL * 2 + t.GAP_PILL_ICON * 2
        rect = option.rect
        pill = QRectF(
            rect.left() + t.PAD_CELL,
            rect.center().y() - t.PILL_HEIGHT / 2,
            min(width, rect.width() - t.PAD_CELL * 2),
            t.PILL_HEIGHT,
        )

        if background is None:
            # Открытое состояние: пунктирный контур, заливки нет.
            pen = QPen(QColor(t.PILL_DASH))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(t.BORDER_WIDTH)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(background))
        painter.drawRoundedRect(pill, t.RADIUS_PILL, t.RADIUS_PILL)

        centre = pill.center()
        radius = t.GAP_PILL_ICON / 2
        dot_rect = QRectF(
            pill.left() + t.GAP_PILL_ICON,
            centre.y() - radius,
            radius * 2,
            radius * 2,
        )
        if background is None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(dot), t.BORDER_WIDTH))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(dot))
        painter.drawEllipse(dot_rect)

        painter.setPen(QColor(foreground))
        text_rect = pill.adjusted(t.GAP_PILL_ICON * 2 + radius * 2, 0, -t.GAP_PILL_ICON, 0)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(text_rect.width())),
        )
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802 — имя от Qt
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), t.TABLE_ROW_HEIGHT))
        return size


def paint_badge(badge: QLabel, label: str, code: str | None) -> QLabel:
    """Перекрасить пилюлю под исход. Цвет зависит от **значения**, не от роли.

    Оттого стиль здесь локальный: селектором по роли «зелёный, если одобрено»
    не выражается. Значения всё равно из токенов, и живёт это в `kit`, а не на
    экране, — иначе на каждом экране заведётся своя пилюля.
    """
    background, foreground, _dot = _pen_and_brush(code)
    border = (
        f"{t.BORDER_WIDTH}px dashed {t.PILL_DASH}"
        if background is None
        else f"{t.BORDER_WIDTH}px solid {background}"
    )
    badge.setText(label)
    badge.setStyleSheet(
        f"background: {background or 'transparent'};"
        f"color: {foreground};"
        f"border: {border};"
        f"border-radius: {t.RADIUS_PILL}px;"
        f"padding: 0px {t.PAD_CELL}px;"
        f"font-size: {t.SIZE_PILL}pt;"
        f"font-weight: {t.WEIGHT_PILL};"
    )
    return badge


def decision_badge(label: str, code: str | None, parent: QWidget | None = None) -> QLabel:
    """Та же пилюля отдельной подписью — для шапки карточки, где строки нет."""
    badge = QLabel(parent)
    badge.setLayoutDirection(LTR)
    badge.setFixedHeight(t.PILL_HEIGHT)
    return paint_badge(badge, label, code)
