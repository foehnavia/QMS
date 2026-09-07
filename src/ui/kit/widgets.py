"""Компоненты канона §10: таблица, форма, кнопки, подсказка, пустое состояние.

Ни один экран не пишет число оформления сам — он собирает экран **отсюда**.
Правило держит гард `tests/test_ui_kit.py`: шестнадцатеричный цвет, кегль,
радиус или высота вне `src/ui/kit/` роняют прогон.

Сами значения живут в `tokens`, вид — в `theme`; здесь только сборка виджета и
те правила канона, которые стилем не выражаются: строка — единица выбора,
ячейка фокуса не берёт, высота строки одна на все состояния.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import tokens as t
from .direction import directional, iso
from .theme import (
    ROLE,
    ROLE_DANGER,
    ROLE_EMPTY_BODY,
    ROLE_EMPTY_TITLE,
    ROLE_HINT,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    ROLE_SECTION,
    ROLE_STATUS,
    ROLE_SUBTITLE,
    ROLE_TITLE,
)


def _roled(widget: QWidget, role: str) -> QWidget:
    """Пометить виджет ролью — по ней его и красит единый лист стиля."""
    widget.setProperty(ROLE, role)
    return widget


# --- кнопки ----------------------------------------------------------------------


def primary(text: str) -> QPushButton:
    """Основное действие экрана. Канон §4: **одно** на экран.

    Всё, что действует на выбранную строку, — вторичное: работа экрана — чтение,
    а не действие.
    """
    return _roled(QPushButton(iso(text)), ROLE_PRIMARY)


def secondary(text: str) -> QPushButton:
    return _roled(QPushButton(iso(text)), ROLE_SECONDARY)


def danger(text: str) -> QPushButton:
    """Разрушающее действие — **контуром**, не залитым красным блоком.

    Залитая красная кнопка читается как основное действие экрана, а удаление им
    не бывает никогда (канон §4).
    """
    return _roled(QPushButton(iso(text)), ROLE_DANGER)


def button_row(*buttons: QWidget, stretch_at_end: bool = True) -> QHBoxLayout:
    """Ряд действий с воздухом канона между кнопками."""
    row = QHBoxLayout()
    row.setSpacing(t.GAP_CONTROL)
    for button in buttons:
        row.addWidget(button)
    if stretch_at_end:
        row.addStretch(1)
    return row


# --- подписи ---------------------------------------------------------------------


def title(text: str) -> QLabel:
    return _roled(QLabel(iso(text)), ROLE_TITLE)


def subtitle(text: str) -> QLabel:
    return _roled(QLabel(iso(text)), ROLE_SUBTITLE)


def section_caption(text: str) -> QLabel:
    return _roled(QLabel(iso(text)), ROLE_SECTION)


def hint(text: str = "") -> QLabel:
    """Строка объяснения под контролом: говорит **почему**, а не что."""
    label = _roled(QLabel(iso(text) if text else ""), ROLE_HINT)
    label.setWordWrap(True)
    return label


def status_label(text: str = "") -> QLabel:
    label = _roled(QLabel(text), ROLE_STATUS)
    label.setWordWrap(True)
    return label


def section_header(text: str, caption: str = "") -> QWidget:
    """Заголовок раздела: имя экрана и строка о том, что сейчас показано.

    Подзаголовок держим виджетом на самом заголовке: он меняется вместе с
    выдачей («Measurement zones · 14 values»), а не описывает экран вообще.
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    box.title_label = title(text)
    box.caption_label = subtitle(caption)
    layout.addWidget(box.title_label)
    layout.addWidget(box.caption_label)
    box.caption_label.setVisible(bool(caption))
    box.setFixedHeight(t.SECTION_HEADER_HEIGHT)
    return box


def set_section_caption(header: QWidget, caption: str) -> QWidget:
    """Обновить строку подзаголовка — что именно показано сейчас."""
    header.caption_label.setText(iso(caption))
    header.caption_label.setVisible(bool(caption))
    return header


# --- форма -----------------------------------------------------------------------


def form() -> QFormLayout:
    """Форма «подпись + поле».

    Поле не растягивается на всю ширину: иначе значение уезжает от своей подписи
    через полэкрана и липнет к подписи соседней колонки (находка прогона В-1).
    """
    layout = QFormLayout()
    layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    layout.setHorizontalSpacing(t.GAP_CONTROL)
    layout.setVerticalSpacing(t.GAP_CONTROL)
    return layout


