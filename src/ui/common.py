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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from db.models import Direction

from . import kit
from .kit import tokens
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


# --- Панель находок: одна на оба экрана (наряд 0031 §2) --------------------------
#
# Переехала сюда из `deviation_view.py` целиком — вместе с колонками, ширинами,
# высотами и обеими сборками текста. Норма `design-system.md` §3 revision 1.12:
# «Expansion follows the object, not the screen» — раскрытие принадлежит
# **объекту**, а не экрану, поэтому у списка отклонений и у таблицы прецедентов
# в карточке панель обязана быть **одна**, а не вторая такая же.
#
# Почему `common.py`, а не `kit/`: `kit` держит описанное каноном **по форме** —
# кнопку, пилюлю, таблицу. Панель описана каноном по **метрикам** (§3), но её
# колонки предметные: размер, канон, зона, тип отклонения. Предметное общее
# место у нас здесь, и по той же причине здесь уже живут `mark_other_revision`
# и `unbound_size_text`.
#
# Копия вместо переезда была запрещена прямо, и довод не теоретический: первая
# же правка ширины легла бы в один файл из двух.

NO_INSPECTIONS = "No inspections"

PANEL_INDENT = ""
PANEL_COLUMNS = (
    PANEL_INDENT,
    "Dim.",
    "Canon",
    "Sign · value",
    "Zone",
    "Deviation type",
    "Outcome",
    "Inspections",
)
PANEL_WIDTHS = {
    PANEL_INDENT: 30,
    "Dim.": 72,
    "Canon": 70,
    "Sign · value": 92,
    "Zone": 196,
    "Deviation type": 176,
    "Outcome": 168,
    "Inspections": 340,
}

#: Сколько исследований видно в ячейке; остальные — строкой `+N inspections`.
INSPECTIONS_SHOWN = 2

#: Направление колонок панели: номер размера, канон и величина — принудительно
#: LTR. `Zone` и `Deviation type` берут направление по содержимому: значения
#: справочников бывают ивритскими (`CLAUDE.md` §9).
PANEL_NUMERIC_COLUMNS = (1, 2, 3)

#: Вправо — только «знак · величина»: её сравнивают по величине вниз по столбцу.
PANEL_MAGNITUDE_COLUMNS = (3,)


def panel_height(inspection_counts: list[int]) -> int:
    """Высота панели раскрытия: своя шапка плюс строки находок (§4 наряда)."""
    return tokens.PANEL_HEADER_HEIGHT + sum(finding_row_height(n) for n in inspection_counts)


def finding_row_height(inspections: int) -> int:
    """Высота строки находки: **28 / 43 / 58** по числу показанных исследований.

    Правило `design-system.md` §3, revision 1.7: «Inside an expanded record the
    finding sub-row is 28 / 43 / 58 by the number of inspections listed».
    Показанных всегда не больше двух; третье и далее сворачиваются в строку
    `+N inspections`, и она добавляет столько же, сколько вторая строка списка.
    """
    if inspections <= 1:
        return tokens.FINDING_ROW_HEIGHT
    if inspections == 2:
        return tokens.FINDING_ROW_TWO
    return tokens.FINDING_ROW_MANY


def inspections_text(rows) -> str:
    """Ячейка `Inspections`: **тип · позиция**, по строке на исследование.

    Короткий вывод сюда не попадает намеренно (§4.2 наряда `0028`): 340 px это
    около 45 знаков. Вывод целиком уходит в подсказку — приём не новый, так уже
    сделано с обоснованием решения. Позиции у исследования больше нет вовсе
    (`Inspection.md` rev 1.03).
    """
    if not rows:
        return NO_INSPECTIONS
    shown = [strip_iso(iso(row.type_name)) for row in rows[:INSPECTIONS_SHOWN]]
    hidden = len(rows) - len(shown)
    if hidden > 0:
        shown.append(f"+{hidden} inspection" + ("" if hidden == 1 else "s"))
    return "\n".join(shown)


def inspections_tooltip(rows) -> str:
    """Полный вывод каждого исследования — **без обрезки** (§4.2 наряда `0028`).

    Позиции здесь больше нет: исследование поставляет сведения и суждения не
    несёт (`Inspection.md` rev 1.03).
    """
    lines = []
    for row in rows:
        lines.append(
            f"{row.type_name}\n{row.conclusion}" if row.conclusion else row.type_name
        )
    return "\n\n".join(lines)


