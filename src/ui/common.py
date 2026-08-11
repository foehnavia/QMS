"""Мелкие общие детали UI: показ доменных ошибок, RTL-хелперы."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from domain.errors import DomainError


def show_error(parent: QWidget | None, error: Exception, title: str = "Не сохранено") -> None:
    """Показать ошибку оператору.

    Текст `DomainError` пишется в домене для оператора — показываем как есть.
    Всё остальное — неожиданная ошибка, её текст показываем с пометкой.
    """
    if isinstance(error, DomainError):
        QMessageBox.warning(parent, title, str(error))
    else:
        QMessageBox.critical(parent, "Ошибка", f"Непредвиденная ошибка:\n{error}")


def apply_rtl(widget: QWidget) -> None:
    """Явная RTL-раскладка для виджета (приложение и так RTL — это подстраховка)."""
    widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


# U+2068 FIRST STRONG ISOLATE … U+2069 POP DIRECTIONAL ISOLATE
_FSI, _PDI = "⁨", "⁩"


def iso(text: str) -> str:
    """Изолировать строку от RTL-контекста, сохранив её внутренний порядок.

    В RTL-приложении хвостовая пунктуация и ведущие знаки уезжают не туда:
    «Добавить деталь…» рисуется как «…Добавить деталь», а допуск
    `+0.05 / -0.05` — как `0.05- / 0.05+`. Изолят прижимает направление по
    первому сильному символу, поэтому одинаково работает и для иврита.
    """
    return f"{_FSI}{text}{_PDI}"


def russian_buttons(box) -> None:
    """Подписать стандартные кнопки диалога по-русски.

    Qt берёт их из своих переводов, а переводчик в приложение не ставится —
    иначе оператор видит Save/Cancel.
    """
    from PySide6.QtWidgets import QDialogButtonBox

    labels = {
        QDialogButtonBox.StandardButton.Save: "Сохранить",
        QDialogButtonBox.StandardButton.Cancel: "Отмена",
        QDialogButtonBox.StandardButton.Ok: "ОК",
    }
    for standard, label in labels.items():
        button = box.button(standard)
        if button is not None:
            button.setText(label)
