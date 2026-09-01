"""Токены дизайн-системы — единственное место, где живут числа оформления.

Соответствие один в один с `docs/design/design-system.md` §1–§3 (ревизия 1.1):
имя константы = имя токена канона, значение = значение канона. Ничего
производного здесь не считается — производные собирает `theme`.

Гард `tests/test_ui_kit.py` следит, чтобы шестнадцатеричный цвет, кегль,
радиус и высота не появились нигде в `src/ui/`, кроме этого пакета.
"""

from __future__ import annotations

# --- §1 Colour: синий — единственный акцент --------------------------------------

BLUE_50 = "#EFF5FE"
BLUE_100 = "#E4EDFC"
BLUE_500 = "#3B7BE8"
BLUE_600 = "#2563D9"
BLUE_700 = "#1B4FBF"
BLUE_HALO = "#DCE7FB"

# --- §1 Colour: нейтральные, холодные --------------------------------------------

WHITE = "#FFFFFF"
N_50 = "#F7F9FB"
N_100 = "#EFF2F5"
N_200 = "#E3E7EC"
N_250 = "#DCE0E6"
N_300 = "#C7CDD5"
N_350 = "#A9B1BC"
N_400 = "#8B94A1"
N_450 = "#B4BCC7"
N_500 = "#6C7683"
N_600 = "#4A525D"
N_700 = "#3C444E"
N_900 = "#1B2027"

# --- §1 Colour: лента навигации — единственная тёмная плоскость ------------------

RIBBON = "#16324F"
RIBBON_TEXT = "#FFFFFF"
RIBBON_MUTED = "#9FB3CC"
RIBBON_ACTIVE = "#1E4470"
RIBBON_BORDER = "#0F2438"

# --- §1 Colour: решение — четыре исхода плюс открытое состояние ------------------

#: `code -> (фон, текст, точка)`. `None` в фоне — пилюля рисуется контуром;
#: контурная ровно одна, и это «решения ещё нет» (канон §1).
DECISION_COLOURS: dict[str | None, tuple[str | None, str, str]] = {
    None: (None, N_500, N_350),
    "approved": ("#E4F4EA", "#1E6B3F", "#2E9155"),
    "rejected": ("#FCE8E8", "#99312F", "#C7433F"),
    "sorting": ("#FDF0DC", "#8A5A15", "#C58A2A"),
    "repair": ("#EFE7FA", "#5C3D96", "#8763C7"),
}

#: Рамка контурной пилюли и опасной кнопки — цвета, которых нет в шкале выше.
PILL_DASH = N_300
DANGER_BORDER = "#F0CFCE"
DANGER_TEXT = "#99312F"

# --- §2 Type ---------------------------------------------------------------------

#: Подтверждено `QFontDatabase` на целевой машине (наряд 0011 §1): все три
#: установлены и несут иврит. Цифры равной ширины по умолчанию — `tnum` не нужен.
FONT_STACK = ('"Segoe UI"', '"Arial"', '"Tahoma"')
FONT_FAMILY = ", ".join(FONT_STACK)

#: Кегли — точками, как в каноне; Qt берёт дробный размер через `setPointSizeF`.
SIZE_TITLE = 18.0
SIZE_SUBTITLE = 11.5
SIZE_BODY = 13.0
SIZE_HEADER = 11.0
SIZE_PILL = 11.5
SIZE_STATUS = 11.5
SIZE_CAPTION = 10.5

WEIGHT_TITLE = 650
WEIGHT_IDENTIFIER = 600
WEIGHT_HEADER = 700
WEIGHT_PILL = 600
WEIGHT_BODY = 400

# --- §3 Metrics: высоты зон ------------------------------------------------------

RIBBON_HEIGHT = 44
SECTION_HEADER_HEIGHT = 64
TAB_STRIP_HEIGHT = 44
TOOLBAR_HEIGHT = 52
TABLE_HEADER_HEIGHT = 34
TABLE_ROW_HEIGHT = 40
FOOTER_HEIGHT = 36

