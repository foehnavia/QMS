"""Компоненты канона §10: таблица, форма, кнопки, подсказка, пустое состояние.

Ни один экран не пишет число оформления сам — он собирает экран **отсюда**.
Правило держит гард `tests/test_ui_kit.py`: шестнадцатеричный цвет, кегль,
радиус или высота вне `src/ui/kit/` роняют прогон.

Сами значения живут в `tokens`, вид — в `theme`; здесь только сборка виджета и
те правила канона, которые стилем не выражаются: строка — единица выбора,
ячейка фокуса не берёт, высота строки одна на все состояния.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
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
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import tokens as t
from .direction import directional, iso
from .metrics import cell_chrome, delegate_chrome, frame_height, header_chrome
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


def icon_button(name: str, tip: str) -> QPushButton:
    """Действие **рядом со значением** — иконкой, без подписи.

    Размеры из канона §3: кнопка строки 24, иконка внутри строки 13. Подпись
    здесь была бы шире самого значения, а действие тут вспомогательное: основной
    способ прочесть обоснование — прочесть его, а не скопировать.

    Подсказка обязательна и передаётся аргументом: иконка без подписи обязана
    называть себя словами хотя бы при наведении, иначе оператор угадывает.
    """
    from .icons import icon  # noqa: PLC0415 — иначе круговой импорт

    button = QPushButton()
    button.setIcon(icon(name, t.N_500, t.ICON_ROW))
    button.setIconSize(QSize(t.ICON_ROW, t.ICON_ROW))
    button.setFixedSize(t.ROW_ACTION_HEIGHT, t.ROW_ACTION_HEIGHT)
    button.setToolTip(tip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return _roled(button, ROLE_SECONDARY)


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


def align_labels_to_first_line(layout: QFormLayout) -> QFormLayout:
    """Подпись и **первая строка** значения — на одной линии.

    По умолчанию `QFormLayout` центрирует подпись по высоте поля. Пока в поле
    одна строка текста, центр и верх совпадают и разницы не видно; стоит полю
    стать выше — переносом на вторую строку или соседом-виджетом выше текста, —
    подпись съезжает вниз относительно первой строки значения.

    Повод — прогон 09.09: у `Explanation` в шапке карточки рядом со значением
    появилась иконка копирования (24 px против ~17 px строки текста), высота ряда
    стала высотой кнопки, и подпись с значением встали на разные уровни.

    Выравнивание задаётся **явно**, а не достаётся умолчанием Qt: умолчание тут
    зависит от того, что окажется в ряду, то есть меняется само (`CLAUDE.md`
    §9а.22 — объявленное переопределяется тем, чего не объявляли).
    """
    layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return layout


class _ProseRow(QWidget):
    """Ряд поля-прозы: просит всю доступную ширину, а не свой `sizeHint`."""

    def sizeHint(self):  # noqa: N802 — имя от Qt
        hint = super().sizeHint()
        # Заведомо больше любой шапки приложения: раскладка обрежет по месту, и
        # поле получит **доступное**, а не то, что напросил ярлык. Число берётся
        # у объявленной ширины полного диалога, а не выдумывается.
        hint.setWidth(t.DIALOG_FULL)
        return hint


def prose_row(*parts: QWidget) -> QWidget:
    """**Именованное исключение** из правила `form()` — поле, чьё значение проза.

    `form()` объявляет `FieldsStayAtSizeHint`, и это ратификация находки прогона
    В-1: поля не растягиваются, иначе значение уезжает от своей подписи через
    полэкрана и липнет к подписи соседней колонки. Правило верно для реквизитов —
    номера, даты, количества, — и **здесь не отменяется**.

    Но у `QLabel` с переносом `sizeHint` не есть длина строки: Qt считает его
    эвристикой, и ярлык сам просит узкую коробку. Обоснование отклонения —
    единственное поле шапки, чьё значение длинная проза, — переносилось на вторую
    строку при пустой правой половине шапки (прогон 09.09).

    Исключение именованное и **одно**: ряд просит доступную ширину и не ставит
    распорку в конец — иначе свободную ширину забрала бы она, а не значение.

    Потолок читаемости `FREE_TEXT_CHARS` сюда **не применяется**: это поле-ярлык,
    а не колонка таблицы, и перенос для него законен, когда текст правда длинный.
    Требование — не переносить, **пока ширина есть**.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(t.GAP_CONTROL)
    for part in parts:
        row.addWidget(part)
    box = _ProseRow()
    box.setLayout(row)
    box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return box


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

