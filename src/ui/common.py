"""Мелкие общие детали UI: доменные ошибки, направление текста, подписи словарей.

Направление живёт на **трёх уровнях** (наряд 0007, §4), а не одной глобальной
настройкой приложения:

* **шасси** — навигация, кнопки, заголовки, рамки диалогов — жёстко LTR
  (`app.setLayoutDirection`, `app.py`);
* **ячейка / поле данных** — по содержимому: `DirectionalDelegate` для таблиц,
  `bind_direction` для редакторов свободного текста;
* **вкрапление** — чужой по направлению токен внутри строки — изолят (`iso`).

Уровня «ячейка» до наряда 0007 в коде не было вовсе: направление было одно на всё
приложение, и ивритские данные держались только тем, что окно было RTL.
"""

from __future__ import annotations

import re
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QStyledItemDelegate, QWidget

from db.models import Direction
from domain.errors import DomainError

LTR = Qt.LayoutDirection.LeftToRight
RTL = Qt.LayoutDirection.RightToLeft


def show_error(parent: QWidget | None, error: Exception, title: str = "Not saved") -> None:
    """Показать ошибку оператору.

    Текст `DomainError` пишется в домене для оператора — показываем как есть.
    Всё остальное — неожиданная ошибка, её текст показываем с пометкой.
    """
    if isinstance(error, DomainError):
        QMessageBox.warning(parent, title, str(error))
    else:
        QMessageBox.critical(parent, "Error", f"Unexpected error:\n{error}")


# --- направление по содержимому ---------------------------------------------------

#: Классы bidi сильных символов: `R` — иврит, `AL` — арабский.
_STRONG_RTL = frozenset({"R", "AL"})


def first_strong(text: str) -> Qt.LayoutDirection | None:
    """Направление по **первому сильному** символу; `None` — сильных нет.

    Тот же критерий, что у изолята `U+2068` (first-strong-isolate), поэтому
    ячейка и её внутренние вкрапления не спорят друг с другом.
    """
    for char in text or "":
        category = unicodedata.bidirectional(char)
        if category == "L":
            return LTR
        if category in _STRONG_RTL:
            return RTL
    return None


def base_direction(text: str, default: Qt.LayoutDirection = LTR) -> Qt.LayoutDirection:
    """Базовое направление строки; строка без сильных символов берёт `default`.

    Чисто числовая строка (`19.08.2026`, `± 0.05`) сильных символов не содержит —
    и остаётся LTR, как её и читают.
    """
    return first_strong(text) or default


def is_rtl(text: str) -> bool:
    return base_direction(text) == RTL


def apply_rtl(widget: QWidget) -> QWidget:
    """Развернуть виджет справа налево — точечный инструмент для ивритского поля.

    До наряда 0007 был «подстраховкой под RTL-приложение»; шасси теперь LTR,
    поэтому RTL ставится осознанно и только там, где содержимое ивритское.
    """
    widget.setLayoutDirection(RTL)
    return widget


def numeric_field(widget: QWidget) -> QWidget:
    """Заставить поле с латинско-цифровым содержимым рисоваться слева направо.

    Изолят (`iso`) спасает только текст, который мы формируем сами. Внутри
    редакторов — `QDateEdit`, `QSpinBox` — текст рисует Qt, обернуть его нечем, и
    числовые группы, разделённые нейтральными символами, переставляются:
    `19.08.2026` показывается как `2026.08.19`, а оператор читает это как дату.
    Разворачиваем сам виджет; признак применения — «содержимое гарантированно
    латинско-цифровое» (дата, количество, допуск, величина), а не «окно RTL».
    """
    widget.setLayoutDirection(LTR)
    return widget


def apply_direction(widget: QWidget, text: str) -> QWidget:
    """Направление виджета по переданному содержимому (разовая установка)."""
    widget.setLayoutDirection(base_direction(text))
    return widget


def bind_direction(widget: QWidget) -> QWidget:
    """Редактор свободного текста: направление следует за тем, что набирают.

    Ни LTR, ни RTL не форсируется (наряд 0007, §4а) — оператор пишет на иврите
    или на английском, и поле разворачивается под первый сильный символ уже
    введённого текста. Поддержаны `QLineEdit` и `QPlainTextEdit`.
    """
    read = widget.toPlainText if hasattr(widget, "toPlainText") else widget.text

    def sync(*_args) -> None:
        widget.setLayoutDirection(base_direction(read()))

    widget.textChanged.connect(sync)
    sync()
    return widget


