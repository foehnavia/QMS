"""Ореол фокуса — то, чего лист стиля дать не может.

Канон §3: фокус — рамка 1 px `blue-600` **плюс ореол 3 px** `blue-halo`, и при
этом **ни одного пикселя смещения**: раскладка при обходе по Tab не дёргается.

Рамку даёт QSS (`:focus { border-color }`), ореол — нет: `outline` в Qt Style
Sheets не поддерживается. Это не рассуждение, а замер (наряд 0012): у поля в
фокусе 548 пикселей цвета рамки и **ноль** пикселей цвета ореола. Лист стиля
объявлял ореол, которого на экране не было, — ровно тот класс дефекта, ради
которого заведена конвенция «сверяй то, чем рисуют, а не подпись рядом».

Поэтому ореол рисует отдельный виджет-накладка: он лежит поверх поля, но
красит только полосу по краю, середина остаётся прозрачной. Размер самого
контрола не меняется — накладка живёт в координатах родителя и в раскладке не
участвует.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from . import tokens as t

#: Контролы, у которых фокус виден оператору. Таблица и список сюда не входят:
#: у них фокус показывает выбранная строка, а не ореол вокруг всей таблицы.
HALOED = (
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QComboBox,
    QSpinBox,
    QDateEdit,
    QPushButton,
)


class FocusHalo(QWidget):
    """Полоса `blue-halo` по краю контрола; середина прозрачна."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802 — имя от Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(t.BLUE_HALO), t.FOCUS_HALO_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = t.FOCUS_HALO_WIDTH / 2
        painter.drawRoundedRect(
            self.rect().adjusted(inset, inset, -inset, -inset),
            t.RADIUS_CONTROL + inset,
            t.RADIUS_CONTROL + inset,
        )


class FocusHaloController(QObject):
    """Держит одну накладку и переставляет её за фокусом.

    Накладка одна на приложение: одновременно сфокусирован ровно один контрол,
    и заводить по виджету на каждое поле незачем.
    """

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._halo: FocusHalo | None = None
        app.focusChanged.connect(self._follow)

    def _follow(self, _old: QWidget | None, new: QWidget | None) -> None:
        if self._halo is not None:
            self._halo.hide()
            self._halo.setParent(None)
            self._halo.deleteLater()
            self._halo = None

        if new is None or not isinstance(new, HALOED) or new.parentWidget() is None:
            return
        # Контрол без рамки ореола не получает: у плоской кнопки ленты его
        # некуда положить, и он читался бы как чужая рамка на тёмном фоне.
        if new.property("role") in ("ribbon-item",):
            return

        halo = FocusHalo(new.parentWidget())
        geometry = new.geometry().adjusted(
            -t.FOCUS_HALO_WIDTH,
            -t.FOCUS_HALO_WIDTH,
            t.FOCUS_HALO_WIDTH,
            t.FOCUS_HALO_WIDTH,
        )
        halo.setGeometry(geometry)
        halo.show()
        # Ниже самого контрола: полоса выходит за его край, а середину рисует он.
        halo.stackUnder(new)
        self._halo = halo


def install(app: QApplication) -> FocusHaloController:
    """Повесить ореол на приложение. Зовётся один раз, из `apply_theme`."""
    existing = app.findChild(FocusHaloController)
    if existing is not None:
        return existing
    return FocusHaloController(app)