def stretching_form() -> QFormLayout:
    """Та же форма, но поле тянется — для форм ввода, где важна ширина поля."""
    layout = QFormLayout()
    layout.setHorizontalSpacing(t.GAP_CONTROL)
    layout.setVerticalSpacing(t.GAP_CONTROL)
    return layout


def column(*parts) -> QVBoxLayout:
    """Вертикаль с воздухом канона; последний растягивающийся аргумент — таблица."""
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(t.GAP_CONTROL)
    for part in parts:
        if isinstance(part, QWidget):
            layout.addWidget(part)
        else:
            layout.addLayout(part)
    return layout


def split_row(*parts) -> QHBoxLayout:
    """Ряд «панель + рабочая область»: зазор канона, панель своей ширины."""
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(t.GAP_CONTROL)
    for part in parts:
        if isinstance(part, QWidget):
            layout.addWidget(part)
        else:
            layout.addLayout(part)
    return layout


def boxed(layout) -> QWidget:
    """Уложить компоновку в виджет — колонка формы, ряд кнопок под виджет."""
    box = QWidget()
    box.setLayout(layout)
    return box


def screen_layout(widget: QWidget) -> QVBoxLayout:
    """Вертикаль экрана с отступом канона по краям."""
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(t.PAD_SCREEN, t.PAD_SCREEN, t.PAD_SCREEN, t.PAD_SCREEN)
    layout.setSpacing(t.GAP_CONTROL)
    return layout


def dialog_layout(widget: QWidget) -> QVBoxLayout:
    """Вертикаль диалога — тот же отступ, что у экрана: рамка одна на всё."""
    return screen_layout(widget)


# --- таблица ---------------------------------------------------------------------


# --- ширина колонки: класс содержимого, а не число на экране ----------------------

#: Класс → предел в знаках. Ширина — свойство **типа данных**: номер детали
#: одинаково широк в списке отклонений, в карточке и в привязке.
#: Ниже этой доли области таблица прижимается к левому краю, а не центрируется.
CENTRING_SHARE = 0.6

CONTENT_WIDTH = {
    "identifier": t.WIDTH_IDENTIFIER,
    "magnitude": t.WIDTH_MAGNITUDE,
    "date": t.WIDTH_DATE,
    "state": t.WIDTH_STATE,
    "counter": t.WIDTH_COUNTER,
    "text": t.WIDTH_TEXT,
    "link": t.WIDTH_LINK,
}

#: Слова подписей, по которым класс угадывается **по умолчанию**. Экран может
#: назвать класс сам (`content=`), но шестнадцать экранов ради этого не
#: переписываются: у большинства колонок класс читается из имени.
_BY_NAME = (
    ("date", "date"),
    ("counter", "qty"),
    ("counter", "findings"),
    ("counter", "inspections"),
    ("counter", "insp."),
    ("counter", "positions"),
    ("counter", "characteristics"),
    ("counter", "used by"),
    ("text", "explanation"),
    ("text", "comment"),
    ("link", "protocol"),
    ("link", "attachment"),
    ("link", "drawing"),
    ("state", "state"),
    ("state", "decision"),
    ("state", "result"),
    ("state", "zone"),
    ("state", "type"),
    ("state", "size"),
    ("state", "connection"),
    ("state", "groups"),
    ("state", "canon"),
    ("state", "value"),
)


def content_class(label: str, column: int, magnitude_columns: tuple[int, ...]) -> str:
    """Класс колонки: объявленный экраном, угаданный по подписи или базовый.

    Величина узнаётся не по имени, а по тому, что экран **уже объявил**
    (`magnitude_columns`): это тот же список, которым задаётся выравнивание, и
    заводить рядом второй значило бы дать им разойтись.
    """
    if column in magnitude_columns:
        return "magnitude"
    lowered = label.casefold()
    for name, needle in _BY_NAME:
        if needle in lowered:
            return name
    return "identifier"


#: Из каких знаков считается знакоместо. Не цифра: в шрифте канона `0` — семь
#: пикселей, а `M` — двенадцать, и колонка «на 12 знакомест», посчитанная
#: цифрой, резала восьмизначное `1 record` (замерено, предупреждение §7.3).
#: Объявление «ширина этой колонки — её заголовок, и только он» (§8.3, класс 2).
#: Ставится вместо числа знакомест у счётчиков и коротких фиксированных значений:
#: `0`, `15`, `9999`, `yes` не растут, заголовок задан нами и тоже не растёт, —
#: запас в четверть там не нужен ни с какой стороны.
FIT_LABEL = "label"