#: Объявление «ширина этой колонки — её заголовок, и только он» (§8.3, класс 2).
#: Ставится у счётчиков и коротких фиксированных значений: `0`, `15`, `9999`,
#: `yes` не растут, заголовок задан нами и тоже не растёт.
#:
#: Единственный класс, который меряется зазором **заголовка** (20 px), а не
#: ячейки (27): ширину задаёт подпись, содержимое у́же неё по построению.
#: Заголовок добавочного отступа отрисовки не платит, и приписать ему семь
#: пикселей ячейки значило бы раздуть каждую такую колонку — а у
#: `card_dialog.PRECEDENT_WIDTHS` запас до полотна ровно один пиксель.
#: Отсюда же ответ на «`Revision` и `Insp.` режутся»: не режутся — замер по
#: ячейке приписывал заголовку чужой зазор (наряд `0034` §1).
FIT_LABEL = "label"

#: Метка «эту колонку рисует пилюля исхода»: `kit.pill(labels)`.
_PILL = "pill"

#: Метка «ширина этой колонки объявлена в пикселях»: `kit.px(200)`.
_PX = "px"

#: Класс §2: **закрытый список** — ширину даёт самое длинное значение справочника.
_CLOSED = "closed"

#: Класс §2: **жёсткий формат** — ширину даёт эталонная строка формата.
_FIXED = "fixed"

#: Класс §2: **свободный текст** — ширину даёт остаток полотна, с потолком.
_FREE = "free"

#: Объявление свободной колонки. Значением, а не вызовом: она ничего не несёт,
#: кроме самого факта «эта колонка забирает остаток».
FREE = (_FREE, None)


