"""Пилюля находки внутри строки отклонения — компонент `finding_chip` (§10 канона).

Отличается от пилюли исхода (`pills.py`) не оформлением, а тем, **что она несёт**.
Пилюля исхода — одно значение контролируемого словаря, и колонка отвечает на
вопрос «что решили». Пилюля находки — сама находка: номер размера, величина со
знаком, тип отклонения. Их в ячейке несколько, и высота строки от их числа
зависит — единственное место в приложении, где строка не равна 40
(`design-system.md` §3, revision 1.7).

**Значок мензурки — признак наличия, не вердикт.** Он стоит там, где у находки
есть исследования, и не меняется от их позиции: позиция читается в раскрытии,
колонкой `Research`, а свёрнутой строке нужен один признак — «есть или нет»
(решение 8 QMS-018). Красить его по позиции значило бы поднять полярный вердикт
на уровень отклонения, чего канон прямо не велит (`Inspection.md`, «Decision
independence»).

Рисуется делегатом, а не виджетами в ячейке: виджет на пилюлю дал бы по три-шесть
виджетов на строку, и на списке в тысячу отклонений это заметно — тот же довод,
по которому делегатом рисуется пилюля исхода.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from . import tokens as t
from .direction import LTR

#: Роль, под которой ячейка несёт **состав находок** строки — список `Chip`.
#: Подпись в `DisplayRole` остаётся текстовой сводкой: её читают тесты и
#: подсказка, а рисует ячейку делегат.
CHIPS_ROLE = Qt.ItemDataRole.UserRole + 2

#: Сколько пилюль видно в свёрнутой строке. Третья и далее сворачиваются в
#: строку `+N findings` — это **счётчик**, и он принят сознательно
#: (`REVIEW_deviations-screen.md` §4): главное требование, различить два
#: отклонения по одной детали не открывая карточку, выполняется уже двумя.
CHIPS_SHOWN = 2

#: Роль, под которой ячейка раскрытия несёт **состояние**, а не стрелку.
#: Рисует стрелку делегат, и берёт он состояние отсюда — не разбором подписи.
EXPANDED_ROLE = Qt.ItemDataRole.UserRole + 3


@dataclass(frozen=True)
class Chip:
    """Одна находка так, как её видно в свёрнутой строке."""

    #: `Dim. 19` — приглушённая половина подписи.
    dimension: str
    #: Величина со знаком — **одна неделимая величина**, знак в той же строке.
    value: str
    #: Тип отклонения из справочника; пусто — не указан.
    kind: str
    #: Есть ли у находки исследования. Признак наличия, не суждение.
    researched: bool
    #: Исход находки: `permitted` · `not_permitted` · `None` («ещё не решали»).
    #: Рисуется **формой**, а не цветом, и показывается всегда — см. `_outcome`.
    outcome: str | None = None

    def text(self) -> str:
        """Подпись пилюли одной строкой — она же уходит в `DisplayRole`."""
        return " · ".join(part for part in (self.dimension, self.value, self.kind) if part)


def more_findings(hidden: int) -> str:
    """Подпись свёрнутого остатка. Единственное число — не «1 findings»."""
    return f"+{hidden} finding" + ("" if hidden == 1 else "s")


def chips_text(chips: list[Chip]) -> str:
    """Текстовая сводка ячейки — то, что уходит в `DisplayRole` и в подсказку.

    Существует потому, что рисует ячейку делегат, а сравнивать в тестах и
    показывать в подсказке надо содержимое, а не картинку.
    """
    shown = [chip.text() for chip in chips[:CHIPS_SHOWN]]
    hidden = len(chips) - len(shown)
    if hidden > 0:
        shown.append(more_findings(hidden))
    return "\n".join(shown)


def row_height(findings: int) -> int:
    """Высота строки отклонения: **40 / 66 / 82** (`design-system.md` §3, rev 1.7).

    Единственное место в приложении, где строка не равна 40, — и это то самое
    исключение, вокруг которого правило и написано: строка несёт сами пилюли,
    поэтому растёт вместе с ними. Ни один другой экран этих чисел не наследует.

    Одна находка — обычная строка 40. Вторая добавляет пилюлю с зазором
    (22 + 4 = 26). Третья и далее добавляют не пилюлю, а строку `+N findings`
    (16): показанных пилюль всегда две.
    """
    if findings <= 1:
        return t.TABLE_ROW_HEIGHT
    if findings == 2:
        return t.ROW_TWO_FINDINGS
    return t.ROW_MANY_FINDINGS


class FindingChipsDelegate(QStyledItemDelegate):
    """Рисует состав находок пилюлями. Вешается на **одну** колонку таблицы."""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 — имя от Qt
        chips = index.data(CHIPS_ROLE) or []

        style_option = option
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style_option.direction = LTR
        widget = style_option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(style.ControlElement.CE_ItemViewItem, style_option, painter, widget)
        if not chips:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        font = QFont(option.font)
        font.setPointSizeF(t.SIZE_PILL)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        top = option.rect.top() + t.PAD_CHIP_ROW
        left = option.rect.left() + t.PAD_CELL
        limit = option.rect.right() - t.PAD_CELL

        for chip in chips[:CHIPS_SHOWN]:
            self._chip(painter, metrics, chip, left, top, limit)
            top += t.CHIP_HEIGHT + t.GAP_CHIP

        hidden = len(chips) - CHIPS_SHOWN
        if hidden > 0:
            painter.setPen(QColor(t.BLUE_600))
            painter.drawText(
                QRectF(left, top, limit - left, t.MORE_LINE_HEIGHT),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                more_findings(hidden),
            )
        painter.restore()

    def _chip(self, painter, metrics, chip: Chip, left: int, top: int, limit: int) -> None:
        """Одна пилюля: оправа, подпись и **две** иконки.

        Иконка исследования — только когда исследования есть; иконка исхода —
        **всегда, во всех трёх состояниях**. Пустое место на месте второй было бы
        неотличимо от «иконка не поместилась» (§3 наряда `0030`).
        """
        glyphs = t.CHIP_GLYPH_SIZE + t.GAP_PILL_ICON  # исход рисуется всегда
        if chip.researched:
            glyphs += t.CHIP_GLYPH_SIZE + t.GAP_PILL_ICON
        text = chip.text()
        width = min(
            metrics.horizontalAdvance(text) + t.PAD_CELL * 2 + glyphs,
            max(limit - left, 0),
        )
        box = QRectF(left, top, width, t.CHIP_HEIGHT)

        painter.setPen(QPen(QColor(t.N_250), t.BORDER_WIDTH))
        painter.setBrush(QColor(t.N_100))
        painter.drawRoundedRect(box, t.RADIUS_PILL, t.RADIUS_PILL)

        text_rect = box.adjusted(t.PAD_CELL, 0, -(t.PAD_CELL + glyphs), 0)
        painter.setPen(QColor(t.N_700))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(text_rect.width())),
        )
        # Исход — крайним справа: он есть у каждой пилюли, и столбик из них
        # читается взглядом вниз только при общем положении.
        self._outcome(painter, box, chip.outcome)
        if chip.researched:
            self._flask(painter, box.adjusted(0, 0, -(t.CHIP_GLYPH_SIZE + t.GAP_PILL_ICON), 0))

    def _flask(self, painter, box: QRectF) -> None:
        """Мензурка — контур, как все значки канона (§5): ни эмодзи, ни дингбат.

        Эмодзи и глифы шрифта не перекрашиваются вместе с состоянием и на каждой
        машине рисуются по-своему; здесь важно, что значок **виден** и что он
        одного цвета всегда — он говорит «есть исследования», и только это.
        """
        size = t.CHIP_GLYPH_SIZE
        right = box.right() - t.PAD_CELL
        centre_y = box.center().y()
        neck = size * 0.28
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(t.N_500), t.BORDER_WIDTH))
        top_y = centre_y - size / 2
        bottom_y = centre_y + size / 2
        left_x = right - size
        # Горлышко, два ската и дно — контур мензурки одним полилайном.
        painter.drawLine(QPointF(left_x + neck, top_y), QPointF(right - neck, top_y))
        painter.drawLine(QPointF(left_x + neck, top_y), QPointF(left_x + neck, top_y + neck))
        painter.drawLine(QPointF(right - neck, top_y), QPointF(right - neck, top_y + neck))
        painter.drawLine(QPointF(left_x + neck, top_y + neck), QPointF(left_x, bottom_y))
        painter.drawLine(QPointF(right - neck, top_y + neck), QPointF(right, bottom_y))
        painter.drawLine(QPointF(left_x, bottom_y), QPointF(right, bottom_y))

    def _outcome(self, painter, box: QRectF, outcome: str | None) -> None:
        """Исход — **формой**, а не цветом: галочка · крестик · пустой кружок.

        `design-system.md` §1: цвет никогда не несёт смысл в одиночку. Слова в
        пилюле нет и быть не может — она и заведена ради скана взглядом, — поэтому
        различать состояния обязан **контур**, а цвет только усиливает то, что уже
        прочитано. Слово живёт в подсказке ячейки.

        Три разные фигуры, а не три оттенка одной: монохромная печать и читатель
        с дальтонизмом обязаны видеть ту же разницу, что и все остальные.
        """
        size = t.CHIP_GLYPH_SIZE
        right = box.right() - t.PAD_CELL
        centre = QPointF(right - size / 2, box.center().y())
        half = size / 2

        colour = {
            "permitted": t.OUTCOME_PERMITTED,
            "not_permitted": t.OUTCOME_REFUSED,
        }.get(outcome, t.N_400)
        pen = QPen(QColor(colour), t.OUTCOME_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if outcome == "permitted":
            # Галочка: две линии, длинная вверх-вправо.
            painter.drawLine(
                QPointF(centre.x() - half * 0.8, centre.y()),
                QPointF(centre.x() - half * 0.2, centre.y() + half * 0.6),
            )
            painter.drawLine(
                QPointF(centre.x() - half * 0.2, centre.y() + half * 0.6),
                QPointF(centre.x() + half * 0.8, centre.y() - half * 0.7),
            )
        elif outcome == "not_permitted":
            # Крестик: две линии крест-накрест.
            painter.drawLine(
                QPointF(centre.x() - half * 0.7, centre.y() - half * 0.7),
                QPointF(centre.x() + half * 0.7, centre.y() + half * 0.7),
            )
            painter.drawLine(
                QPointF(centre.x() + half * 0.7, centre.y() - half * 0.7),
                QPointF(centre.x() - half * 0.7, centre.y() + half * 0.7),
            )
        else:
            # Пустой кружок: «ещё не решали» — состояние, а не отсутствие.
            painter.drawEllipse(centre, half * 0.7, half * 0.7)

    def sizeHint(self, option, index):  # noqa: N802 — имя от Qt
        size = super().sizeHint(option, index)
        chips = index.data(CHIPS_ROLE) or []
        size.setHeight(max(size.height(), row_height(len(chips))))
        return size


class ExpanderDelegate(QStyledItemDelegate):
    """Стрелка раскрытия — рисуется, а не пишется текстом ячейки.

    Колонка объявлена в 23 px, а лист стиля даёт ячейке `padding: 0 10px`: на
    подпись остаётся 3 px, и текстовая стрелка обрезается вовсе. Замечено
    замером на нативной платформе (`CLAUDE.md` §9а.8) — тест на текст ячейки
    был зелёным, потому что текст-то в ячейке есть.

    Треугольник чертится путём, а не берётся глифом и не описывается подстилем:
    подстилю Qt заливает прямоугольник сплошным и «треугольника из рамок» не
    знает (`CLAUDE.md` §9, В-6), а глиф дингбата на каждой машине свой (канон §5).
    """

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 — имя от Qt
        expanded = bool(index.data(EXPANDED_ROLE))

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
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.N_500))

        centre = option.rect.center()
        half = t.EXPANDER_ARROW / 2
        if expanded:
            points = (
                QPointF(centre.x() - half, centre.y() - half * 0.6),
                QPointF(centre.x() + half, centre.y() - half * 0.6),
                QPointF(centre.x(), centre.y() + half * 0.7),
            )
        else:
            points = (
                QPointF(centre.x() - half * 0.6, centre.y() - half),
                QPointF(centre.x() - half * 0.6, centre.y() + half),
                QPointF(centre.x() + half * 0.7, centre.y()),
            )
        painter.drawPolygon(points)
        painter.restore()
