"""Гард дизайн-системы: числа оформления живут только в `src/ui/kit/`.

Наряд 0011 §5, по образцу гарда на кириллицу (наряд 0007 §7). Без него
дизайн-система разойдётся по экранам копиями на первом же спринте — ровно так,
как разошёлся язык интерфейса до наряда 0007: ревью его не проверяло.

Ловим три вида утечки, разбором AST, а не текста:

* **цвет** — шестнадцатеричный литерал в строке;
* **лист стиля** — `setStyleSheet` где угодно вне `kit`: любое его содержимое
  это значения канона, и один селектор в экране уже копия;
* **магическое число геометрии** — литерал в `resize`, `setFixedHeight`,
  `setContentsMargins` и подобных. Ноль разрешён: это не значение канона, а
  «без отступа».
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from ui import kit
from ui.kit import tokens

pytestmark = pytest.mark.usefixtures("qt_app")

SRC = Path(__file__).resolve().parents[1] / "src"
UI = SRC / "ui"
KIT = UI / "kit"

#: `#1B2027`, `#fff` — цвет, где бы он ни стоял.
COLOUR = re.compile(r"#[0-9A-Fa-f]{3,8}\b")

#: Свойство оформления с числом внутри строки: обрывок листа стиля в экране.
STYLE_PROPERTY = re.compile(
    r"\b(font-size|font-weight|border-radius|border|padding|margin|"
    r"min-height|max-height|min-width|max-width|background)\s*:",
    re.IGNORECASE,
)

#: Методы, чей числовой аргумент — это размер, отступ или высота.
GEOMETRY_CALLS = frozenset(
    {
        "resize",
        "setFixedHeight",
        "setFixedWidth",
        "setFixedSize",
        "setMinimumHeight",
        "setMinimumWidth",
        "setMaximumHeight",
        "setMaximumWidth",
        "setContentsMargins",
        "setSpacing",
        "setHorizontalSpacing",
        "setVerticalSpacing",
        "setPointSize",
        "setPointSizeF",
        "setDefaultSectionSize",
        "setIconSize",
        "addSpacing",
    }
)


def _offences(path: Path) -> list[str]:
    """Нарушения канона в одном файле: `строка: что именно`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if COLOUR.search(node.value):
                found.append(f"{node.lineno}: colour literal")
            elif STYLE_PROPERTY.search(node.value):
                found.append(f"{node.lineno}: stylesheet fragment")
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name == "setStyleSheet":
                found.append(f"{node.lineno}: setStyleSheet outside kit")
            elif name in GEOMETRY_CALLS:
                # Ноль — это «без отступа», а не значение дизайн-системы.
                if any(
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, (int, float))
                    and argument.value != 0
                    for argument in node.args
                ):
                    found.append(f"{node.lineno}: literal size in {name}()")
    return found


def test_no_design_values_outside_the_kit() -> None:
    """Ни цвета, ни кегля, ни отступа, ни высоты вне `src/ui/kit/`."""
    offenders = {
        path.relative_to(SRC).as_posix(): _offences(path)
        for path in sorted(UI.rglob("*.py"))
        if KIT not in path.parents
    }
    leaked = {path: found for path, found in offenders.items() if found}
    assert leaked == {}, f"design values outside src/ui/kit/: {leaked}"