class FindingsPanel(QTableWidget):
    """Панель находок под раскрытой строкой — своя шапка, своя сетка.

    Это **не** продолжение таблицы над ней: у уровней разные колонки, и панель
    живёт своей сеткой (решение 13 реестра). Ни выбора, ни фокуса она не берёт —
    единица действия остаётся отклонением, и клик внутри панели не меняет
    выбранное отклонение просто потому, что панели нечего выбирать.
    """

    def __init__(
        self,
        findings,
        inspections,
        parent: QWidget | None = None,
        *,
        subordinate: bool = False,
    ) -> None:
        """`subordinate` — оформить шапку **подписью колонок**, а не заголовком.

        Параметр, а не смена вида для всех, и это требование наряда `0032` §4:
        панель после `0031` **одна** на список отклонений и на карточку, и
        перекрасив её здесь, мы перекрасили бы оба экрана. В списке шапка панели
        остаётся прежней — там она отделяет уровень внутри длинной таблицы; в
        диалоге она обязана читаться как подробность строки, иначе повтор
        оформления и делает из карточки лоскутное одеяло.

        Умолчание `False` выбрано намеренно: прежнее поведение достаётся тому,
        кто ничего не просил.
        """
        super().__init__(0, len(PANEL_COLUMNS), parent)
        self.setHorizontalHeaderLabels(PANEL_COLUMNS)
        self.setObjectName(
            kit.OBJECT_PANEL_SUBORDINATE if subordinate else "findingsPanel"
        )

        kit.dress_table(
            self,
            numeric_columns=PANEL_NUMERIC_COLUMNS,
            magnitude_columns=PANEL_MAGNITUDE_COLUMNS,
            widths=tuple(kit.px(PANEL_WIDTHS[name]) for name in PANEL_COLUMNS),
        )
        # Ни выбора, ни фокуса, ни прокрутки: панель показана целиком, а
        # прокручивается список над ней (§3 наряда, инварианты 1 и 2).
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().setMinimumSectionSize(min(PANEL_WIDTHS.values()))
        for index, name in enumerate(PANEL_COLUMNS):
            self.setColumnWidth(index, PANEL_WIDTHS[name])
        self.horizontalHeader().setFixedHeight(tokens.PANEL_HEADER_HEIGHT)
        self.setFrameShape(QTableWidget.Shape.NoFrame)

        self.fill(findings, inspections)

    def fill(self, findings, inspections) -> None:
        """Разложить находки; исследования приходят готовым словарём по находке."""
        ordered = sorted(findings, key=lambda row: dimension_sort_key(row.local_number))
        self.setRowCount(len(ordered))
        for index, row in enumerate(ordered):
            found = inspections.get(row.finding_id, [])
            values = (
                "",
                iso(row.local_number),
                iso(row.canon),
                signed_label(row.direction, row.value),
                row.zone or "",
                row.deviation_type or "",
                outcome_label(row.outcome),
                inspections_text(found),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == PANEL_COLUMNS.index("Inspections") and found:
                    cell.setToolTip(inspections_tooltip(found))
                self.setItem(index, column, cell)
            self.setRowHeight(index, finding_row_height(len(found)))

        self.setFixedHeight(panel_height([len(inspections.get(r.finding_id, [])) for r in ordered]))

    def fit_to(self, width: int) -> None:
        """Уложить колонки панели в `width`, отдавая разницу `Inspections`.

        Панель одна на оба экрана, и её сетка (1144) шире таблицы прецедентов
        карточки: там после наряда `0032` полотно 1120. Без укладки панель теряла
        **две последние колонки целиком** — `Outcome` и `Inspections` просто не
        рисовались, и это видно только на снимке.

        Разница снимается с `Inspections` и только с неё: у неё единственной
        полный текст уже лежит в подсказке, так что укорочение ячейки ничего не
        теряет, — тот же довод, по которому §2 наряда снимал ширину с
        `Explanation`. Прочие колонки панели не трогаются: их числа назначены
        замером, и снять с них значит вернуть обрезку туда, где её убирали.

        Список отклонений сюда не заходит: там таблица шире сетки панели, и
        укладывать нечего.
        """
        others = sum(
            PANEL_WIDTHS[name] for name in PANEL_COLUMNS if name != "Inspections"
        )
        column = PANEL_COLUMNS.index("Inspections")
        self.setColumnWidth(column, max(width - others, tokens.PANEL_TAIL_MIN))

    def sizeHint(self):  # noqa: N802 — имя от Qt
        size = super().sizeHint()
        size.setHeight(self.height())
        return size
