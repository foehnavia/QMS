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
from .kit.widgets import UnexpectedErrorDialog, in_test_mode, set_test_mode, show_error

__all__ = [
    "DECISION_DEV_LABELS",
    "DECISION_DEV_SHORT",
    "OUTCOME_LABELS",
    "NO_OUTCOME_LABEL",
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
    "outcome_label",
    "deviation_text",
    "optional_id",
    "dimension_sort_key",
    "directional",
    "first_strong",
    "is_rtl",
    "iso",
    "joined",
    "numeric_field",
    "show_error",
    "set_test_mode",
    "in_test_mode",
    "UnexpectedErrorDialog",
    "canon_geometry_label",
    "position_index",
    "position_label",
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

#: Исход **находки** (`Finding.md` rev 1.01, QMS-025).
#:
#: Отвечает на вопрос «прошёл ли этот размер», а не «что делать с партией», —
#: поэтому слова не пересекаются с исходами отклонения ни одним: `Permitted`
#: рядом с `Approved — use as is` в одной карточке должны читаться как два разных
#: суждения, потому что они и есть два разных суждения.
OUTCOME_LABELS = {
    "permitted": "Permitted",
    "not_permitted": "Not permitted",
}

#: `outcome IS NULL` — по этому размеру ещё не решали. Нормальное состояние
#: свежей регистрации: находки заводятся при регистрации, суждение приходит позже.
NO_OUTCOME_LABEL = "Not decided"


def outcome_label(outcome: str | None) -> str:
    """Подпись исхода находки; `None` — «ещё не решали».

    Строится **из кода**, а не разбором текста, и одним хелпером на все экраны:
    один факт, показанный в пилюле, в панели раскрытия и в карточке, обязан
    называться там одинаково (`CLAUDE.md` §9а.11).
    """
    if outcome is None:
        return NO_OUTCOME_LABEL
    return OUTCOME_LABELS.get(outcome, outcome)


def optional_id(value: object, field: str) -> int | None:
    """Необязательный идентификатор записи — или `None`; иначе `TypeError`.

    Диалог, у которого идентификатор стоит **вторым** параметром, а родитель
    третьим, ловит один и тот же промах: `Dialog(engine, self)` — родитель
    уезжает в слот идентификатора. Молча это не падает: `item_id` становится
    «не None», форма идёт читать запись, и оператор получает
    `sqlite3.ProgrammingError: type 'ItemView' is not supported` из глубины
    SQLAlchemy — трассу, по которой до своей же строки вызова доходить долго.

    Отказ здесь называет промах на месте. Тот же приём, что у
    `bind_direction` на текстовой области (решение 2026-08-19): молча-бесполезный
    вызов повторил бы ошибку, поэтому хелпер **отказывает**.
    """
    if value is None or isinstance(value, int):
        return value
    raise TypeError(
        f"{field} must be an int or None, got {type(value).__name__} — "
        "a widget in this slot usually means the parent was passed positionally; "
        "pass it as parent=…"
    )


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


def position_label(g_index: int) -> str:
    """Ярлык g-позиции — один на всё приложение: `g13` (Р-3 долга к шву).

    До этого один и тот же индекс назывался `1` в редакторе группы, `g1` в
    привязке и `G1` на чертеже. Ярлык — общий словарь чертежа и базы, ради
    которого запрещено переиспользование индексов; разнобой написания бьёт
    ровно в это. Метка конструктора (`G13`) отличается только регистром и
    читается как тот же идентификатор.
    """
    return iso(f"g{g_index}")


def position_index(text: str) -> int | None:
    """Прочитать индекс обратно из ярлыка. `None` — это не ярлык позиции.

    Пара к `position_label`: раз показ в одном месте, то и разбор в одном,
    иначе они разойдутся на первой же правке.
    """
    cleaned = strip_iso(text or "").strip().lstrip("gG")
    return int(cleaned) if cleaned.isdigit() else None


def deviation_text(value: float | None) -> str:
    """Одно предельное отклонение со **своим** знаком: `+0.05` · `−0.02` · `+0`.

    Знак читается из значения, а не дорисовывается шаблоном. До QMS-016 сборка
    шла как `f"+{abs(plus)} / −{abs(minus)}"`, и у **посадки с натягом**, где оба
    отклонения уходят в плюс, пара `+0.05 / +0.02` выводилась как
    `+0.05 / −0.02`: поле допуска зеркально, несимметричная посадка выглядела
    симметричной. В базе значения были верны — врал показ (дефект Р-2, блокирующий).

    Знак минуса — `−` (U+2212), как у `signed_label` и как пишет канон: в базе он
    ASCII-дефис (единая точка для парсера S6), а показывать оператору два разных
    минуса на одном экране незачем. Ноль знака не несёт вовсе и пишется как `0` (ISO 286).
    """
    if value is None:
        return ""
    if value == 0:
        # По ISO 286 нулевое отклонение пишется без знака: `+0` обещает
        # направление, которого у нуля нет (Р-5 долга к шву).
        return "0"
    return f"{'−' if value < 0 else '+'}{abs(value):g}"


def tolerance_text(plus: float | None, minus: float | None) -> str:
    """Пара предельных отклонений **без изолята** — часть составной ячейки.

    `+0.05 / −0.05` · `+0.05 / +0.02` · `−0.02 / −0.05`. Пустое отклонение
    остаётся пустым и разделителя за собой не тянет: `−0` на месте незаполненного
    значения — то же дорисовывание, ради отмены которого сделан наряд 0015.
    """
    return " / ".join(
        text for text in (deviation_text(plus), deviation_text(minus)) if text
    )


def tolerance_label(plus: float | None, minus: float | None) -> str:
    """Отклонения отдельной ячейкой: тот же токен, обёрнутый **одним** изолятом."""
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


def dimension_sort_key(local_number: str) -> tuple:
    """Порядок номеров размеров: «9» раньше «10», а не наоборот.

    Номер — строка (канон допускает буквенные `AA`/`AB` для состояний до и после
    электрополировки), поэтому обычная сортировка текстом ставит «10» перед «9».
    Разбиваем на цифровые и нецифровые куски и числа сравниваем числами.
    """
    parts = re.split(r"(\d+)", (local_number or "").strip())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part)