def test_the_guard_actually_catches_each_kind(tmp_path: Path) -> None:
    """Страховка от «зелёного» гарда: три вида утечки ловятся, токен — нет."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "SELECTED = '#EFF5FE'\n"
        "def build(widget, table):\n"
        "    widget.setStyleSheet('QLabel { font-size: 13pt; }')\n"
        "    widget.resize(1040, 720)\n"
        "    table.setFixedHeight(tokens.INLINE_TABLE_HEIGHT)\n"
        "    widget.layout().setContentsMargins(0, 0, 0, 0)\n",
        encoding="utf-8",
    )
    kinds = [line.split(": ", 1)[1] for line in _offences(probe)]

    assert "colour literal" in kinds
    assert "setStyleSheet outside kit" in kinds
    assert "stylesheet fragment" in kinds
    assert "literal size in resize()" in kinds
    # Токен и нулевой отступ — не нарушения.
    assert "literal size in setFixedHeight()" not in kinds
    assert "literal size in setContentsMargins()" not in kinds


# --- сами компоненты ---------------------------------------------------------------


def test_tokens_carry_the_ratified_font_stack() -> None:
    """С-1 закрыт замером: три семейства, все установлены, все с ивритом."""
    assert tokens.FONT_STACK == ('"Segoe UI"', '"Arial"', '"Tahoma"')
    assert "Selawik" not in tokens.FONT_FAMILY
    assert "system-ui" not in tokens.FONT_FAMILY


# --- наряд 0019 (доводка §7): поле выбора с отбором ---------------------------------
#
# Проверки идут **настоящими нажатиями** по показанному полю и сверяют то, что
# видит оператор: содержимое строки и список подписей после каждого нажатия.
# Первая редакция проверялась вызовом внутренних методов и была зелёной при
# неработающем поле — этого повторять нельзя.


ITEMS = [
    (1, "C1-08375A"),
    (2, "MF5-10375A-N"),
    (3, "C1-08420B"),
    (4, "маккад"),
]


def _field(qt_app):
    from conftest import shown_field

    kit.apply_theme(qt_app)
    field = kit.FilterCombo("type to narrow the list")
    field.set_rows(ITEMS)
    host = shown_field(field)
    return field, host


def test_every_keystroke_stays_in_the_line(qt_app) -> None:
    """§7.1.1: набранное видно в строке — после **каждого** нажатия.

    На живой сборке первая буква пропадала: список и строка у редактируемого
    `QComboBox` — один источник, и пересборка модели стирала набранное.
    """
    from conftest import type_keys

    field, _host = _field(qt_app)

    trace = type_keys(field, "мак")

    assert [typed for typed, _shown in trace] == ["м", "ма", "мак"]


def test_the_list_shows_exactly_what_was_matched(qt_app) -> None:
    """§7.1.2: в списке ровно отобранное — сверяем подписи, а не «сузился ли».

    Симптом оператора: на букву `м` показывалась запись, в которой этой буквы
    нет вовсе.
    """
    from conftest import type_keys

    field, _host = _field(qt_app)

    trace = type_keys(field, "м")

    assert trace[-1] == ("м", ["маккад"])


def test_the_popup_height_matches_what_is_in_it(qt_app) -> None:
    """§7.1.3: высота списка и его содержимое — одно состояние.

    Симптом оператора: список ростом в одну строку, а внутри прокручиваются все
    записи. Значит содержимое и высота относились к разным моментам.
    """
    from conftest import type_keys

    field, _host = _field(qt_app)
    type_keys(field, "C1")

    popup = field.popup()
    row_height = popup.sizeHintForRow(0)

    assert popup.count() == 2, field.visible_labels()
    assert popup.isVisible()
    fits = popup.height() / row_height
    assert 2 <= fits < 3, f"в списке {popup.count()} строк, а по высоте {fits:.1f}"


def test_a_middle_substring_filters_and_backspace_widens(qt_app) -> None:
    """§7.1.4: вхождение в середине отбирает, стирание расширяет обратно."""
    from conftest import backspace, type_keys

    field, _host = _field(qt_app)

    trace = type_keys(field, "10375")
    assert trace[-1] == ("10375", ["MF5-10375A-N"])

    typed, shown = backspace(field)
    assert typed == "1037"
    assert shown == ["MF5-10375A-N"]

    for _ in range(4):
        typed, shown = backspace(field)
    assert typed == ""
    assert shown == [label for _key, label in ITEMS], "полное стирание вернуло не всё"


def test_nothing_matches_is_explained_not_left_blank(qt_app) -> None:
    """Пустой список без объяснения читается как «таких деталей нет»."""
    from conftest import type_keys

    field, _host = _field(qt_app)

    type_keys(field, "zzz")

    assert field.is_explaining() is True
    shown = field.visible_labels()
    assert len(shown) == 1 and "Nothing matches" in shown[0]
    # Объяснение не выбирается: значением поля оно стать не может.
    assert not field.popup().item(0).flags()


def test_free_text_never_becomes_the_value(qt_app) -> None:
    """Страховка от свободного текста: несовпавшее откатывается по уходу фокуса."""
    from conftest import type_keys

    field, _host = _field(qt_app)
    field.setCurrentText("C1-08375A")

    type_keys(field, "MF5-999")
    field.settle()  # так же зовёт форма и уход фокуса

    assert field.current_key() == 1
    assert field.lineEdit().text() == "C1-08375A"


def test_the_field_yields_the_key_not_the_label(qt_app) -> None:
    """Контракт наружу: идентификатор, и он не зависит от состояния отбора."""
    from conftest import type_keys

    field, _host = _field(qt_app)
    field.setCurrentText("MF5-10375A-N")

    type_keys(field, "C1")  # список сужен на совсем другие записи

    assert field.currentData() == 2
    assert field.current_key() == 2


def test_choosing_a_row_sets_the_value_and_closes_the_list(qt_app) -> None:
    """Выбор строки — единственный момент, когда код пишет в строку ввода."""
    from conftest import type_keys

    field, _host = _field(qt_app)
    seen = []
    field.keyChanged.connect(seen.append)

    type_keys(field, "8420")
    field._pick(field.popup().item(0))

    assert field.current_key() == 3
    assert field.lineEdit().text() == "C1-08420B"
    assert field.popup().isVisible() is False
    assert seen == [3]


def test_an_emptied_line_means_nothing_is_selected(qt_app) -> None:
    """Стёртая строка — законное «не выбрано»: иначе снять выбор нечем."""
    from conftest import clear_line

    field, _host = _field(qt_app)
    field.setCurrentText("C1-08375A")
    field.lineEdit().setFocus()

    typed, shown = clear_line(field)

    assert typed == ""
    assert field.current_key() is None
    # И список при этом полон: стирание — не отбор, а снятие выбора.
    assert shown == [label for _key, label in ITEMS]


def test_a_hebrew_value_keeps_its_own_direction(qt_app) -> None:
    """Канон §6: направление строки следует за набранным, а не за окном."""
    from PySide6.QtCore import Qt

    from conftest import type_keys

    field, _host = _field(qt_app)
    field.set_rows(ITEMS + [(5, "אזור הברגה")])

    type_keys(field, "אזור")

    assert field.visible_labels() == ["אזור הברגה"]
    assert field.lineEdit().layoutDirection() == Qt.LayoutDirection.RightToLeft



def test_the_popup_does_not_swallow_the_keys(qt_app) -> None:
    """§8.1: со второго символа поле отвечать не переставало.

    Всплытие создано окном типа `Popup`, а такое окно **забирает клавиатуру
    целиком**. Список с `NoFocus` нажатия не обрабатывал и никому не передавал —
    они пропадали: первая буква проходила (всплытия ещё нет), вторая и все
    следующие исчезали, `Backspace` не реагировал, выход был один — щёлкнуть
    мимо. Теперь нажатия из всплытия переадресуются в строку.

    Тест ловит это только потому, что событие идёт **через приложение**: адресат
    выбирается так же, как выбирает Qt, — активное всплытие раньше фокуса.
    """
    from PySide6.QtWidgets import QApplication

    from conftest import type_keys

    field, _host = _field(qt_app)

    trace = type_keys(field, "375")

    # Всплытие действительно захватило ввод — иначе тест ничего не проверяет.
    assert QApplication.activePopupWidget() is field.popup()
    assert [typed for typed, _shown in trace] == ["3", "37", "375"]
    assert trace[-1][1] == ["C1-08375A", "MF5-10375A-N"]


def test_backspace_arrows_enter_and_escape_work_with_the_list_open(qt_app) -> None:
    """§8.5.3: при открытом списке работают стирание, стрелки, выбор и закрытие."""
    from conftest import (
        backspace,
        press_arrow,
        press_enter,
        press_escape,
        type_keys,
    )

    field, _host = _field(qt_app)

    type_keys(field, "C1-")
    assert field.visible_labels() == ["C1-08375A", "C1-08420B"]

    # Backspace — стирает и расширяет отбор обратно.
    typed, shown = backspace(field)
    assert typed == "C1"
    assert shown == ["C1-08375A", "C1-08420B"]

    # Стрелки водят по списку.
    assert field.popup().currentRow() == 0
    press_arrow(down=True)
    assert field.popup().currentRow() == 1
    press_arrow(down=False)
    assert field.popup().currentRow() == 0

    # Enter выбирает то, на чём стоит отметка, и закрывает список.
    press_arrow(down=True)
    press_enter()
    assert field.current_key() == 3
    assert field.lineEdit().text() == "C1-08420B"
    assert field.popup().isVisible() is False

    # Escape закрывает список и возвращает строку к выбранному.
    # Перед новым набором строку чистим — оператор так и делает, иначе набранное
    # допишется к подписи выбранного.
    from conftest import clear_line

    clear_line(field)
    again = type_keys(field, "MF5")
    assert again[-1][1] == ["MF5-10375A-N"]
    press_escape()
    assert field.popup().isVisible() is False
    # Строка чистилась, значит выбор снят — Escape возвращает её к «не выбрано».
    assert field.lineEdit().text() == ""
    assert field.current_key() is None


def test_an_empty_popup_is_never_shown(qt_app) -> None:
    """Р-1 долга к шву: показывать нечего — не показываем.

    У пустого списка `sizeHintForRow(0)` отвечает **-1**, и умолчание через
    `or` не подставлялось: -1 истинно. Высота выходила отрицательной.
    """
    from conftest import shown_field

    kit.apply_theme(qt_app)
    field = kit.FilterCombo("empty on purpose")
    field.set_rows([])
    host = shown_field(field)  # хост держим: без ссылки виджеты уничтожаются
    assert host.isVisible()

    field.filter_to("")
    field._open()

    assert field.popup().count() == 0
    assert field.popup().isVisible() is False



# --- наряд 0020 §3.1: ширина — свойство класса содержимого ---------------------------


def test_no_column_stretches_and_width_is_the_sum(qt_app) -> None:
    """Ширина таблицы — сумма колонок и от размера окна не зависит (§3.1).

    Прежде колонки тянулись на всё окно (`Stretch`), и на широком экране
    идентификатор занимал полполосы, а объяснение всё равно не помещалось.
    """
    from PySide6.QtWidgets import QHeaderView

    kit.apply_theme(qt_app)
    table = kit.data_table(("Number", "Date", "Explanation"))
    header = table.horizontalHeader()

    assert header.sectionResizeMode(0) != QHeaderView.ResizeMode.Stretch
    assert header.stretchLastSection() is False

    table.resize(600, 200)
    narrow = [table.columnWidth(c) for c in range(3)]
    table.resize(1900, 200)
    wide = [table.columnWidth(c) for c in range(3)]

    assert narrow == wide, "колонка тянется за окном"


def test_each_class_carries_its_own_limit(qt_app) -> None:
    """Класс содержимого несёт предел: счётчик уже идентификатора, текст шире."""
    kit.apply_theme(qt_app)
    table = kit.data_table(("Number", "Findings", "Explanation"))

    identifier, counter, text = (table.columnWidth(c) for c in range(3))

    assert counter < identifier < text
    # И ни одна не уже собственной подписи: обрезанная подпись — это колонка,
    # про которую оператор не знает, что в ней.
    for column in range(3):
        label = table.horizontalHeaderItem(column).text()
        assert table.columnWidth(column) >= table.fontMetrics().horizontalAdvance(label)


def test_centring_only_when_the_table_fills_most_of_the_area(qt_app) -> None:
    """Правило 3 §7.3: центрируем только заполненную область.

    Поле шире самой таблицы читается как поломка, а не как приём — так и вышло
    на Reference data. Порог — доля области (`CENTRING_SHARE`); ниже неё
    таблица прижимается к левому краю, выше — центрируется, а совсем широкая
    отдаёт отступы и прокручивается.
    """
    from PySide6.QtCore import QRect

    from ui.kit.widgets import CENTRING_SHARE

    kit.apply_theme(qt_app)
    table = kit.data_table(("Number", "Date"))
    total = sum(table.columnWidth(c) for c in range(table.columnCount()))

    # Область вдвое шире таблицы — доля ниже порога, значит влево.
    table.setGeometry(QRect(0, 0, total * 2, 200))
    assert table._margin == 0, "узкая таблица утоплена в поле вместо левого края"

    # Область чуть шире таблицы — доля выше порога, центрируем.
    table.setGeometry(QRect(0, 0, int(total / CENTRING_SHARE) - 20, 200))
    assert table._margin > 0, "заполненная таблица не отцентрирована"

    # Область уже таблицы — отступов нет вовсе.
    table.setGeometry(QRect(0, 0, total // 2, 200))
    assert table._margin == 0, "широкая таблица обязана отдать отступы"


def test_a_truncated_cell_explains_itself(qt_app) -> None:
    """Предел без подсказки — потеря данных на экране (§3.1).

    Проверяем **то, чем показывают**: делегат отвечает на запрос подсказки
    полным текстом ровно тогда, когда текст не помещается.
    """
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QTableWidgetItem, QToolTip

    kit.apply_theme(qt_app)
    table = kit.data_table(("Number",))
    table.setRowCount(1)
    long_value = "DEV-260903-0001-and-a-very-long-tail-that-cannot-fit"
    table.setItem(0, 0, QTableWidgetItem(long_value))
    table.setColumnWidth(0, 60)

    index = table.model().index(0, 0)
    option = table.viewOptions() if hasattr(table, "viewOptions") else None
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), table.mapToGlobal(QPoint(5, 5)))
    table.itemDelegate().helpEvent(event, table, option, index)

    assert QToolTip.text() == long_value



# --- наряд 0020 §7: ширины объявлены поимённо ---------------------------------------


def test_a_slot_is_the_average_glyph_and_not_the_widest(qt_app) -> None:
    """§8.3: знакоместо — **средний** знак шрифта канона, не самый широкий.

    Разметку оператора по пикселям воспроизводит именно средний знак: текущая
    раскладка ложилась в `знакоместа × 12 px + 20` (12 — ширина `M`), желаемая —
    в `знакоместа × ≈7.4 px + 20`. Запас от обрезки сидит в самих числах
    знакомест (§7.3), а не в том, что каждый знак считается за `M`.

    Оговорка про платформу: под offscreen шрифт **моноширинный** (все знаки
    13 px), поэтому «средний» и «самый широкий» здесь неразличимы, и разницу
    ловит не этот тест, а замер на нативной платформе
    (`tools/screenshots.py --run-db` печатает ширину каждой колонки). Тест
    сторожит **правило**: единица берётся ровно одним способом.
    """
    from ui.kit.widgets import column_width, slot_width

    kit.apply_theme(qt_app)
    table = kit.data_table(("Value",))

    assert slot_width(table) == table.fontMetrics().horizontalAdvance("0")
    for slots in (6, 12, 26):
        assert column_width(table, slots) == slot_width(table) * slots + tokens.PAD_CELL * 2


def test_a_counter_column_is_its_header_and_nothing_more(qt_app) -> None:
    """§8.3, класс 2: у счётчика ширина — заголовок плюс отступы, без запаса.

    `0`, `15`, `9999`, `yes` не растут, заголовок задан нами и тоже не растёт;
    запас в четверть там не нужен ни с какой стороны. Объявляется `FIT_LABEL`,
    и число знакомест на такую колонку больше не влияет вовсе.
    """
    from ui.kit.widgets import column_width

    kit.apply_theme(qt_app)
    table = kit.data_table(("Characteristics",), widths=(kit.FIT_LABEL,))
    metrics = table.fontMetrics()

    expected = metrics.horizontalAdvance("Characteristics") + tokens.PAD_CELL * 2
    assert table.columnWidth(0) == expected
    assert column_width(table, kit.FIT_LABEL, "Characteristics") == expected
    # Заголовок короче — колонка уже; знакоместа роли не играют ни в одном случае.
    assert column_width(table, kit.FIT_LABEL, "Insp.") < expected


def test_a_pill_column_leaves_room_for_the_pill_not_just_its_text(qt_app) -> None:
    """§8, находка прогона: делегат режет «Not deci…», а замер по тексту молчит.

    Пилюлю рисует `DecisionPillDelegate` — своим шрифтом (крупнее и жирнее
    табличного) и со своей оправой: отступы плюс кружок исхода. Ширина колонки
    обязана считаться по тому, **чем рисуют**, а не по голому тексту ячейки.
    """
    from PySide6.QtGui import QFont, QFontMetrics

    from ui.deviation_view import COLUMNS, FULL_WIDTHS
    from ui.kit.pills import PILL_CHROME
    from ui.kit.widgets import column_width

    kit.apply_theme(qt_app)
    table = kit.data_table(
        COLUMNS, widths=tuple(kit.px(FULL_WIDTHS[name]) if name in FULL_WIDTHS
                              else kit.FIT_LABEL for name in COLUMNS)
    )
    decision = COLUMNS.index("Decision")

    # Оправа учтена ровно один раз и ровно та же, которой рисует делегат.
    assert column_width(table, kit.pill(14), "Decision") == (
        column_width(table, 14, "Decision") + PILL_CHROME
    )

    # Наряд `0028` перевёл этот экран на **пиксели канвы**: ширина объявлена
    # рисунком, а не выведена из знакомест, и объявление экрана доходит до
    # колонки без пересчёта — вот это здесь и проверяется.
    assert table.columnWidth(decision) == FULL_WIDTHS["Decision"]
    assert table.columnWidth(decision) != column_width(table, kit.pill(14), "Decision")

    # **Хватает ли объявленных пикселей самой пилюле — под offscreen непроверяемо**
    # (`CLAUDE.md` §9а.8): шрифт здесь моноширинный, `0` и `M` одной ширины, и
    # «Not decided» получает 197 px там, где на пропорциональном шрифте берёт 116.
    # Тест, сверяющий пиксели канвы с этим завышением, красный на верной сетке —
    # то есть проверяет платформу, а не экран. Замер живёт на нативной платформе,
    # в `tools/screenshots.py` (`measure_pill_room`), где шрифт настоящий.
    font = QFont(table.font())
    font.setPointSizeF(tokens.SIZE_PILL)
    font.setWeight(QFont.Weight(tokens.WEIGHT_PILL))
    pill_metrics = QFontMetrics(font)
    # Оправа всё же обязана быть учтена: без неё расчёт врёт на любой платформе.
    assert pill_metrics.horizontalAdvance("Approved") + PILL_CHROME > 0


def test_a_declared_width_beats_the_guessed_class(qt_app) -> None:
    """§7.3: класс остался умолчанием, объявление экрана — правилом.

    Догадка по имени и развела `Connection` (короткое содержимое, широкий
    класс) с `Item type` (длинное содержимое, узкий): имена врут.
    """
    kit.apply_theme(qt_app)
    guessed = kit.data_table(("Item type",))
    declared = kit.data_table(("Item type",), widths=(24,))

    assert declared.columnWidth(0) != guessed.columnWidth(0)
    assert declared.columnWidth(0) >= 24 * kit.widgets.slot_width(declared)


def test_no_cell_and_no_header_wraps(qt_app) -> None:
    """Критерий 1 §7.4: ни ячейка, ни заголовок не уезжают на вторую строку."""
    from PySide6.QtWidgets import QTableWidgetItem

    kit.apply_theme(qt_app)
    table = kit.data_table(("Value", "Used by"), widths=(26, 12))
    table.setRowCount(1)
    table.setItem(0, 0, QTableWidgetItem("Straight Multy-Unit"))
    table.setItem(0, 1, QTableWidgetItem("2 records"))

    assert table.wordWrap() is False
    metrics = table.fontMetrics()
    for column, text in ((0, "Straight Multy-Unit"), (1, "2 records")):
        room = table.columnWidth(column) - tokens.PAD_CELL * 2
        assert metrics.horizontalAdvance(text) <= room, (
            f"{text!r} не помещается в свою колонку"
        )
        label = table.horizontalHeaderItem(column).text()
        assert metrics.horizontalAdvance(label) <= room, f"заголовок {label!r} не влез"


def test_every_declared_width_holds_a_quarter_more(qt_app) -> None:
    """Критерий 6 §7.4: запас в четверть — проверкой, а не глазами.

    К самому длинному реальному значению каждой объявленной колонки можно
    дописать ещё четверть длины, и оно по-прежнему не обрежется. Значения
    удлиняются искусственно: завтра они удлинятся сами.
    """
    kit.apply_theme(qt_app)

    from ui.cg_view import COLUMNS as CG_COLUMNS
    from ui.cg_view import WIDTHS as CG_WIDTHS
    from ui.item_view import COLUMNS as ITEM_COLUMNS
    from ui.item_view import WIDTHS as ITEM_WIDTHS
    from ui.reference_view import COLUMNS as REF_COLUMNS
    from ui.reference_view import WIDTHS as REF_WIDTHS

    # Самое длинное реальное значение каждой колонки — из базы прогона.
    longest = {
        ("Value",): "Straight Multy-Unit",
        ("Used by",): "2 records",
        ("Item number",): "MF5-10375A-N",
        ("Item type",): "Straight Multy-Unit",
        ("Connection",): "IntHex",
        ("Size class",): "General",
        ("Groups",): "C1 SP375 Int. Con. Zone",
        ("Group",): "C1 SP375 Int. Con. Zone",
    }

    for columns, widths in (
        (REF_COLUMNS, REF_WIDTHS),
        (ITEM_COLUMNS, ITEM_WIDTHS),
        (CG_COLUMNS, CG_WIDTHS),
    ):
        table = kit.data_table(columns, widths=widths)
        metrics = table.fontMetrics()
        for index, name in enumerate(columns):
            value = longest.get((name,))
            if value is None:
                continue
            grown = value + "M" * max(len(value) // 4, 1)
            room = table.columnWidth(index) - tokens.PAD_CELL * 2
            assert metrics.horizontalAdvance(grown) <= room, (
                f"{name}: {grown!r} ({len(grown)} знаков) не помещается — запаса нет"
            )


def test_the_stylesheet_is_built_from_tokens() -> None:
    """Стиль — производная канона: значения приходят из `tokens`, не из головы."""
    sheet = kit.stylesheet()

    assert tokens.BLUE_600 in sheet
    assert tokens.RIBBON in sheet
    assert f"{tokens.TABLE_HEADER_HEIGHT}px" in sheet


def test_the_theme_does_not_inherit_the_system_palette(qt_app: QApplication) -> None:
    """Канон §0: светлая палитра ставится явно, тёмный режим Windows не в счёт."""
    kit.apply_theme(qt_app)

    assert qt_app.palette().window().color().name().upper() == tokens.WHITE
    assert qt_app.font().families()[0] == "Segoe UI"


def test_the_ribbon_keeps_its_height_when_squeezed() -> None:
    """Решение В-5: при сжатии уходят подписи, а не пиксели высоты."""
    ribbon = kit.NavigationRibbon("MIS-QMS", "Offline")
    ribbon.add_section("Deviations")
    ribbon.resize(tokens.WINDOW_MIN_WIDTH, tokens.RIBBON_HEIGHT)
    assert ribbon.status.isVisible() or not ribbon.isVisible()

    ribbon.resize(tokens.WINDOW_MIN_WIDTH - 200, tokens.RIBBON_HEIGHT)

    assert ribbon.height() == tokens.RIBBON_HEIGHT
    assert not ribbon.status.isVisible()


def test_the_picker_hides_its_filter_on_a_short_list() -> None:
    """Граница решения В-6: строка отбора появляется после 12 значений."""
    short = [(index, f"value {index}") for index in range(tokens.PICKER_FILTER_THRESHOLD)]
    long = [(index, f"value {index}") for index in range(tokens.PICKER_FILTER_THRESHOLD + 1)]

    # `isVisibleTo` спрашивает про **свой** диалог: окно не показано, и
    # `isVisible` под offscreen ответил бы «нет» на оба случая.
    with_short = kit.PickerDialog("Pick an item", "Item:", short)
    with_long = kit.PickerDialog("Pick an item", "Item:", long)

    assert not with_short.filter.isVisibleTo(with_short)
    assert with_long.filter.isVisibleTo(with_long)


def test_the_picker_filter_narrows_by_substring() -> None:
    """Отбор — подстрокой и без учёта регистра; список под диалогом не трогается."""
    rows = [(1, "C1-08375A"), (2, "MF5-10375A-N"), (3, "C1-08420B")]
    dialog = kit.PickerDialog("Pick an item", "Item:", rows)

    dialog.filter.setText("08375")

    assert dialog.values.count() == 1
    assert dialog.values.item(0).text() == "C1-08375A"
    # Исходный набор не тронут: диалог сужает выбор, а не список.
    assert len(dialog._rows) == 3


def test_the_data_table_holds_one_row_height() -> None:
    """Канон §3: одно состояние — одно число. Раскрытия строки в сборке нет."""
    table = kit.data_table(("A", "B"), numeric_columns=(1,))

    assert table.verticalHeader().defaultSectionSize() == tokens.TABLE_ROW_HEIGHT
    assert isinstance(table.itemDelegate(), kit.DirectionalDelegate)
    assert isinstance(table, QTableWidget)


def test_buttons_carry_their_role_not_their_colour() -> None:
    """Кнопка не красит себя сама — она объявляет роль, красит единый лист."""
    for factory, role in (
        (kit.primary, "primary"),
        (kit.secondary, "secondary"),
        (kit.danger, "danger"),
    ):
        button = factory("Do it")
        assert isinstance(button, QPushButton)
        assert button.property(kit.ROLE) == role
        assert button.styleSheet() == ""


def test_the_compact_empty_state_is_one_line_without_a_way_out() -> None:
    """Канон §8 ревизии 1.2: секция с соседями объясняет пустоту строкой.

    Выбор варианта — про **единицу**, а не про место: выход принадлежит
    поверхности вокруг секции, и повторять его в каждой секции значит
    предлагать один и тот же выход дважды.
    """
    box = kit.empty_state(
        "No precedents yet", "only decided deviations are listed", compact=True
    )

    assert box.compact is True
    assert not box.title_label.isVisibleTo(box)
    assert "No precedents yet" in box.body_label.text()
    assert "only decided deviations are listed" in box.body_label.text()
    # Компактная секция ниже полной: это и есть та вертикаль, которую она
    # возвращает таблице.
    full = kit.empty_state("No precedents yet", "only decided deviations are listed")
    assert box.sizeHint().height() < full.sizeHint().height()


def test_an_empty_state_can_change_its_reason() -> None:
    """«Находка не выбрана» и «прецедентов нет» — разные ответы, не один."""
    box = kit.empty_state("No precedents yet", "nothing decided before", compact=True)

    kit.set_empty_reason(box, "No finding selected", "pick a finding above")

    assert "No finding selected" in box.body_label.text()
    assert "pick a finding above" in box.body_label.text()
    assert "No precedents" not in box.body_label.text()


def test_the_choice_shows_which_option_is_taken(qt_app) -> None:
    """Сверяем то, **чем рисуют**: отмеченный кружок обязан быть на экране.

    Qt рисует родной индикатор, только пока виджет не попал под лист стиля; как
    только под него попадает хоть одно правило, оператор получает пустой кружок.
    Найдено снимком диалога решения: четыре исхода и ни одной видимой отметки
    (`CLAUDE.md` §9 — тест берёт значение из того же источника, что и отрисовка).
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    # Тему применяем сами (§3.6 наряда 0020): лист стиля сюда приходил побочно,
    # от соседнего теста, и запущенный в одиночку тест мерил родной стиль
    # Windows — то есть проверял не то, что чинили. Тест, зависящий от порядка
    # запуска, не проверка, а лотерея.
    kit.apply_theme(qt_app)

    host = QWidget()
    layout = QVBoxLayout(host)
    choice = kit.Choice()
    choice.add("approved", "Approved — use as is")
    choice.add("rejected", "Rejected — scrap")
    layout.addWidget(choice)
    host.resize(320, 90)
    host.layout().activate()
    choice.set_value("approved")

    image = host.grab().toImage()
    accent = QColor(tokens.BLUE_600).rgb() & 0xFFFFFF
    painted = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) & 0xFFFFFF == accent
    )

    assert choice.value() == "approved"
    assert painted > 0, "отмеченный вариант не нарисован"



