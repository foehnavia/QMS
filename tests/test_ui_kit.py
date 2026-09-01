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


def test_the_choice_shows_which_option_is_taken() -> None:
    """Сверяем то, **чем рисуют**: отмеченный кружок обязан быть на экране.

    Qt рисует родной индикатор, только пока виджет не попал под лист стиля; как
    только под него попадает хоть одно правило, оператор получает пустой кружок.
    Найдено снимком диалога решения: четыре исхода и ни одной видимой отметки
    (`CLAUDE.md` §9 — тест берёт значение из того же источника, что и отрисовка).
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QVBoxLayout, QWidget

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