# --- Две пометки выдачи (QMS-017, доводка наряда 0025; `Search.md` v1.05) ----------
#
# Пометки различаются **свойством**, а не функцией, и свойства ортогональны:
#
#   цвет (красный)      — за этим номером нет канона, опереться не на что;
#   начертание (жирный) — эта строка из другого выпуска чертежа.
#
# Читаются они вместе, а не одна вместо другой: жирная красная строка говорит
# «прежний выпуск, да ещё и без канона» — ровно сумму своих слагаемых. Ни одно
# свойство не занимает смысл другого и не меняет вид между экранами.
#
# Основание — приёмка наряда 0025. Прежде обе пометки ставила одна функция
# `mark_unbound`: в прецедентах она красила размер, а в списке отклонений детали
# ею же красили **колонку ревизии**, перекрывая подсказку своей. Один и тот же
# факт выглядел на двух экранах по-разному, а красный жирный означал два разных
# факта, различимых в одной строке только наведением мыши.

#: Знак у размера, за номером которого не стоит g-позиция.
UNBOUND_MARK = "!"

#: Смысл **цвета**, одной строкой. Ставится только на ячейку размера и только
#: когда размер не привязан к канону — на колонку ревизии не попадает никогда.
UNBOUND_TOOLTIP = (
    "There is nothing behind this number but the number itself: the dimension is "
    "not bound to the canon."
)


def unbound_size_text(local_number: str, g_label: str | None, *, canon_bound: bool) -> str:
    """Текст ячейки размера: `19 · CG-A · g13` либо `! · 41`.

    Знак — **отдельный токен в своём изоляте**, а не приклеенная к номеру буква
    (`CLAUDE.md` §9): склеенный, он в RTL-строке уезжает к другому краю номера и
    начинает читаться как часть значения.
    """
    if not canon_bound:
        return joined(UNBOUND_MARK, local_number)
    return joined(local_number, g_label)


def mark_unbound(cell) -> None:
    """Ячейка **размера** без канона: красный и полужирный.

    Красится **вся ячейка**, а не один знак, и это осознанный размен. Раскрасить
    внутри ячейки два прогона разным стилем можно только своим делегатом, который
    сам раскладывает текст, — а ровно там, где приложение раскладывало строки
    руками, у него и жили ошибки направления (QMS-016, пять случаев подряд). Qt,
    получив ячейку целиком, раскладывает её сам и в RTL не ошибается.

    Жирность здесь — часть оформления размера, а не пометка выпуска: у не-канонного
    размера красный и так стоит, и вес добавлен ради читаемости знака `!`. Пометку
    выпуска ставит `mark_other_revision`, и только на колонку ревизии.
    """
    from PySide6.QtGui import QColor  # noqa: PLC0415

    from .kit import tokens  # noqa: PLC0415

    cell.setForeground(QColor(tokens.DANGER_TEXT))
    font = cell.font()
    font.setBold(True)
    cell.setFont(font)
    cell.setToolTip(UNBOUND_TOOLTIP)


def mark_other_revision(cell, revision: str, current: str | None) -> None:
    """Ячейка **ревизии** прежнего выпуска: только полужирный, свой текст.

    Цвет здесь не ставится **никогда**: он занят другим смыслом. Прежний выпуск —
    не ошибка и не потеря опоры, а факт, который инженер взвешивает сам: допуск мог
    сдвинуться между выпусками, и прежнее «approved» дано против границ, которых
    больше нет.

    Одна функция на все экраны, перечисляющие отклонения, — затем и заведена: один
    и тот же факт не имеет права выглядеть на двух экранах по-разному, а
    расставленное вручную на каждом экране расходится на первой же правке.
    """
    font = cell.font()
    font.setBold(True)
    cell.setFont(font)
    cell.setToolTip(
        f"Revision {revision}: another issue of the drawing"
        + (f", not the current one ({current})." if current else ".")
    )