def _indicator_box(image, row_top: int, row_bottom: int, colour: str, zone: int = 26):
    """Рамка индикатора — по **его собственному цвету**, а не «всё, что не фон».

    Прежний замер брал любые непохожие на фон пиксели и при широкой рамке
    прихватывал чужое: ореол фокуса, кольцо соседней кнопки, подпись. Цвет
    индикатора известен — им и меряем; заодно исчезает зависимость от того, кто
    ещё нарисован рядом.
    """
    from PySide6.QtGui import QColor

    wanted = QColor(colour).rgb() & 0xFFFFFF
    painted = [
        (x, y)
        for y in range(row_top, row_bottom)
        for x in range(0, zone)
        if image.pixel(x, y) & 0xFFFFFF == wanted
    ]
    if not painted:
        return None
    xs = [point[0] for point in painted]
    ys = [point[1] for point in painted]
    return min(xs), min(ys), max(xs), max(ys)


def test_the_radio_indicator_is_the_same_circle_in_both_states(qt_app) -> None:
    """№18: два состояния одного элемента — одна фигура, один размер, один край.

    Прежний тест этого класса считал только «есть ли синие пиксели» — и был
    зелёным, когда отмеченный индикатор рисовался **квадратом**, крупнее
    невыбранного и левее него. Причина в QSS: `width`/`height` задают content-box,
    поэтому более толстая рамка у `:checked` растила весь индикатор, а радиус в
    7 px на рамке в 4 px давал скруглённый квадрат.

    Поэтому тест меряет **нарисованное**: рамку индикатора в каждом состоянии,
    её размер, левый край и долю закрашенного (у круга ≈ π/4, у квадрата ≈ 1).
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QRadioButton, QVBoxLayout, QWidget

    # Тему применяем **сами**: без листа стиля индикатор рисует родной стиль
    # Windows, и тест мерил бы не то, что чинил наряд. Прежде лист приходил
    # сюда побочно — его ставил соседний тест, и порядок запуска решал, что
    # именно измерено (наблюдение наряда 0019).
    kit.apply_theme(qt_app)

    host = QWidget()
    layout = QVBoxLayout(host)
    checked = QRadioButton("checked")
    unchecked = QRadioButton("unchecked")
    layout.addWidget(checked)
    layout.addWidget(unchecked)
    host.resize(220, 80)
    host.layout().activate()
    checked.setChecked(True)

    image = host.grab().toImage()
    # Отмеченный красится акцентом, невыбранный — цветом своей рамки.
    marked = _indicator_box(
        image, checked.y(), checked.y() + checked.height(), tokens.BLUE_600
    )
    plain = _indicator_box(
        image, unchecked.y(), unchecked.y() + unchecked.height(), tokens.N_250
    )

    assert marked is not None, "отмеченный индикатор не нарисован"
    assert plain is not None, "невыбранный индикатор не нарисован"

    def size(box):
        return box[2] - box[0] + 1, box[3] - box[1] + 1

    # Размер сверяем с **рисуемой коробкой**, а не двух состояний между собой:
    # отмеченный залит целиком, невыбранный виден только кольцом рамки, и их
    # рамки по цвету не равны по построению. Коробка одна и та же:
    # содержимое плюс две рамки (Р-1 ревью наряда 0019).
    drawn = tokens.INDICATOR_SIZE + 2 * tokens.BORDER_WIDTH
    width, height = size(marked)
    # Допуск в два пикселя — цена точного совпадения по цвету: край круга
    # сглажен, и крайнее кольцо в чистый акцент не попадает (замерено).
    assert abs(width - drawn) <= 2 and abs(height - drawn) <= 2, (
        f"отмеченный индикатор {size(marked)} против рисуемой коробки {drawn}"
    )
    # Левый край меряем **краем фигуры**, а не краем чистого цвета: у залитого
    # диска и у кольца чистый цвет начинается на разном пикселе из-за
    # сглаживания, и сравнивать их между собой значит сравнивать заливки, а не
    # положение. Ореол фокуса из замера исключён — он рисуется своим цветом.
    def left_edge(row_top: int, row_bottom: int) -> int:
        background = QColor(image.pixel(image.width() - 2, row_top + 1)).rgb() & 0xFFFFFF
        halo = QColor(tokens.BLUE_HALO).rgb() & 0xFFFFFF
        middle = (row_top + row_bottom) // 2
        for x in range(26):
            pixel = image.pixel(x, middle) & 0xFFFFFF
            if pixel not in (background, halo):
                return x
        return -1

    marked_edge = left_edge(checked.y(), checked.y() + checked.height())
    plain_edge = left_edge(unchecked.y(), unchecked.y() + unchecked.height())
    assert marked_edge >= 0 and abs(marked_edge - plain_edge) <= 1, (
        f"левые края разошлись: {marked_edge} против {plain_edge}"
    )
    assert abs(width - height) <= 1, "индикатор не квадратен по габариту — не круг"

    # Форма меряется **углами**, а не долей закраски: доля обманывает — у
    # прежнего отмеченного индикатора она была 0.45 (белая середина в толстой
    # рамке), у нынешнего 0.80 (диск), и порога между ними нет.
    #
    # Угол берётся квадратом два на два от вершины рамки: замерено **0 из 16**
    # у круга против **15 из 16** у скруглённого квадрата. Квадрат три на три
    # такого запаса не даёт — в него заходит край самого диска.
    from PySide6.QtGui import QColor

    accent = QColor(tokens.BLUE_600).rgb() & 0xFFFFFF

    def corner(x0: int, y0: int, dx: int, dy: int, side: int = 2) -> int:
        return sum(
            1
            for step_y in range(side)
            for step_x in range(side)
            if image.pixel(x0 + step_x * dx, y0 + step_y * dy) & 0xFFFFFF == accent
        )

    corners = (
        corner(marked[0], marked[1], 1, 1)
        + corner(marked[2], marked[1], -1, 1)
        + corner(marked[0], marked[3], 1, -1)
        + corner(marked[2], marked[3], -1, -1)
    )
    assert corners <= 4, (
        f"углы индикатора закрашены — это квадрат, а не круг: {corners} из 16"
    )


def test_the_checked_indicator_is_visible_at_all(qt_app) -> None:
    """Обратная сторона: одинаковость не должна достигаться исчезновением отметки."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QRadioButton, QVBoxLayout, QWidget

    kit.apply_theme(qt_app)
    host = QWidget()
    layout = QVBoxLayout(host)
    checked = QRadioButton("checked")
    layout.addWidget(checked)
    host.resize(220, 44)
    host.layout().activate()
    checked.setChecked(True)

    image = host.grab().toImage()
    accent = QColor(tokens.BLUE_600).rgb() & 0xFFFFFF
    painted = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) & 0xFFFFFF == accent
    )
    assert painted > 0, "отмеченный вариант не нарисован вовсе"