#: Панель внутри экрана — список списков справочников (макет S2: 280, зазор 8).
#: Это **не** боковое меню: навигация — лента, а панель принадлежит экрану.
PANEL_WIDTH = 280

#: Знак приложения на ленте — квадрат с буквой (макет S1).
RIBBON_MARK_SIZE = 22

#: Иконки: 16 в навигации и на панели действий, 13 в строке и в пилюле,
#: 34 в пустом состоянии (канон §3).
ICON_NAV = 16
ICON_ROW = 13
ICON_EMPTY = 34


# --- §3 Metrics: контролы --------------------------------------------------------

BUTTON_HEIGHT = 32
TOOLBAR_BUTTON_HEIGHT = 30
NAV_ITEM_HEIGHT = 32
PILL_HEIGHT = 22
ROW_ACTION_HEIGHT = 24

# --- §3 Metrics: радиусы, штрихи, воздух -----------------------------------------

RADIUS_CONTROL = 5
RADIUS_PANEL = 7
RADIUS_ROW_ACTION = 4
RADIUS_PILL = 11

BORDER_WIDTH = 1
SELECTION_BAR_WIDTH = 2
FOCUS_HALO_WIDTH = 3

PAD_SCREEN = 20
PAD_RIBBON_H = 16
#: Отступ внутри пункта ленты (макет S1: 14, при сжатии 10).
PAD_NAV_ITEM = 14
PAD_CELL = 10
GAP_CONTROL = 8
GAP_NAV_ICON = 9
GAP_PILL_ICON = 6

# --- §3 Metrics: окно ------------------------------------------------------------

WINDOW_MIN_WIDTH = 1280
WINDOW_MIN_HEIGHT = 760

#: Ширины диалогов — часть спеки компонента «диалог» (наряд 0010 §8.5).
DIALOG_NARROW = 560
DIALOG_MEDIUM = 720
DIALOG_WIDE = 980
DIALOG_FULL = 1180
DIALOG_HEIGHT_SHORT = 320
DIALOG_HEIGHT_MEDIUM = 620
DIALOG_HEIGHT_TALL = 820

#: Порог, ниже которого строка отбора в `picker` только мешает (решение В-6).
PICKER_FILTER_THRESHOLD = 12

#: Высота вложенных таблиц в диалогах: находки в карточке, исследования в форме.
INLINE_TABLE_HEIGHT = 150
INLINE_TABLE_HEIGHT_SHORT = 130

#: Текстовая область на две-три строки: вложения, комментарий к находке.
#: Отдельно от высот таблиц: это поле ввода, а не список, и растить его до
#: таблицы значит отнимать вертикаль у того, ради чего форма открыта.
TEXT_AREA_HEIGHT = 70

#: Баллон на чертеже — общий для редактора группы и привязки.
#:
#: Состояние привязки красится **шкалой канона**, а не своей палитрой: связано —
#: зелёный исхода «одобрено», нет у детали — нейтральный серый, не решено —
#: светлая заливка. `(заливка, обводка, подпись внутри)`.
BALLOON_RADIUS = 16
BALLOON_MARGIN = 12
BALLOON_STROKE = 2
BALLOON_STROKE_SELECTED = 3
BALLOON_CAPTION_WIDTH = 120
BALLOON_CAPTION_HEIGHT = 18
BALLOON_STATES = {
    "neutral": (N_50, N_500, N_900),
    "linked": (DECISION_COLOURS["approved"][2], DECISION_COLOURS["approved"][1], WHITE),
    "absent": (N_300, N_600, WHITE),
}

#: Заглушка на месте чертежа: группа без чертежа обязана работать.
DRAWING_PLACEHOLDER = N_50
DRAWING_PLACEHOLDER_BORDER = N_300
DRAWING_PLACEHOLDER_TEXT = N_400

#: Пустое состояние (§8): иконка 34, заголовок 14/650, текст 12.
EMPTY_ICON_SIZE = 34
SIZE_EMPTY_TITLE = 14.0
SIZE_EMPTY_BODY = 12.0
WEIGHT_EMPTY_TITLE = 650