#: Метка «эту колонку рисует пилюля»: `kit.pill(14)` вместо голого `14`.
_PILL = "pill"


def pill(chars: int) -> tuple[str, int]:
    """Объявить колонку, которую рисует пилюля исхода (`DecisionPillDelegate`).

    Число знакомест остаётся тем же (§7.3), но к нему добавляется **оправа**
    пилюли: её собственные отступы и кружок. Без этого делегат режет подпись
    («Not deci…» на базе прогона), а замер по тексту ячейки обрезки не видит —
    рисует-то не текст, а пилюля, и шрифтом покрупнее.
    """
    return (_PILL, chars)


def slot_width(table) -> int:
    """Одно знакоместо — **средняя** ширина знака шрифта канона, не самая широкая.

    Замена самого широкого знака на средний — вторая доводка (§8.3). Разметку
    оператора по пикселям воспроизводит именно средний знак: текущая раскладка
    ложилась в `знакоместа × 12 px + 20`, где 12 — ширина `M`, а желаемая — в
    `знакоместа × ≈7.4 px + 20`. Гарантия от обрезки при этом не теряется: она
    сидит в запасе в четверть внутри самих чисел знакомест (§7.3), а не в том,
    что каждый знак считается за `M`.
    """
    return table.fontMetrics().horizontalAdvance("0")


def column_width(table, chars, label: str = "") -> int:
    """Ширина колонки в пикселях. Два класса содержимого — два расчёта (§8.3).

    `chars` — число знакомест **растущего** содержимого либо `FIT_LABEL` для
    счётчика: тогда ширину задаёт заголовок и ничего больше.

    Заголовок не переносится никогда — это нижняя граница обоих классов
    (правило 1 §7.3). Обрезанная подпись это колонка, про которую оператор не
    знает, что в ней (`spectior` вместо `Inspections` на первом снимке).
    """
    from .pills import PILL_CHROME  # noqa: PLC0415 — иначе круговой импорт

    metrics = table.fontMetrics()
    by_label = metrics.horizontalAdvance(label) if label else 0
    chrome = 0
    if isinstance(chars, tuple) and chars[0] == _PILL:
        chars, chrome = chars[1], PILL_CHROME
    by_slots = 0 if chars == FIT_LABEL else slot_width(table) * chars + chrome
    return max(by_slots, by_label) + t.PAD_CELL * 2


def _fit_columns(table, magnitude_columns, content, widths) -> None:
    """Раздать колонкам ширину. Ни одна не тянется.

    Порядок источников (решение §7.3): **объявленная экраном ширина** →
    объявленный класс → класс, угаданный по подписи. Угадывание осталось
    умолчанием для необъявленных колонок и только им: оно развело `Connection`
    (короткое содержимое, широкий класс) с `Item type` (длинное содержимое,
    узкий), потому что имена врут.
    """
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    for column in range(table.columnCount()):
        label = table.horizontalHeaderItem(column)
        caption = label.text() if label else ""
        if widths and column < len(widths) and widths[column] is not None:
            slots = widths[column]
        else:
            name = (
                content[column]
                if content and column < len(content)
                else content_class(caption, column, magnitude_columns)
            )
            slots = CONTENT_WIDTH[name]
        table.setColumnWidth(column, column_width(table, slots, caption))