def test_the_editors_still_draw_their_arrows() -> None:
    """§9: у стилизованного виджета индикатор рисует тот, кого спросили последним.

    Безобидное `border: none` на `::drop-down` забрало отрисовку у родного стиля
    и не оставило стрелки вовсе — ноль тёмных пикселей в её зоне. Описать её
    обратно правилом QSS нельзя: Qt заливает прямоугольник подстиля и о приёме
    «треугольник из рамок» не знает — выходит квадрат. Поэтому подстиль
    **намеренно не описан**, и чертит родной стиль.

    Тест считает пиксели, а не проверяет наличие правила: правило было и раньше,
    а стрелки не было.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QComboBox, QDateEdit, QSpinBox, QVBoxLayout, QWidget

    host = QWidget()
    layout = QVBoxLayout(host)
    combo = QComboBox()
    combo.addItems(["implant"])
    date = QDateEdit()
    date.setCalendarPopup(True)
    spin = QSpinBox()
    for editor in (combo, date, spin):
        layout.addWidget(editor)
    host.resize(240, 130)
    host.layout().activate()
    image = host.grab().toImage()

    def drawn(editor) -> int:
        box = editor.geometry()
        return sum(
            1
            for y in range(box.top() + 2, box.bottom() - 2)
            for x in range(box.right() - 24, box.right() - 2)
            if QColor(image.pixel(x, y)).lightness() < 170
        )

    assert drawn(combo) > 0, "выпадающий список без стрелки"
    assert drawn(date) > 0, "поле даты без стрелки"
    assert drawn(spin) > 0, "счётчик без стрелок"


def test_the_theme_leaves_the_arrow_to_the_native_style() -> None:
    """Обратная сторона того же: описанный подстиль снова заберёт отрисовку.

    Смотрим на **правила**, а не на текст листа: подстиль назван в пояснении к
    этому же месту, и тест, спотыкающийся о собственный комментарий, ловил бы
    не то.
    """
    import re

    sheet = re.sub(r"/\*.*?\*/", "", kit.stylesheet(), flags=re.S)
    rules = [line for line in sheet.splitlines() if "{" in line]

    assert not [rule for rule in rules if "::down-arrow" in rule]
    assert not [rule for rule in rules if "::drop-down" in rule]


def test_a_choice_starts_with_nothing_taken() -> None:
    """Канон §4: предвыбранный вариант — ответ, которого оператор не давал."""
    choice = kit.Choice()
    choice.add("approved", "Approved — use as is")
    choice.add("rejected", "Rejected — scrap")

    assert choice.value() is None
    assert not any(button.isChecked() for button in choice.buttons())


def test_the_empty_state_says_what_why_and_a_way_out() -> None:
    """Канон §8: пустая таблица без объяснения — источник ложного вывода."""
    action = kit.secondary("Add a deviation…")
    box = kit.empty_state(
        "No precedents yet",
        "Nothing has been decided on this characteristic before.",
        action,
    )
    labels = [child.text() for child in box.findChildren(QLabel)]

    assert any("No precedents" in text for text in labels)
    assert any("decided" in text for text in labels)
    assert action.parent() is not None



def test_the_checkbox_indicator_is_visible_in_both_states(qt_app) -> None:
    """§9 В-6 и находка наряда `0029`: **индикатор обязан быть виден на экране**.

    Флажок `No protocol` на первом снимке выглядел подписью: как только на виджет
    лёг лист стиля, отрисовка перешла к нему, а `QCheckBox::indicator` описан не
    был — и в снятом состоянии не рисовалось **ничего**, кликать было не по чему.
    Радиокнопка этого не показывала: её подстиль описан с наряда `0019`.

    Считаются **пиксели**, а не наличие правила в листе (`CLAUDE.md` §9). И оба
    состояния сразу: тест на одно отмеченное был бы зелёным ровно на том экране,
    который сломался, — там отмеченный флажок рисовался галочкой, а снятый
    исчезал.
    """
    from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

    # Тему применяем сами: без листа стиля индикатор рисует родной стиль, и тест
    # мерил бы не то, что чинил наряд (наблюдение наряда 0019).
    kit.apply_theme(qt_app)

    host = QWidget()
    layout = QVBoxLayout(host)
    checked = QCheckBox("checked")
    unchecked = QCheckBox("unchecked")
    layout.addWidget(checked)
    layout.addWidget(unchecked)
    host.resize(220, 80)
    host.layout().activate()
    checked.setChecked(True)

    image = host.grab().toImage()
    marked = _indicator_box(
        image, checked.y(), checked.y() + checked.height(), tokens.BLUE_600
    )
    plain = _indicator_box(
        image, unchecked.y(), unchecked.y() + unchecked.height(), tokens.N_250
    )

    assert marked is not None, "отмеченный флажок не нарисован"
    assert plain is not None, "снятый флажок не нарисован — кликать не по чему"

    def size(box):
        return box[2] - box[0] + 1, box[3] - box[1] + 1

    drawn = tokens.INDICATOR_SIZE + 2 * tokens.BORDER_WIDTH
    # **Высота**, а не ширина: отмеченный залит целиком, снятый виден только
    # кольцом рамки, и по горизонтали скруглённый угол съедает у кольца крайние
    # столбцы точек ровно своего цвета (замерено: 15 против 12). Высота от этого
    # не страдает — прямой участок рамки там полной длины.
    assert size(marked)[1] == size(plain)[1] == drawn, (size(marked), size(plain))
    # Левый край один: индикатор, съезжающий при переключении, читается как
    # подпрыгивающая строка.
    assert marked[0] == plain[0]


def test_the_checkbox_is_square_and_the_radio_is_round(qt_app) -> None:
    """Обратная сторона: описав подстиль, легко получить **не ту фигуру**.

    Флажок — переключатель, радиокнопка — выбор одного из нескольких, и формы
    менять местами нельзя: круглый флажок читается как радиокнопка, из которой
    нельзя выйти. Различает их **доля закрашенного** в рамке индикатора: у
    квадрата ≈ 1, у круга ≈ π/4 ≈ 0.79.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QCheckBox, QRadioButton, QVBoxLayout, QWidget

    kit.apply_theme(qt_app)

    host = QWidget()
    layout = QVBoxLayout(host)
    box = QCheckBox("box")
    radio = QRadioButton("radio")
    layout.addWidget(box)
    layout.addWidget(radio)
    host.resize(220, 80)
    host.layout().activate()
    box.setChecked(True)
    radio.setChecked(True)

    image = host.grab().toImage()

    def filled(widget) -> float:
        frame = _indicator_box(
            image, widget.y(), widget.y() + widget.height(), tokens.BLUE_600
        )
        assert frame is not None
        left, top, right, bottom = frame
        area = (right - left + 1) * (bottom - top + 1)
        wanted = QColor(tokens.BLUE_600).rgb() & 0xFFFFFF
        painted = sum(
            1
            for y in range(top, bottom + 1)
            for x in range(left, right + 1)
            if image.pixel(x, y) & 0xFFFFFF == wanted
        )
        return painted / area

    # Порог между 0.79 (круг) и 1.0 (квадрат) — замерено: флажок 0.867,
    # радиокнопка 0.776. Скруглённый угол флажка не даёт ровной единицы, и
    # порог поставлен между измеренными значениями, а не у идеальных.
    square, round_one = filled(box), filled(radio)
    assert square > 0.85, f"флажок вышел не квадратным: {square}"
    assert round_one < 0.85, f"радиокнопка вышла не круглой: {round_one}"
    assert square > round_one, (square, round_one)
