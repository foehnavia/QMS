"""Лента навигации — шасси окна вместо бокового меню.

Почему лента, а не меню слева (решение С-4 наряда 0010): боковое меню съедает
ширину, а таблица отклонений широкая, и горизонтальный скролл в ней дороже
вертикального.

**Высота всегда 44** (решение В-5). Она не следует за шириной: сжатие при 1280
горизонтальное, и уходят из ленты подписи разделов и правая строка состояния —
не пиксели высоты. Второе вертикальное состояние пришлось бы учитывать каждому
экрану, каждому снимку и каждому тесту, а выигрыш от ленты 36 — одна пятая
строки таблицы.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget

from . import tokens as t
from .direction import LTR, iso
from .theme import (
    ROLE,
    ROLE_RIBBON,
    ROLE_RIBBON_BRAND,
    ROLE_RIBBON_ITEM,
    ROLE_RIBBON_STATUS,
)

#: Ширина, ниже которой правая строка состояния уступает место разделам.
#: Не «красивое число»: это минимум окна по канону — до него лента полная.
COMPACT_WIDTH = t.WINDOW_MIN_WIDTH


class NavigationRibbon(QWidget):
    """Бренд слева, разделы по центру, строка состояния справа.

    Разделы будущих спринтов показываются **выключенными**, а не прячутся:
    порядок сборки должен быть виден оператору.
    """

    sectionSelected = Signal(int)

    def __init__(self, brand: str, status: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty(ROLE, ROLE_RIBBON)
        # Подкласс `QWidget` фон из листа стиля сам не рисует — только с этим
        # атрибутом. Без него лента оставалась белой внутри окна, хотя
        # отдельным окном рисовалась правильно.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(LTR)
        self.setFixedHeight(t.RIBBON_HEIGHT)

        self._buttons: list[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self.brand = QLabel(iso(brand))
        self.brand.setProperty(ROLE, ROLE_RIBBON_BRAND)

        self.status = QLabel(iso(status))
        self.status.setProperty(ROLE, ROLE_RIBBON_STATUS)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(t.PAD_RIBBON_H, 0, t.PAD_RIBBON_H, 0)
        self._layout.setSpacing(t.GAP_CONTROL)
        self._layout.addWidget(self.brand)
        self._layout.addSpacing(t.PAD_SCREEN)
        self._layout.addStretch(1)
        self._layout.addWidget(self.status)

    # --- сборка ------------------------------------------------------------------

    def add_section(self, title: str, *, enabled: bool = True, note: str = "") -> QPushButton:
        """Добавить раздел. `note` — пометка спринта у ещё не собранного."""
        label = f"{title}  ({note})" if note else title
        button = QPushButton(iso(label))
        button.setProperty(ROLE, ROLE_RIBBON_ITEM)
        button.setCheckable(True)
        button.setEnabled(enabled)
        if enabled:
            index = len(self._buttons)
            button.clicked.connect(lambda *_args, row=index: self.select(row))
            self._group.addButton(button, index)
            self._buttons.append(button)
        # Перед растяжкой и строкой состояния: разделы идут за брендом.
        self._layout.insertWidget(self._layout.count() - 2, button)
        return button

    # --- состояние ----------------------------------------------------------------

    def select(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self.sectionSelected.emit(index)

    def current_index(self) -> int:
        for index, button in enumerate(self._buttons):
            if button.isChecked():
                return index
        return -1

    def set_status(self, text: str) -> None:
        self.status.setText(iso(text))

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя от Qt
        """Сжатие горизонтальное: уходит строка состояния, высота не меняется."""
        super().resizeEvent(event)
        self.status.setVisible(self.width() >= COMPACT_WIDTH)
