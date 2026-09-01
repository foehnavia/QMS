"""Направление и выравнивание — механизмы, переехавшие в `kit` без смены смысла.

Приехали из `ui/common.py` (наряды 0007, 0011): здесь им место, потому что это
такая же часть дизайн-системы, как палитра, и она обязана быть одна на все
экраны. Правила не менялись — менялся адрес.

Направление живёт на **трёх уровнях** (наряд 0007 §4, канон §6):

* **шасси** — навигация, кнопки, заголовки, рамки диалогов — жёстко LTR
  (`app.setLayoutDirection`, `app.py`);
* **ячейка / поле данных** — по содержимому: `DirectionalDelegate` для таблиц,
  `bind_direction` для однострочных полей; текстовым областям Qt резолвит
  направление **по абзацу** сам (ревью Р-2);
* **вкрапление** — чужой по направлению токен внутри строки — изолят (`iso`).
"""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate, QWidget

LTR = Qt.LayoutDirection.LeftToRight
RTL = Qt.LayoutDirection.RightToLeft

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


def bind_direction(editor: QLineEdit) -> QLineEdit:
    """Однострочное поле: направление следует за тем, что набирают.

    Ни LTR, ни RTL не форсируется (наряд 0007, §4а) — оператор пишет на иврите
    или на английском, и поле разворачивается под первый сильный символ уже
    введённого текста. У `QLineEdit` базой абзаца служит именно `layoutDirection`
    виджета, поэтому здесь хелпер и нужен.

    **Только `QLineEdit`.** Текстовой области (`QPlainTextEdit`, `QTextEdit`) он не
    нужен и вреден — ревью Р-2, подтверждено исполнением:

    * направление там резолвится **по абзацу** самим Qt: `block.textDirection()`
      даёт RTL для ивритской строки и в LTR-поле, и в RTL-поле, а
      `document().defaultTextOption()` остаётся `LayoutDirectionAuto`;
    * `layoutDirection` двигает только хром — полоса прокрутки перепрыгивает на
      другую сторону, стоит набрать первый ивритский символ;
    * текстовая область держит абзацы **разных** направлений сразу (ивритское
      обоснование и латинский путь к протоколу в одном поле), поэтому одно
      направление на виджет там просто неверная единица.
    """
    if not isinstance(editor, QLineEdit):
        raise TypeError(
            "bind_direction is for QLineEdit only: a text area resolves direction "
            "per paragraph on its own (naryad 0007, review R-2)"
        )

    def sync(*_args) -> None:
        editor.setLayoutDirection(base_direction(editor.text()))

    editor.textChanged.connect(sync)
    sync()
    return editor


class DirectionalDelegate(QStyledItemDelegate):
    """Направление и выравнивание ячейки таблицы — по её значению и по колонке.

    **Направление и выравнивание — два разных вопроса** (решение Cowork по ревью
    наряда 0007, канон §6), и списки колонок у них разные.

    *Направление.* Первый сильный символ иврит → RTL, латиница → LTR.
    `numeric_columns` (дата, счётчик, идентификатор, величина) — всегда LTR:
    сильных символов у них нет, а базу они обязаны иметь свою, не от
    соседа-иврита по строке.

    *Выравнивание.* Вправо — только то, что глаз сравнивает **по величине** вниз
    по столбцу: номинал, допуски, количество отклонения, «знак · величина»
    (`magnitude_columns`). Там выравнивание ставит разряды в столбик и делает
    разброс видимым без чтения. Всё остальное — влево: у дат, счётчиков и
    номеров сравнивать нечего, а левый край держит их у подписи колонки.

    Выравнивание текстовых колонок задаётся **логически** — `AlignLeft`, то есть
    «к началу строки»: поверх него Qt накладывает
    `QStyle.visualAlignment(direction, …)`, которая под RTL сама меняет левое на
    правое. Написать `AlignRight` для ивритской ячейки значит получить после
    этого превращения выравнивание **влево** — ошибка, найденная снимком
    ивритского справочника. Для `magnitude_columns` такой двусмысленности нет:
    они всегда LTR, и `AlignRight` там означает ровно правый край.
    """

    def __init__(
        self,
        numeric_columns: tuple[int, ...] = (),
        magnitude_columns: tuple[int, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Величина — частный случай числовой колонки: перечислять её дважды
        # незачем, и рассинхронизировать два списка тоже незачем.
        self._magnitude = frozenset(magnitude_columns)
        self._numeric = frozenset(numeric_columns) | self._magnitude

    def initStyleOption(self, option, index) -> None:  # noqa: N802 - имя от Qt
        super().initStyleOption(option, index)
        column = index.column()
        numeric = column in self._numeric
        option.direction = LTR if numeric or not is_rtl(option.text) else RTL
        horizontal = (
            Qt.AlignmentFlag.AlignRight
            if column in self._magnitude
            else Qt.AlignmentFlag.AlignLeft
        )
        option.displayAlignment = horizontal | Qt.AlignmentFlag.AlignVCenter


def directional(
    table,
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
):
    """Повесить на таблицу делегат направления. Возвращает саму таблицу."""
    table.setItemDelegate(DirectionalDelegate(numeric_columns, magnitude_columns, table))
    return table


# U+2068 FIRST STRONG ISOLATE ... U+2069 POP DIRECTIONAL ISOLATE
_FSI, _PDI = "⁨", "⁩"


def iso(text: str) -> str:
    """Изолировать строку, сохранив её внутренний порядок.

    Изолят прижимает направление по первому сильному символу внутри, поэтому
    работает в обе стороны: и латинская подпись внутри ивритской ячейки, и
    ивритское слово внутри английской фразы. Без него хвостовая пунктуация и
    ведущие знаки уезжают не туда: `Add item…` рисуется как `…Add item`, а
    допуск `+0.05 / -0.05` — как `0.05- / 0.05+`.

    Изолят **один — вокруг атомарного токена** (ратификация S5, уточнение
    QMS-016): два изолята подряд остаются двумя runs и в RTL-контексте
    раскладываются справа налево. Строка из нескольких самостоятельных токенов
    собирается через `joined`.
    """
    return f"{_FSI}{text}{_PDI}"


def joined(*parts: str, sep: str = " · ") -> str:
    """Собрать ячейку из токенов: каждый в своём изоляте, порядок — за базой.

    Отличается от `iso` вокруг готовой строки тем, что каждый токен держит своё
    внутреннее направление сам, а порядок токенов достаётся базовому направлению
    ячейки (делегат). Это и есть механизм смешанной ячейки «иврит + английский
    термин + число» (наряд 0007, §4а).
    """
    return sep.join(iso(part) for part in parts if part)


def strip_iso(text: str) -> str:
    """Снять изоляты — текст из редактируемой ячейки приходит вместе с ними."""
    return (text or "").replace(_FSI, "").replace(_PDI, "")