def _centre_columns(table, width: int | None = None) -> None:
    """Центрировать полотно, а лишнюю ширину отдать отступам.

    Таблица уже своей области → отступы поровну по краям, и в них видна
    утопленная поверхность. Сумма колонок шире области → отступы исчезают и
    таблица прокручивается вбок: без этой второй половины сломались бы широкие
    экраны (правка пользователя к решению 02.09).
    """
    total = sum(table.columnWidth(column) for column in range(table.columnCount()))
    bar = table.verticalScrollBar()
    available = (table.width() if width is None else width) - table.frameWidth() * 2
    if bar.isVisible():
        available -= bar.width()
    # Центрируем **только** когда таблица занимает существенную часть области
    # (правило 3 §7.3). Поле шире самой таблицы читается как поломка, а не как
    # приём: на снимке Reference data так и вышло.
    margin = 0
    if available > 0 and total >= available * CENTRING_SHARE:
        margin = max((available - total) // 2, 0)

    # Отступ задаётся **листом стиля**, а не `setViewportMargins`: последние Qt
    # держит под свои заголовки, и правка их разводит шапку с телом — на снимке
    # это вышло смещённой шапкой и обрезанной первой строкой. Отступ листа —
    # часть коробки виджета, и полотно с шапкой едут вместе (замерено).
    if getattr(table, "_margin", None) == margin:
        return
    table._margin = margin
    # Селектор по типу, а не голое свойство: голое наследуют дети, и шапка
    # получала отступ **вторично** — на снимке подписи стояли на 334 px правее
    # своих колонок.
    table.setStyleSheet(
        f"QTableView {{ padding-left: {margin}px; padding-right: {margin}px; }}"
    )
    # Пересчёт стиля — синхронно. Иначе он ждёт следующего прохода цикла
    # событий, а снимки снимаются без него: на снимке шапка оставалась на
    # прежнем месте, пока тело уже переехало.
    table.style().unpolish(table)
    table.style().polish(table)


class DataTable(QTableWidget):
    """Таблица канона: полотно центрируется, лишняя ширина уходит в отступы.

    Пересчёт висит на `setGeometry`, а не на `resizeEvent`, и это не вкусовщина:
    скрытому виджету Qt событие изменения размера **не шлёт вовсе** — оно
    откладывается до показа. Снимки же снимаются без `show()` (`CLAUDE.md` §9),
    и на первом снимке таблица вышла прижатой влево при пустом поле справа.
    `setGeometry` зовёт раскладка независимо от видимости.
    """

    def setGeometry(self, rect) -> None:  # noqa: N802 - Qt API
        # Отступ считаем **до** раскладки и по новой ширине: поставленный после,
        # он до шапки не доезжает — она уже разложена, и на снимке подписи
        # уезжали относительно тела.
        _centre_columns(self, rect.width())
        super().setGeometry(rect)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        _centre_columns(self)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Показ — момент, когда ширина заведомо настоящая.

        Нужен потому, что `QWidget::setGeometry` в Qt **не виртуальный**:
        раскладка зовёт его в C++, мимо питоньей замены. Пересчёт на отрисовке
        пробовался и отвергнут — он меняет отступ уже после того, как разложена
        шапка, и та уезжает относительно тела (видно снимком).
        """
        super().showEvent(event)
        _centre_columns(self)



def dress_table(
    table: QTableWidget,
    *,
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
    content: tuple[str, ...] = (),
    widths: tuple[int, ...] = (),
    read_only: bool = True,
) -> QTableWidget:
    """Одеть **готовую** таблицу по канону §7.

    Отдельно от `data_table` потому, что таблица прецедентов — подкласс
    `QTableWidget` со своим `fill`, и одевать её надо тем же кодом, а не
    похожим: разошедшиеся настройки двух таблиц и есть та болезнь, ради
    которой заведён `kit`.
    """
    table.horizontalHeader().setFixedHeight(t.TABLE_HEADER_HEIGHT)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(t.TABLE_ROW_HEIGHT)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    # Границы колонок видимы: без них клик по ячейке в широкой таблице —
    # догадка, а не выбор (§3.1 наряда 0020).
    table.setShowGrid(True)
    # Ячейка однострочная (правило 2 §7.3): длинное режется с подсказкой, а не
    # разъезжается вниз. Двухстрочные ячейки и были первым, что назвал оператор.
    table.setWordWrap(False)

    # Полотно белое, поле вокруг него — утопленная поверхность.
    #
    # Лист стиля красит **и полотно тоже** (фон `QAbstractScrollArea` в QSS
    # достаётся viewport), поэтому палитры мало: на первом же снимке всё, что
    # правее последней колонки, вышло утопленным, а белыми остались только
    # ячейки. Полотну цвет задаём явно — и это единственный `setStyleSheet` вне
    # `theme`, потому что бывает он только у части виджета.
    table.viewport().setStyleSheet(f"background: {t.WHITE};")

    _fit_columns(table, magnitude_columns, content, widths)
    _centre_columns(table)

    if read_only:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    directional(table, numeric_columns, magnitude_columns)
    return table


def data_table(
    columns: tuple[str, ...],
    *,
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
    content: tuple[str, ...] = (),
    widths: tuple[int, ...] = (),
    read_only: bool = True,
) -> QTableWidget:
    """Таблица данных канона §7.

    Строка — единица выбора, ячейка фокуса не берёт, высота строки одна на все
    состояния (40, канон §3): три уровня раскрытия из макета не собраны, и
    второго вертикального состояния у таблицы нет.

    Направление ячейки — по её содержимому, числовые и величинные колонки
    объявляются списком, а не угадываются (канон §6).
    """
    table = DataTable(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    return dress_table(
        table,
        numeric_columns=numeric_columns,
        magnitude_columns=magnitude_columns,
        content=content,
        widths=widths,
        read_only=read_only,
    )


def inline_table_height(table: QTableWidget, *, short: bool = False) -> QTableWidget:
    """Высота вложенной таблицы в диалоге — из токенов, не из головы."""
    table.setFixedHeight(
        t.INLINE_TABLE_HEIGHT_SHORT if short else t.INLINE_TABLE_HEIGHT
    )
    return table


def slice_tabs() -> QTabWidget:
    """Полоса вкладок среза — 44 px, подчёркивание активной вкладки."""
    tabs = QTabWidget()
    tabs.tabBar().setExpanding(False)
    return tabs


# --- выбор одного из немногих ------------------------------------------------------


class Choice(QWidget):
    """Выбор одного из **не более пяти** взаимоисключающих значений — радиокнопками.

    Канон §4: выпадающий список прячет варианты и стоит лишнего клика; там, где
    оператор выбирает, **читая формулировки**, а не вспоминая их, варианты стоят
    на экране разом. Правило про компонент, а не про экран: список остаётся для
    открытых наборов — значений справочника, деталей, групп.

    **Умолчания нет.** Предвыбранная радиокнопка — это ответ, которого оператор
    не давал, а оба места применения (исход отклонения, вывод исследования)
    попадают в документ. `value()` возвращает `None`, пока не выбрано.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QRadioButton] = []
        self._values: list[object] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(t.GAP_PILL_ICON)

    def add(self, value: object, label: str, note: str = "") -> QRadioButton:
        """Добавить вариант; `note` — строка пояснения под ним."""
        button = QRadioButton(iso(label))
        self._group.addButton(button, len(self._buttons))
        self._buttons.append(button)
        self._values.append(value)
        self._layout.addWidget(button)
        if note:
            explanation = hint(note)
            explanation.setContentsMargins(t.PAD_SCREEN, 0, 0, 0)
            self._layout.addWidget(explanation)
        return button

    def value(self) -> object | None:
        """Что выбрано; `None` — ещё ничего."""
        for button, value in zip(self._buttons, self._values):
            if button.isChecked():
                return value
        return None

    def set_value(self, value: object) -> None:
        """Отметить вариант — при правке уже записанного решения."""
        for button, candidate in zip(self._buttons, self._values):
            if candidate == value:
                button.setChecked(True)
                return

    def buttons(self) -> list[QRadioButton]:
        return list(self._buttons)


