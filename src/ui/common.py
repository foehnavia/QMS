"""Подписи контролируемых словарей и сборка составных значений ячейки.

Направление, изоляты и делегат переехали в `ui.kit.direction` (наряд 0011):
это часть дизайн-системы, и жить она обязана там же, где палитра и метрики.
Здесь они **реэкспортируются** — экраны и тесты зовут их привычным именем,
а адрес у механизма один.

Что осталось своим: подписи словарей и `signed_label`. Это не оформление, а
язык интерфейса — термины канона `docs/model/`, и `kit` про домен не знает.
"""

from __future__ import annotations

import re

from db.models import Direction

from .kit.direction import (
    LTR,
    RTL,
    DirectionalDelegate,
    apply_direction,
    apply_rtl,
    base_direction,
    bind_direction,
    directional,
    first_strong,
    is_rtl,
    iso,
    joined,
    numeric_field,
    strip_iso,
)
from .kit.widgets import show_error

__all__ = [
    "DECISION_DEV_LABELS",
    "DECISION_DEV_SHORT",
    "DECISION_INSP_LABELS",
    "DirectionalDelegate",
    "LTR",
    "NO_DECISION_LABEL",
    "NO_DECISION_SHORT",
    "RTL",
    "apply_direction",
    "apply_rtl",
    "base_direction",
    "bind_direction",
    "decision_dev_label",
    "dimension_sort_key",
    "directional",
    "first_strong",
    "is_rtl",
    "iso",
    "joined",
    "numeric_field",
    "show_error",
    "canon_geometry_label",
    "signed_label",
    "strip_iso",
    "tolerance_label",
    "tolerance_text",
]


# --- Подписи контролируемых словарей (наряды 0004, 0007, 0011) --------------------

#: Исходы отклонения — подписи из `model/Deviation.md` (Outcomes).
#: Порядок фиксирован: он же порядок списка в диалоге решения.
DECISION_DEV_LABELS = {
    "approved": "Approved — use as is",
    "rejected": "Rejected — scrap",
    "sorting": "Sorting — 100 % inspection",
    "repair": "Repair — legalised deviation",
}

#: Короткая метка **колонки списка**: в диалоге решения, в карточке и в
#: выходном документе исход называется полной формулировкой, в колонке — одним
#: словом (дизайн-система, макет S13). Полная формулировка в узкой колонке
#: всё равно обрезается многоточием, а обрезанная пилюля перестаёт читаться.
DECISION_DEV_SHORT = {
    "approved": "Approved",
    "rejected": "Rejected",
    "sorting": "Sorting",
    "repair": "Repair",
}

#: Позиция без геометрии — прочерк. Деталь по такой позиции не засеется, и
#: оператор должен видеть это в момент привязки, а не выяснять при регистрации.
NO_GEOMETRY = "—"

#: `decision_dev IS NULL` — регистрация прошла, шаг 8 ещё нет.
NO_DECISION_LABEL = "No decision yet"

#: То же состояние в колонке списка — короткой меткой.
NO_DECISION_SHORT = "Not decided"

#: Вердикт исследования (ратификация В-9, наряд 0010 §11).
#:
#: Прежнее `Deviation approved` называло объект, к которому исследование **не
#: привязано** (оно висит на находке), и дословно совпадало с исходом
#: отклонения `approved` — двумя разными сущностями под одной подписью в одной
#: карточке. `Finding approved` тоже неверно: находка решения не несёт вовсе.
#:
#: Поэтому подпись называет не объект, а **суждение**: исследование отвечает,
#: можно ли это принять, решение — что с деталью сделано. Хранимые значения
#: `approved` / `not_approved` не менялись — правится только подпись.
DECISION_INSP_LABELS = {
    "approved": "Acceptable",
    "not_approved": "Not acceptable",
}


def decision_dev_label(decision: str | None, *, short: bool = False) -> str:
    """Подпись исхода отклонения; `None` — «решение не принято».

    `short=True` — метка колонки списка. Разделение не косметика: полная
    формулировка объясняет исход тому, кто его принимает, и для этого живёт в
    диалоге и в карточке; в столбце из десяти строк её читают взглядом сверху
    вниз, и там нужно одно слово.
    """
    if decision is None:
        return NO_DECISION_SHORT if short else NO_DECISION_LABEL
    source = DECISION_DEV_SHORT if short else DECISION_DEV_LABELS
    return source.get(decision, decision)


def signed_label(direction: str, value: float | None) -> str:
    """Знак и величина **одной** ячейкой — и **один** изолят на всю строку.

    Знак и число раздельными колонками (и раздельными изолятами) существовали до
    QMS-016 и оба раза оказывались неверны:

    * два изолята подряд остаются двумя runs и в RTL-контексте раскладываются
      справа налево — `− 0.05` показывалось как `0.05 −` (ратификация S5);
    * в двух колонках знак и его величина расходятся по разным краям соседних
      столбцов и перестают читаться как одно число.

    Поэтому величина со знаком — **атомарный токен**: собирается целиком и
    оборачивается ровно одним изолятом. В базе знак хранится ASCII-дефисом
    (единая точка для парсера S6), а оператору показывается `−` (U+2212), как
    пишет канон.
    """
    sign = "+" if direction == Direction.PLUS else "−"
    number = "" if value is None else f"{value:g}"
    return iso(f"{sign} {number}".strip())


def tolerance_text(plus: float | None, minus: float | None) -> str:
    """Допуск **без изолята**: `+0.05 / −0.05`, годится как часть составной ячейки.

    Знак минуса — `−` (U+2212), как у `signed_label` и как пишет канон: в базе
    он ASCII-дефис (единая точка для парсера S6), а дефис и минус — разные
    символы, и показывать оператору два разных минуса на одном экране незачем.
    """
    if plus is None and minus is None:
        return ""
    return f"+{_magnitude(plus)} / −{_magnitude(minus)}"


def tolerance_label(plus: float | None, minus: float | None) -> str:
    """Допуск отдельной ячейкой: тот же токен, обёрнутый **одним** изолятом."""
    text = tolerance_text(plus, minus)
    return iso(text) if text else ""


def canon_geometry_label(
    nominal: float | None, plus: float | None, minus: float | None
) -> str:
    """Геометрия канонической позиции одной ячейкой: `38.1 +0.2 / −0.1`.

    Два самостоятельных токена — номинал и допуск, — поэтому собирается через
    `joined`: каждый в своём изоляте, порядок за базой ячейки (`CLAUDE.md` §9).
    Один изолят вокруг всей строки задал бы только базу, а токены остались бы
    переставленными.

    Пустая геометрия — прочерк, а не пустая ячейка: у позиции без номинала
    деталь по ней не засеется, и это надо видеть, а не додумывать.
    """
    if nominal is None and plus is None and minus is None:
        return NO_GEOMETRY
    return joined(_magnitude_or_empty(nominal), tolerance_text(plus, minus), sep=" ")


def _magnitude_or_empty(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _magnitude(value: float | None) -> str:
    """Величина без знака: знак ставит сборщик, иначе выходит `−-0.05`."""
    return "0" if value is None else f"{abs(value):g}"


def dimension_sort_key(local_number: str) -> tuple:
    """Порядок номеров размеров: «9» раньше «10», а не наоборот.

    Номер — строка (канон допускает буквенные `AA`/`AB` для состояний до и после
    электрополировки), поэтому обычная сортировка текстом ставит «10» перед «9».
    Разбиваем на цифровые и нецифровые куски и числа сравниваем числами.
    """
    parts = re.split(r"(\d+)", (local_number or "").strip())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part)