#: Класс, угаданный по подписи, → **эталонная строка** его формата.
#:
#: Замена семи знакоместных чисел (наряд `0034` §2). Строка — реальное значение
#: этого формата, а не «сколько-то знаков»: `QFontMetrics` меряет её тем самым
#: шрифтом, которым колонку и нарисуют, поэтому запас в четверть больше не нужен
#: ни с какой стороны. Дата по этому замеру получает 69 px вместо прежних 104 —
#: разница и есть та догадка, которую наряд снимает.
#:
#: Угадывание остаётся **умолчанием для необъявленных** колонок и только им:
#: экран, знающий своё содержимое, объявляет класс сам (`closed` / `fixed` /
#: `free`), и это всегда точнее подписи.
CONTENT_SAMPLE = {
    # `DEV-260903-0001` — самый длинный бизнес-номер приложения.
    "identifier": "DEV-260903-0001",
    # Величина со знаком — одна неделимая ячейка (`CLAUDE.md` §9).
    "magnitude": "+ 0.05 / − 0.05",
    "date": "09.09.2026",
    # Состояние — подпись самого длинного исхода; пилюля добавляет оправу сама.
    "state": "Not permitted",
    # Счётчик не растёт: ширину ему задаёт заголовок и только он.
    "counter": FIT_LABEL,
    "text": FREE,
    "link": FREE,
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


def px(pixels: int) -> tuple[str, int]:
    """Объявить **точную** ширину колонки в пикселях, без пересчёта знакомест.

    Знакоместа (§7.3 наряда 0020) — способ вывести ширину там, где её никто не
    вывел за нас. Там, где сетка **нарисована** и её числа лежат в канве
    (список отклонений, `docs/design/canvas/MIS-QMS Deviations List.dc.html`),
    выводить нечего: пересчёт через среднюю ширину знака дал бы другие числа, и
    сумма перестала бы сходиться с той, что проверена дизайном.

    Пола по заголовку здесь **нет** намеренно. Он молча расширил бы колонку и
    сумма разошлась бы с канвой — а наряд `0028` говорит прямо: не сходится —
    вопрос Cowork, а не подгонка. Обрезанный заголовок при объявленных пикселях
    ловится замером на нативной платформе (`tools/screenshots.py`), а не тихой
    правкой ширины.
    """
    return (_PX, pixels)


def pill(labels) -> tuple[str, tuple[str, ...]]:
    """Объявить колонку, которую рисует пилюля исхода (`DecisionPillDelegate`).

    Принимает **закрытый список подписей**, а не число знакомест (наряд `0034`
    §2): исход — значение контролируемого словаря, и самое длинное из них можно
    измерить, а не оценить. К замеру добавляется оправа пилюли (`PILL_CHROME`):
    её собственные отступы и кружок. Без оправы делегат режет подпись
    («Not deci…» на базе прогона), а замер по тексту ячейки обрезки не видит —
    рисует-то не текст, а пилюля, и шрифтом покрупнее.
    """
    return (_PILL, tuple(labels))


def closed(values) -> tuple[str, tuple[str, ...]]:
    """Класс §2: **закрытый список** — ширина по самому длинному значению.

    Значения приходят из справочника, поэтому колонка пересчитывается сама,
    стоит оператору завести новое: догадок здесь не остаётся по построению.
    Пустой список означает «справочник ещё не прочитан» — колонка садится на
    свой заголовок, а не схлопывается.
    """
    return (_CLOSED, tuple(str(value) for value in values))


def fixed(sample: str) -> tuple[str, str]:
    """Класс §2: **жёсткий формат** — ширина по эталонной строке формата.

    Эталон — реальное значение (`DEV-260903-0001`, `09.09.2026`, `W26007336`), а
    не «столько-то знаков»: меряет его тот же шрифт, которым колонку нарисуют.
    """
    return (_FIXED, sample)


def free() -> tuple[str, None]:
    """Класс §2: **свободный текст** — ширина из остатка полотна, с потолком."""
    return FREE


def slot_width(table) -> int:
    """Одно знакоместо — **средняя** ширина знака шрифта канона.

    **Раздачей ширины больше не занимается** (наряд `0034` §2). Осталось для
    сообщений и диагностики, где нужен ориентир «сколько это примерно знаков»:
    ширину колонки теперь даёт замер самого содержимого, а не знакоместа с
    запасом в четверть.
    """
    return table.fontMetrics().horizontalAdvance("0")


def free_text_width(table) -> int:
    """Потолок колонки свободного текста в пикселях — `FREE_TEXT_CHARS` знаков.

    Знаки переводятся в пиксели знакоместом: сам предел объявлен в знаках,
    потому что читаемость меряется словами, а не пикселями (`tokens` §3).
    """
    return slot_width(table) * t.FREE_TEXT_CHARS + cell_chrome(table)


def content_need(table, spec) -> int:
    """Сколько пикселей просит **содержимое** колонки, без непечатаемого.

    Ноль означает «содержимое ширины не требует»: так отвечают `FIT_LABEL`
    (ширину задаёт заголовок) и свободный текст (ширину задаёт остаток).
    """
    metrics = table.fontMetrics()
    if spec == FIT_LABEL:
        return 0
    if isinstance(spec, tuple):
        kind, value = spec
        if kind == _FREE:
            return 0
        if kind == _CLOSED:
            return max((metrics.horizontalAdvance(v) for v in value), default=0)
        if kind == _FIXED:
            return metrics.horizontalAdvance(value)
        if kind == _PILL:
            from .pills import PILL_CHROME, pill_font  # noqa: PLC0415 — круговой импорт

            pill_metrics = QFontMetrics(pill_font(table.font()))
            widest = max((pill_metrics.horizontalAdvance(v) for v in value), default=0)
            return widest + PILL_CHROME
    raise TypeError(
        f"column width spec must be kit.closed/fixed/free/pill/px/FIT_LABEL, got {spec!r}"
    )


def column_width(table, spec, label: str = "") -> int:
    """Ширина колонки в пикселях: **замер содержимого**, пол — заголовок (§2).

    Непечатаемое прибавляется **замеренное**, и у каждого рисующего оно своё:
    заголовок 20, делегат пилюли 21, текст под стилем 27 (`kit.metrics`). До
    наряда `0034` здесь стояло `+ PAD_CELL * 2` = 20 на всё подряд, то есть
    текстовая колонка недобирала семь пикселей и резалась при идеально
    сходившейся сумме; рядом, в `deviation_view`, жила вторая формула той же
    величины. Теперь место одно.

    Заголовок не переносится никогда — это нижняя граница любого класса
    (правило 1 §7.3). Обрезанная подпись это колонка, про которую оператор не
    знает, что в ней (`spectior` вместо `Inspections` на первом снимке).

    **`kit.px(N)` возвращает ровно `N`**: объявленные пиксели уже полные, и
    прибавка сдвинула бы каждую нарисованную сетку (§1.3 наряда).
    """
    if isinstance(spec, tuple) and spec[0] == _PX:
        return spec[1]

    by_label = (
        table.fontMetrics().horizontalAdvance(label) + header_chrome(table)
        if label
        else 0
    )
    need = content_need(table, spec)
    by_content = need + content_chrome(table, spec) if need else 0
    return max(by_content, by_label)


def content_chrome(table, spec) -> int:
    """Чей зазор платит эта колонка — **того, кто её рисует**.

    Пилюлю рисует делегат своими руками и добавочного отступа отрисовки текста не
    платит (`delegate_chrome`); обычную ячейку рисует стиль, и платит
    (`cell_chrome`). Разница 6 px, и без неё колонка пилюли получала бы лишнее, а
    текстовая — недобирала.
    """
    if isinstance(spec, tuple) and spec[0] == _PILL:
        return delegate_chrome(table)
    return cell_chrome(table)


def column_specs(table, magnitude_columns, content, widths) -> list:
    """Чем объявлена каждая колонка — **чистый разбор**, без установки ширин.

    Порядок источников (решение §7.3): **объявленная экраном ширина** →
    объявленный класс → класс, угаданный по подписи. Угадывание осталось
    умолчанием для необъявленных колонок и только им: оно развело `Connection`
    (короткое содержимое, широкий класс) с `Item type` (длинное содержимое,
    узкий), потому что имена врут.

    Вынесено из `_fit_columns` отдельной функцией, потому что раздача остатка
    (§3) обязана знать состав **до** того, как назначит хоть одну ширину:
    свободной колонке достаётся то, что осталось от всех прочих.
    """
    specs = []
    for column in range(table.columnCount()):
        label = table.horizontalHeaderItem(column)
        caption = label.text() if label else ""
        if widths and column < len(widths) and widths[column] is not None:
            spec = widths[column]
        else:
            name = (
                content[column]
                if content and column < len(content)
                else content_class(caption, column, magnitude_columns)
            )
            spec = CONTENT_SAMPLE[name]
            if isinstance(spec, str) and spec not in (FIT_LABEL,):
                spec = fixed(spec)
        specs.append((spec, caption))
    return specs


def _is_free(spec) -> bool:
    return isinstance(spec, tuple) and spec[0] == _FREE


def share_remainder(table, specs, limit: int) -> dict[int, int]:
    """Сколько достаётся каждой свободной колонке — **чистый расчёт** (§3).

    Порядок раздачи, единый для всех таблиц:

    1. считается сумма колонок известной ширины — она не плавает;
    2. остаток до предела полотна делится между колонками свободного текста;
    3. выше потолка читаемости (`FREE_TEXT_CHARS` знаков) колонка не растёт
       **никогда**, сколько бы места ни осталось;
    4. **остаток сверх потолка не раздаётся никому** — таблица просто у́же своей
       области. Это и есть механический запрет на «колонку с тремя словами во всю
       ширину экрана»: тянуть больше некому и нечем.

    Свободных колонок на экране может не быть вовсе (`cg_view`, `reference_view`,
    `mapping_dialog` и др.) — тогда остаток не раздаётся и таблица у́же полотна.
    Это штатное состояние, а не дефект раскладки (§3.5).

    Чистая функция по той же причине, что `centring_margin` и `table_height`
    (`CLAUDE.md` §9а.15): величину, от которой зависит раскладка, надо уметь
    проверить арифметикой, не поднимая экран.
    """
    free_columns = [i for i, (spec, _) in enumerate(specs) if _is_free(spec)]
    if not free_columns:
        return {}

    floors = {i: column_width(table, specs[i][0], specs[i][1]) for i in free_columns}
    taken = sum(
        column_width(table, spec, caption)
        for i, (spec, caption) in enumerate(specs)
        if not _is_free(spec)
    )
    ceiling = free_text_width(table)
    spare = max(limit - taken, 0)

    share = spare // len(free_columns)
    return {i: max(min(share, ceiling), floors[i]) for i in free_columns}


def refit_columns(table, widths, *, limit: int | None = None) -> None:
    """Пересчитать ширины **по загруженным данным**.

    Ради этого вызова класс «закрытый список» и заведён: при сборке таблицы
    справочник ещё не прочитан, и колонка садится на свой пол по заголовку.
    Экран, дочитав строки, отдаёт сюда фактические значения — и колонка встаёт по
    самому длинному из них. Завёл оператор значение длиннее прежнего — колонка
    выросла сама, без правки кода: «догадок здесь не остаётся по построению»
    (наряд `0034` §2).

    Зовётся из `reload`, а не из раскладки: ширина зависит от данных, и пересчёт
    по событию раскладки уводил бы её в рекурсию (`CLAUDE.md` §9а.15).

    **Предел полотна по умолчанию берётся у самой таблицы** (`canvas_width`), а не
    считается нулём. До наряда `0035` умолчанием был `limit = 0`, то есть «остаток
    не раздавать», и раздача не доезжала до приложения ни разу: строки `limit=` в
    `src/ui` не было вовсе. Функция работала, её никто не звал (§0 наряда `0035`).
    Ноль остаётся выразимым — его передают явно там, где раздавать нечего.
    """
    specs = [
        (widths[column], _caption(table, column)) for column in range(table.columnCount())
    ]
    if limit is None:
        limit = canvas_width(table)
    shares = share_remainder(table, specs, limit) if limit else {}
    for column, (spec, caption) in enumerate(specs):
        table.setColumnWidth(column, shares.get(column) or column_width(table, spec, caption))
    _centre_columns(table)


def _caption(table, column: int) -> str:
    label = table.horizontalHeaderItem(column)
    return label.text() if label else ""


def column_values(table, column: int) -> list[str]:
    """Что **сейчас** стоит в колонке — сырьё для `kit.closed` при пересчёте."""
    return [
        table.item(row, column).text()
        for row in range(table.rowCount())
        if table.item(row, column) is not None
    ]


def _fit_columns(table, magnitude_columns, content, widths, limit: int = 0) -> None:
    """Раздать колонкам ширину. Ни одна не тянется.

    Свободные колонки получают остаток только когда предел полотна известен
    (`limit`); без него они садятся на свой пол по заголовку, а ширину им
    назначит экран, когда узнает свою ширину, — через `refit_columns`.
    """
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)

    specs = column_specs(table, magnitude_columns, content, widths)
    shares = share_remainder(table, specs, limit) if limit else {}
    for column, (spec, caption) in enumerate(specs):
        width = shares.get(column) or column_width(table, spec, caption)
        table.setColumnWidth(column, width)


