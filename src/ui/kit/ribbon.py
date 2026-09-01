"""Лента навигации — шасси окна вместо бокового меню.

Почему лента, а не меню слева (решение С-4 наряда 0010): боковое меню съедает
ширину, а таблица отклонений широкая, и горизонтальный скролл в ней дороже
вертикального.

**Высота всегда 44** (решение В-5). Она не следует за шириной: сжатие при 1280
горизонтальное, и уходят из ленты счётчики разделов и часть служебной строки —
не пиксели высоты. Второе вертикальное состояние пришлось бы учитывать каждому
экрану, каждому снимку и каждому тесту, а выигрыш от ленты 36 — одна пятая
строки таблицы.

**Порядок сжатия объявлен здесь и только здесь** (макет S1): сперва сокращается
служебная строка, затем уходят счётчики разделов. Подписи разделов не исчезают
ни на одном шаге — «Characteristic groups» иконкой не опознаётся.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from . import icons
from . import tokens as t
from .direction import LTR, iso
from .theme import (
    ROLE,
    ROLE_RIBBON,
    ROLE_RIBBON_BRAND,
    ROLE_RIBBON_ITEM,
    ROLE_RIBBON_MARK,
    ROLE_RIBBON_SEPARATOR,
    ROLE_RIBBON_STATUS,
)

#: Ширина, **на** которой и ниже которой лента сжата. Не «красивое число»: это
#: минимум окна по канону, и макет рисует ровно два состояния ленты — полное
#: при 1920 и сжатое при 1280 (макет S1).
COMPACT_WIDTH = t.WINDOW_MIN_WIDTH


class NavButton(QPushButton):
    """Пункт ленты, чья ширина равна его содержимому.

    Своя `sizeHint` здесь не украшение: `QPushButton` под стилем Windows берёт
    ширину из `CT_PushButton` — минимум 80 px плюс собственные поля, и пять
    разделов переставали помещаться в минимум окна 1280 (замер наряда 0012).
    Считаем по канону: отступ пункта, иконка 16, зазор 9 и сама подпись.
    """

    def sizeHint(self) -> QSize:  # noqa: N802 — имя от Qt
        width = self.fontMetrics().horizontalAdvance(self.text()) + t.PAD_NAV_ITEM * 2
        if not self.icon().isNull():
            width += t.ICON_NAV + t.GAP_NAV_ICON
        return QSize(width, t.NAV_ITEM_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — имя от Qt
        return self.sizeHint()


class NavigationRibbon(QWidget):
    """Бренд слева, разделы по центру, служебная строка справа.

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
        self._icons: list[str] = []
        self._titles: list[str] = []
        self._counts: list[str] = []
        self._status_full = status
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        # Знак приложения: квадрат с буквой, затем подпись. Не картинка — у
        # знака своя роль в стиле, а эмодзи и дингбаты канон запрещает (§5).
        self.mark = QLabel(brand[:1])
        self.mark.setProperty(ROLE, ROLE_RIBBON_MARK)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mark.setFixedSize(t.RIBBON_MARK_SIZE, t.RIBBON_MARK_SIZE)

        self.brand = QLabel(iso(brand))
        self.brand.setProperty(ROLE, ROLE_RIBBON_BRAND)

        self.separator = QFrame()
        self.separator.setProperty(ROLE, ROLE_RIBBON_SEPARATOR)
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.separator.setFixedWidth(t.BORDER_WIDTH)

        self.status = QLabel(iso(status))
        self.status.setProperty(ROLE, ROLE_RIBBON_STATUS)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(t.PAD_RIBBON_H, 0, t.PAD_RIBBON_H, 0)
        self._layout.setSpacing(t.GAP_NAV_ICON)
        self._layout.addWidget(self.mark)
        self._layout.addWidget(self.brand)
        self._layout.addWidget(self.separator)
        self._layout.addStretch(1)
        self._layout.addWidget(self.status)

    # --- сборка ------------------------------------------------------------------

    def add_section(
        self,
        title: str,
        *,
        enabled: bool = True,
        note: str = "",
        icon: str = "",
    ) -> QPushButton:
        """Добавить раздел. `note` — почему он недоступен, `icon` — имя контура."""
        # Подпись выключенного раздела говорит, **почему** он серый: всплывающей
        # подсказки на ленте нет — она там не читается (макет S1, заметка 3).
        label = f"{title} — {note}" if note else title
        button = NavButton(iso(label))
        button.setProperty(ROLE, ROLE_RIBBON_ITEM)
        button.setCheckable(True)
        button.setEnabled(enabled)
        if icon:
            button.setIcon(icons.nav_icon(icon, active=False, enabled=enabled))
            button.setIconSize(QSize(t.ICON_NAV, t.ICON_NAV))
        if enabled:
            index = len(self._buttons)
            button.clicked.connect(lambda *_args, row=index: self.select(row))
            self._group.addButton(button, index)
            self._buttons.append(button)
            self._icons.append(icon)
            self._titles.append(label)
            self._counts.append("")
        # Перед растяжкой и служебной строкой: разделы идут за брендом.
        self._layout.insertWidget(self._layout.count() - 2, button)
        return button

    # --- состояние ----------------------------------------------------------------

    def select(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self._repaint_icons()
            self.sectionSelected.emit(index)

    def current_index(self) -> int:
        for index, button in enumerate(self._buttons):
            if button.isChecked():
                return index
        return -1

    def set_status(self, text: str) -> None:
        self._status_full = text
        self._apply_compression()

    def set_count(self, index: int, count: int | None) -> None:
        """Счётчик раздела — сколько записей в его списке.

        `None` — счётчика нет вовсе: у справочников их шесть списков, и одно
        число рядом с разделом не отвечало бы ни на один вопрос.
        """
        if not 0 <= index < len(self._buttons):
            return
        self._counts[index] = "" if count is None else str(count)
        self._apply_compression()

    def section_text(self, index: int) -> str:
        """Подпись раздела как она сейчас нарисована — вместе со счётчиком."""
        return self._buttons[index].text()

    def _repaint_icons(self) -> None:
        """Иконка перекрашивается вместе с состоянием: цвет — часть состояния."""
        for index, button in enumerate(self._buttons):
            name = self._icons[index]
            if name:
                button.setIcon(icons.nav_icon(name, active=button.isChecked()))

    def _apply_compression(self) -> None:
        """Порядок сжатия ленты — один, и объявлен он здесь (макет S1)."""
        compact = self.width() <= COMPACT_WIDTH
        self.status.setText(iso(_shorten(self._status_full) if compact else self._status_full))
        for index, button in enumerate(self._buttons):
            count = "" if compact else self._counts[index]
            title = self._titles[index]
            button.setText(iso(f"{title}  {count}" if count else title))

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя от Qt
        """Сжатие горизонтальное: уходят счётчики и часть строки, высота — нет."""
        super().resizeEvent(event)
        self._apply_compression()


def _shorten(status: str) -> str:
    """Сжатая служебная строка: режим и ревизия базы, без «single station».

    Первый шаг сжатия по макету S1 — **сокращение, а не исчезновение**: из виду
    не должно уходить ни то, что станция офлайн, ни ревизия схемы под ней.
    """
    parts = [part.strip() for part in status.split("·")]
    if len(parts) <= 2:
        return status
    return " · ".join([parts[0]] + parts[2:])