# --- пустое состояние ------------------------------------------------------------


def empty_state(
    what: str,
    why: str,
    action: QPushButton | None = None,
    *,
    compact: bool = False,
) -> QWidget:
    """Пустое состояние канона §8: что пусто, почему и один выход.

    Пустая таблица, которая ничего не говорит, — это то, как оператор заключает
    «прецедентов не было» из экрана, который просто ничего не искал.

    **Два варианта, и выбор между ними не про место** (канон §8, ревизия 1.2):

    * полный — пустое состояние **экрана или вкладки**: пуста вся поверхность,
      и кнопка это выход из неё;
    * `compact=True` — одна строка без иконки и кнопки для **секции внутри**
      экрана, у которой есть соседи: выход принадлежит поверхности вокруг неё.

    Два полных состояния подряд в одном окне — не «мало вертикали», а неверный
    вариант компонента: обе секции были приняты за целые поверхности.
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    # Отступ меньше экранного: пустое состояние живёт **внутри** панели, у
    # которой отступ уже есть, и второй такой же съедает вертикаль у таблицы.
    layout.setContentsMargins(t.PAD_CELL, t.PAD_CELL, t.PAD_CELL, t.PAD_CELL)
    layout.setSpacing(t.GAP_PILL_ICON)

    heading = _roled(QLabel(iso(what)), ROLE_EMPTY_TITLE)
    body = _roled(QLabel(iso(why)), ROLE_EMPTY_BODY)
    body.setWordWrap(True)

    # Подписи держим на самом виджете: их читают и тесты, и экраны, которые
    # меняют текст под конкретную причину пустоты.
    box.title_label = heading
    box.body_label = body
    box.compact = compact

    if compact:
        # Одна строка: заголовок и объяснение читаются как фраза, а не как
        # заголовок с текстом под ним. Заголовок остаётся виджетом — по нему
        # экран меняет причину пустоты, — но в раскладку не идёт.
        heading.setVisible(False)
        body.setText(iso(f"{what} — {why}"))
        layout.addWidget(body)
        return box

    heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    body.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch(1)
    layout.addWidget(heading)
    layout.addWidget(body)
    if action is not None:
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(action)
        row.addStretch(1)
        layout.addLayout(row)
    layout.addStretch(1)
    return box


def set_empty_reason(box: QWidget, what: str, why: str) -> QWidget:
    """Сменить причину пустоты, не пересобирая виджет.

    Секция бывает пуста по разным причинам — «ещё не выбрана находка» и «по
    этой находке прецедентов нет» это разные ответы, и подменять один другим
    значит объяснять оператору не то, что он видит.
    """
    box.title_label.setText(iso(what))
    box.body_label.setText(iso(f"{what} — {why}" if box.compact else why))
    return box


# --- диалог ----------------------------------------------------------------------


def dialog_buttons(
    accept: str = "Save", reject: str = "Cancel"
) -> QDialogButtonBox:
    """Ряд «принять / отменить»: принять — основное действие диалога."""
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    save = buttons.button(QDialogButtonBox.StandardButton.Save)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    save.setText(iso(accept))
    cancel.setText(iso(reject))
    _roled(save, ROLE_PRIMARY)
    _roled(cancel, ROLE_SECONDARY)
    return buttons


def error_box(
    parent: QWidget | None, error: Exception, title: str = "Not saved"
) -> QMessageBox:
    """Собрать модальное сообщение об ошибке, но **не** показывать его.

    Отдельно от `show_error` по одной причине: показанный модальный диалог
    снять снимком нельзя — он ждёт ответа. Экран зовёт `show_error`, снимок —
    `error_box`, и оба получают ровно один и тот же виджет.
    """
    from domain.errors import DomainError

    if isinstance(error, DomainError):
        box = QMessageBox(QMessageBox.Icon.Warning, title, str(error), parent=parent)
    else:
        box = QMessageBox(
            QMessageBox.Icon.Critical,
            "Error",
            f"Unexpected error:\n{error}",
            parent=parent,
        )
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    return box


class UnexpectedErrorDialog(BaseException):
    """Тестовый режим: экран позвал `show_error` там, где тест ждал успеха.

    Наследует `BaseException`, а не `Exception`, намеренно (наряд 0027 §1.2):
    `show_error` зовут **изнутри** широких `except Exception` — из такого места
    обычное исключение поймал бы первый же обработчик выше по стеку, и отказ
    снова стал бы невидимым. `BaseException` проходит их насквозь и разрывает
    прогон с читаемым текстом.
    """


#: Тестовый режим `show_error` — включается **явным** флагом, не угадыванием.
#:
#: Угадывание по `sys.argv` или по переменной окружения было бы второй
#: дисциплиной поверх первой: оно молча не срабатывает там, где условие не
#: совпало, а именно молчание и есть болезнь, которую режим лечит.
_TEST_MODE = False


def set_test_mode(enabled: bool) -> None:
    """Включить/выключить тестовый режим `show_error` (зовёт `conftest.py`).

    Механизм вместо дисциплины (`CLAUDE.md` §9, «Модальные диалоги в тестах»).
    Правило перехвата требовало от каждого теста подменять `show_error`; отказ
    повторился в нарядах `0004`, `0019` и `0024`, и каждый раз прогон **вставал
    без единой строки вывода** — модальное окно под offscreen ждёт ответа вечно.
    В тестовом режиме то же место даёт красный тест с текстом отказа.
    """
    global _TEST_MODE
    _TEST_MODE = bool(enabled)


def in_test_mode() -> bool:
    """Включён ли тестовый режим `show_error`."""
    return _TEST_MODE


def show_error(parent: QWidget | None, error: Exception, title: str = "Not saved") -> None:
    """Показать ошибку оператору.

    Текст `DomainError` пишется в домене **для оператора** — показываем как есть
    и не перефразируем. Всё остальное — неожиданная ошибка, её текст показываем
    с пометкой.

    В тестовом режиме окно не показывается, а бросается `UnexpectedErrorDialog`
    с заголовком и текстом исходной ошибки. Тесты, проверяющие **путь отказа**,
    этого не видят: они подменяют `show_error` целиком (`ui.kit.show_error`), и
    подмена стоит раньше — до сюда дело не доходит (`CLAUDE.md` §9).
    """
    if _TEST_MODE:
        raise UnexpectedErrorDialog(f"{title}: {error}")
    error_box(parent, error, title).exec()