#: Предел вложенности пересчёта центрирования. Раскладка зовёт его синхронно, и
#: несходящийся пересчёт уходит в рекурсию, а не в мигание: стек переполняется, и
#: процесс умирает без питоновской трассы. Законных вложений не бывает больше двух.
CENTRING_DEPTH_LIMIT = 8


def centring_margin(table, width: int | None = None) -> int:
    """Каким должен быть отступ полотна — **чистый расчёт**, без побочных действий.

    Вынесен из `_centre_columns` доводкой 2 наряда `0028`, чтобы свойство, в
    котором жил стоп-дефект, стало проверяемым **на любой платформе**. Свойство
    одно: у расчёта обязана быть неподвижная точка — посчитанный отступ, будучи
    применённым, обязан пересчитаться сам в себя.

    **Свой отступ вычитать нельзя — иначе выход функции становится её входом.**
    Отступ задаётся листом стиля, а Qt считает его частью `frameWidth()`. Без
    поправки `current * 2` неподвижной точки не существует вовсе:

        margin 0  -> frameWidth 1  -> available 1238 -> margin 11
        margin 11 -> frameWidth 12 -> available 1216 -> margin 0

    Гард `_margin == margin` такого не ловит: значение не повторяется, оно
    **чередуется**. А раскладка зовёт пересчёт синхронно, поэтому на нативной
    платформе колебание уходит в неограниченную рекурсию — переполнение стека и
    смерть процесса без питоновской трассы. Под offscreen оно затухает, и прогон
    этого не видел (`CLAUDE.md` §9а.13).
    """
    total = sum(table.columnWidth(column) for column in range(table.columnCount()))
    available = canvas_width(table, width)
    # Центрируем **только** когда таблица занимает существенную часть области
    # (правило 3 §7.3). Поле шире самой таблицы читается как поломка, а не как
    # приём: на снимке Reference data так и вышло.
    if available > 0 and total >= available * CENTRING_SHARE:
        return max((available - total) // 2, 0)
    return 0


def canvas_width(table, width: int | None = None) -> int:
    """Сколько ширины на самом деле достаётся колонкам — **полотно**.

    Одно выражение на два вопроса: сколько отдать отступам (центрирование) и
    сколько раздать свободным колонкам (§3 наряда `0034`). Держать их врозь
    значило бы дать им разойтись — а такие пары расходятся всегда.

    Собственный отступ **прибавляется обратно** (`current * 2`): его задаёт лист
    стиля, а Qt считает его частью `frameWidth()`, и без поправки величина,
    которую расчёт задаёт, вошла бы в его же вход. Подробно и с ценой ошибки —
    в `centring_margin` (`CLAUDE.md` §9а.15).
    """
    current = getattr(table, "_margin", 0) or 0
    available = (
        (table.width() if width is None else width) - table.frameWidth() * 2 + current * 2
    )
    bar = table.verticalScrollBar()
    # Признак — **есть ли что прокручивать**, а не `isVisible()`. У ребёнка
    # непоказанного окна `isVisible()` ложно всегда (`CLAUDE.md` §9а.5), и отступ
    # считался так, будто полосы нет: на карточке с раскрытыми строками полотно
    # ужималось до 1054, отступ оставался прежним, и колонка уезжала за правый
    # край при сумме, которая не менялась ни на пиксель (наряд `0032` §2).
    # `maximum() > 0` означает ровно «полоса нужна» и верно и до показа окна.
    if bar.maximum() > 0:
        available -= bar.width()
    return max(available, 0)


def recentre_columns(table, width: int | None = None) -> None:
    """Пересчитать центрирование полотна — после того, как содержимое изменилось.

    Публичный вход к тому же расчёту. Нужен там, где **вертикальная** полоса
    появляется позже раздачи ширин: она забирает у полотна свои шестнадцать
    пикселей, а отступ, посчитанный до неё, остаётся прежним, и колонка уезжает
    за правый край при идеально сошедшейся сумме.

    Замерено на карточке (наряд `0032` §2): свёрнутая таблица — полотно 1064 при
    сумме 1063, полосы нет; раскрыл строки — полотно 1054, и одна колонка за
    краем. Сумма при этом не менялась ни на пиксель.
    """
    _centre_columns(table, width)


def _centre_columns(table, width: int | None = None) -> None:
    """Центрировать полотно, а лишнюю ширину отдать отступам.

    Таблица уже своей области → отступы поровну по краям, и в них видна
    утопленная поверхность. Сумма колонок шире области → отступы исчезают и
    таблица прокручивается вбок: без этой второй половины сломались бы широкие
    экраны (правка пользователя к решению 02.09).

    Сам расчёт — в `centring_margin`; здесь применение и сторож сходимости.
    """
    margin = centring_margin(table, width)

    # Отступ задаётся **листом стиля**, а не `setViewportMargins`: последние Qt
    # держит под свои заголовки, и правка их разводит шапку с телом — на снимке
    # это вышло смещённой шапкой и обрезанной первой строкой. Отступ листа —
    # часть коробки виджета, и полотно с шапкой едут вместе (замерено).
    if getattr(table, "_margin", None) == margin:
        return

    # Сторож несходимости — **механизм, а не дисциплина**: тот же довод, что
    # закрыл `show_error` (QMS-021) и канон-хеш на приёмке. Расчёт выше сходится;
    # если он когда-нибудь снова перестанет, здесь будет красный тест с читаемым
    # текстом, а не смерть процесса без трассы.
    depth = getattr(table, "_centring_depth", 0) + 1
    table._centring_depth = depth
    try:
        if depth > CENTRING_DEPTH_LIMIT:
            raise RuntimeError(
                f"centring did not converge: {depth} nested passes, "
                f"margin {getattr(table, '_margin', None)} -> {margin}. "
                "The padding this function sets is being read back as frame width."
            )
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
    finally:
        table._centring_depth = depth - 1


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
    """Высота вложенной таблицы в диалоге — из токенов, не из головы.

    Жёсткий низ. Годится там, где таблица **накапливается по ходу работы** и её
    высота не должна прыгать на каждой добавленной строке — форма отклонения. В
    диалоге, который **читают**, он вреден: см. `fit_table_height` ниже.
    """
    table.setFixedHeight(
        t.INLINE_TABLE_HEIGHT_SHORT if short else t.INLINE_TABLE_HEIGHT
    )
    return table


def table_height(rows: int, view: QTableWidget | None = None) -> int:
    """Сколько пикселей занимает таблица с `rows` строками — шапка, строки и рамка.

    Чистая функция: то же свойство, что у `centring_margin`, и по той же причине
    (`CLAUDE.md` §9а.15) — величину, от которой зависит раскладка, надо уметь
    проверить арифметикой, не поднимая экран.

    **`view` даёт рамку, и без него ответ неполон.** Лист стиля отнимает у полотна
    два пикселя (`metrics.frame_height`), и высоты `30 + 40n` последней строке не
    хватает ровно на них: Qt рисует полосу прокрутки там, где прокручивать нечего
    (наряд `0036` §0, подтверждено замером — недобор ровно 2 на всех таблицах).
    Аргумент необязателен там, где виджета ещё нет и считается **пол** раскладки,
    а не высота конкретной таблицы: рамка там прибавится своим владельцем.
    """
    height = t.TABLE_HEADER_HEIGHT + max(rows, 0) * t.TABLE_ROW_HEIGHT
    return height + (frame_height(view) if view is not None else 0)


def fit_table_height(table: QTableWidget, *, rows: int) -> QTableWidget:
    """Высота **по содержимому**: шапка плюс фактические строки, но не больше
    `rows`; дальше — прокрутка внутри таблицы.

    Повод — наряд `0032` §1. `INLINE_TABLE_HEIGHT = 150` стоял низом сразу у трёх
    мест карточки, и таблица с одной находкой получала 150 вместо нужных 70.
    Полторы сотни пикселей отнимались у единственного места, ради которого
    карточку открывают, — у сравнения с прецедентами.

    Потолок — не украшение: выше него карточка перестаёт быть обзором, и таблица
    начинает прокручиваться сама, вместо того чтобы выдавливать соседей.

    **Пустая таблица получает ноль, а не высоту шапки.** Шапка над нулём строк —
    это ровно тот повтор оформления, из-за которого экран читается лоскутным
    одеялом; пустое состояние рядом объясняет пустоту словами.
    """
    visible = min(table.rowCount(), rows)
    table.setFixedHeight(table_height(visible, table) if visible else 0)
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


def table_limit(window_width: int) -> int:
    """Ширина, которой таблица не превышает: доля окна, но не уже пола.

    `design-system.md` §3, revision 1.8: «at most 90 % of the window, **and never
    narrower than 1216**» — 1728 при 1920, 1216 при 1280.

    Пол здесь не подстраховка, а **ревизия пустого места** (QMS-018): при
    минимальном окне прежняя доля отдавала 128 px чистого фона, пока колонки
    голодали настолько, что `W26007336` резался до `W260073…`. Живёт в `kit`, а
    не на экране: правило про таблицы вообще, и второй экран, который до него
    доберётся, обязан получить то же число, а не похожее.
    """
    return max(int(window_width * t.TABLE_SHARE), t.TABLE_WIDTH_FLOOR)