class DirectionalDelegate(QStyledItemDelegate):
    """Направление и выравнивание ячейки таблицы — **по её значению**.

    Первый сильный символ иврит → RTL и выравнивание вправо; латиница → LTR и
    влево. Числовые колонки (дата, количество, величина, счётчик) заданы списком
    и всегда LTR: сильных символов у них нет, а базу они обязаны иметь свою — не
    от соседа-иврита по строке.
    """

    def __init__(
        self, numeric_columns: tuple[int, ...] = (), parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._numeric = frozenset(numeric_columns)

    def initStyleOption(self, option, index) -> None:  # noqa: N802 - имя от Qt
        super().initStyleOption(option, index)
        vertical = Qt.AlignmentFlag.AlignVCenter
        if index.column() in self._numeric or not is_rtl(option.text):
            option.direction = LTR
            option.displayAlignment = Qt.AlignmentFlag.AlignLeft | vertical
        else:
            option.direction = RTL
            option.displayAlignment = Qt.AlignmentFlag.AlignRight | vertical


def directional(table, numeric_columns: tuple[int, ...] = ()):
    """Повесить на таблицу делегат направления. Возвращает саму таблицу."""
    table.setItemDelegate(DirectionalDelegate(numeric_columns, table))
    return table


# U+2068 FIRST STRONG ISOLATE … U+2069 POP DIRECTIONAL ISOLATE
_FSI, _PDI = "⁨", "⁩"


def iso(text: str) -> str:
    """Изолировать строку, сохранив её внутренний порядок.

    Изолят прижимает направление по первому сильному символу внутри, поэтому
    работает в обе стороны: и латинская подпись внутри ивритской ячейки, и
    ивритское слово внутри английской фразы. Без него хвостовая пунктуация и
    ведущие знаки уезжают не туда: `Add item…` рисуется как `…Add item`, а
    допуск `+0.05 / -0.05` — как `0.05- / 0.05+`.

    Изолят **один — вокруг собранной строки** (ратификация S5): два изолята
    подряд остаются двумя runs и в RTL-контексте раскладываются справа налево.
    Строка из нескольких самостоятельных токенов собирается через `joined`.
    """
    return f"{_FSI}{text}{_PDI}"


def joined(*parts: str, sep: str = " · ") -> str:
    """Собрать ячейку из токенов: каждый в своём изоляте, порядок — за базой.

    Отличается от `iso` вокруг готовой строки тем, что каждый токен держит своё
    внутреннее направление сам, а порядок токенов достаётся базовому направлению
    ячейки (делегат). Это и есть механизм смешанной ячейки «иврит + английский
    термин + число» (наряд 0007, §4а); точное правило снимается прогоном.
    """
    return sep.join(iso(part) for part in parts if part)


def strip_iso(text: str) -> str:
    """Снять изоляты — текст из редактируемой ячейки приходит вместе с ними."""
    return (text or "").replace(_FSI, "").replace(_PDI, "")


# --- Подписи контролируемых словарей (наряды 0004, 0007) --------------------------

#: Исходы отклонения — подписи из `model/Deviation.md` (Outcomes).
#: Порядок фиксирован: он же порядок списка в диалоге решения.
DECISION_DEV_LABELS = {
    "approved": "Approved — use as is",
    "rejected": "Rejected — scrap",
    "sorting": "Sorting — 100 % inspection",
    "repair": "Repair — legalised deviation",
}

#: `decision_dev IS NULL` — регистрация прошла, шаг 8 ещё нет.
NO_DECISION_LABEL = "no decision yet"

#: Вердикт исследования. Отвечает «можно ли принять это отклонение», а не «что
#: делать с партией» — потому и формулировки такие.
DECISION_INSP_LABELS = {
    "approved": "Deviation approved",
    "not_approved": "Deviation not approved",
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
    рядом с ивритской ячейкой иначе прилипает не той стороной.
    """
    return iso("+" if direction == Direction.PLUS else "−")


def number_label(value: float | None) -> str:
    """Величина для показа: пусто вместо `None`, ведущий минус в изоляте."""
    return "" if value is None else iso(f"{value:g}")


def dimension_sort_key(local_number: str) -> tuple:
    """Порядок номеров размеров: «9» раньше «10», а не наоборот.

    Номер — строка (канон допускает буквенные `AA`/`AB` для состояний до и после
    электрополировки), поэтому обычная сортировка текстом ставит «10» перед «9».
    Разбиваем на цифровые и нецифровые куски и числа сравниваем числами.
    """
    parts = re.split(r"(\d+)", (local_number or "").strip())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part)
