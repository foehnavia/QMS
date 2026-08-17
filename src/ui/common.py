"""Мелкие общие детали UI: показ доменных ошибок, RTL-хелперы, подписи словарей."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from db.models import Direction
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


def strip_iso(text: str) -> str:
    """Снять изоляты — текст из редактируемой ячейки приходит вместе с ними."""
    return (text or "").replace(_FSI, "").replace(_PDI, "")


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


# --- Подписи контролируемых словарей (наряд 0004) ---------------------------------

#: Исходы отклонения — человеческие подписи из `model/Deviation.md` (Outcomes).
#: Порядок фиксирован: он же порядок списка в диалоге решения.
DECISION_DEV_LABELS = {
    "approved": "Одобрено — использовать как есть",
    "rejected": "Не одобрено — брак",
    "sorting": "Сортировка — 100 % контроль",
    "repair": "Ремонт — узаконенное отклонение",
}

#: `decision_dev IS NULL` — регистрация прошла, шаг 8 ещё нет.
NO_DECISION_LABEL = "решение не принято"

#: Вердикт исследования. Отвечает «можно ли принять это отклонение»,
#: а не «что делать с партией» — потому и формулировки такие.
DECISION_INSP_LABELS = {
    "approved": "Отклонение одобрено",
    "not_approved": "Отклонение не одобрено",
}


def decision_dev_label(decision: str | None) -> str:
    """Подпись исхода отклонения; `None` — «решение не принято»."""
    if decision is None:
        return NO_DECISION_LABEL
    return DECISION_DEV_LABELS.get(decision, decision)


def direction_label(direction: str) -> str:
    """Знак направления для показа: типографский минус, всегда в изоляте.

    В базе хранится ASCII-дефис (единая точка для парсера S6), а оператору
    показываем `−` (U+2212), как пишет канон. Изолят обязателен: одиночный знак
    в RTL-строке иначе прилипает к соседней ячейке не той стороной.
    """
    return iso("+" if direction == Direction.PLUS else "−")


def number_label(value: float | None) -> str:
    """Величина для показа: пусто вместо `None`, ведущий минус в изоляте."""
    return "" if value is None else iso(f"{value:g}")


def ltr_field(widget: QWidget) -> QWidget:
    """Заставить поле с числовым содержимым рисоваться слева направо.

    Изолят (`iso`) спасает только текст, который мы формируем сами. Внутри
    редакторов — `QDateEdit`, `QSpinBox` — текст рисует Qt, обернуть его нечем, и
    в RTL-окне числовые группы, разделённые нейтральными символами,
    переставляются: `17.08.2026` показывается как `2026.08.17`, а оператор
    читает это как дату. Разворачиваем сам виджет — содержимое у него
    гарантированно латинско-цифровое.
    """
    widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    return widget


def dimension_sort_key(local_number: str) -> tuple:
    """Порядок номеров размеров: «9» раньше «10», а не наоборот.

    Номер — строка (канон допускает буквенные `AA`/`AB` для состояний до и после
    электрополировки), поэтому обычная сортировка текстом ставит «10» перед «9».
    Разбиваем на цифровые и нецифровые куски и числа сравниваем числами.
    """
    parts = re.split(r"(\d+)", (local_number or "").strip())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part)
