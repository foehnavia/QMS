"""`picker` — выбор одного значения из списка, со строкой отбора.

Решение В-6 (наряд 0010 §9). Запрет §3а тиражировать механики эталонного экрана
сюда не относится: он про **аппарат экрана** — поиск по выдаче, срезы, чипы,
экспорт. Отбор внутри модального диалога сужает **выбор**, а не меняет, чем
список является.

Границы, чтобы не спорить заново:

* одна строка отбора, подстрокой; ни чипов, ни срезов, ни истории;
* отбор **не выходит за пределы диалога** — под ним ничего не меняется;
* строка **скрыта при 12 значениях и меньше** — короткому списку она мешает.

Цена, названная заранее (наряд 0010): `QInputDialog.getItem` строку отбора не
вмещает, поэтому здесь собственный небольшой диалог вместо готового вызова.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import tokens as t
from .direction import bind_direction, directional
from .widgets import dialog_buttons, dialog_layout, hint


class PickerDialog(QDialog):
    """Модальный выбор из списка `(ключ, подпись)`. Результат — `chosen`."""

    def __init__(
        self,
        title: str,
        prompt: str,
        rows: list[tuple[object, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(t.DIALOG_NARROW, t.DIALOG_HEIGHT_SHORT)
        self._rows = rows
        self.chosen: object | None = None

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("type to narrow the list")
        # Подписи бывают ивритскими (значения справочников) — направление поля
        # следует за набранным, а не за окном.
        bind_direction(self.filter)
        self.filter.textChanged.connect(self._apply_filter)

        self.values = QListWidget()
        # Строка списка разворачивается по своему содержимому: каталожный номер
        # латинский, значение справочника бывает ивритским.
        directional(self.values)
        self.values.itemDoubleClicked.connect(lambda *_args: self.accept())

        self.buttons = dialog_buttons(accept="Select")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = dialog_layout(self)
        layout.addWidget(hint(prompt))
        layout.addWidget(self.filter)
        layout.addWidget(self.values, 1)
        layout.addWidget(self.buttons)

        # Короткому списку строка отбора только мешает (граница решения В-6).
        self.filter.setVisible(len(rows) > t.PICKER_FILTER_THRESHOLD)
        self._fill(rows)

    # --- список -------------------------------------------------------------------

    def _fill(self, rows: list[tuple[object, str]]) -> None:
        self.values.clear()
        for key, label in rows:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.values.addItem(item)
        if self.values.count():
            self.values.setCurrentRow(0)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().casefold()
        self._fill(
            [row for row in self._rows if not needle or needle in row[1].casefold()]
        )

    # --- результат ----------------------------------------------------------------

    def accept(self) -> None:
        item = self.values.currentItem()
        if item is None:
            return
        self.chosen = item.data(Qt.ItemDataRole.UserRole)
        super().accept()


def pick(
    parent: QWidget | None,
    title: str,
    prompt: str,
    rows: list[tuple[object, str]],
) -> object | None:
    """Открыть выбор; `None` — оператор отказался или выбирать не из чего."""
    if not rows:
        return None
    dialog = PickerDialog(title, prompt, rows, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.chosen
