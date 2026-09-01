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


def dress_table(
    table: QTableWidget,
    *,
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
    read_only: bool = True,
) -> QTableWidget:
    """Одеть **готовую** таблицу по канону §7.

    Отдельно от `data_table` потому, что таблица прецедентов — подкласс
    `QTableWidget` со своим `fill`, и одевать её надо тем же кодом, а не
    похожим: разошедшиеся настройки двух таблиц и есть та болезнь, ради
    которой заведён `kit`.
    """
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setFixedHeight(t.TABLE_HEADER_HEIGHT)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(t.TABLE_ROW_HEIGHT)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setShowGrid(False)
    if read_only:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    directional(table, numeric_columns, magnitude_columns)
    return table


def data_table(
    columns: tuple[str, ...],
    *,
    numeric_columns: tuple[int, ...] = (),
    magnitude_columns: tuple[int, ...] = (),
    read_only: bool = True,
) -> QTableWidget:
    """Таблица данных канона §7.

    Строка — единица выбора, ячейка фокуса не берёт, высота строки одна на все
    состояния (40, канон §3): три уровня раскрытия из макета не собраны, и
    второго вертикального состояния у таблицы нет.

    Направление ячейки — по её содержимому, числовые и величинные колонки
    объявляются списком, а не угадываются (канон §6).
    """
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    return dress_table(
        table,
        numeric_columns=numeric_columns,
        magnitude_columns=magnitude_columns,
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


def show_error(parent: QWidget | None, error: Exception, title: str = "Not saved") -> None:
    """Показать ошибку оператору.

    Текст `DomainError` пишется в домене **для оператора** — показываем как есть
    и не перефразируем. Всё остальное — неожиданная ошибка, её текст показываем
    с пометкой.
    """
    error_box(parent, error, title).exec()
