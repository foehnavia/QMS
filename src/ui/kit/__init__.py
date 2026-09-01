"""`kit` — дизайн-система MIS-QMS в коде. Канон — `docs/design/design-system.md`.

**Единственный источник чисел оформления.** Ни один экран не содержит
шестнадцатеричного цвета, кегля, отступа, радиуса или высоты: всё берётся
отсюда. Без этого правила дизайн-система расходится по экранам копиями на
первом же спринте — ровно так, как разошёлся язык интерфейса до наряда 0007.
Держит гард `tests/test_ui_kit.py`.

Состав (канон §10):

* `tokens` — значения §1–§3 плоскими константами;
* `theme` — стиль, шрифт и явная светлая палитра, применяются один раз;
* `direction` — направление и выравнивание: делегат, изоляты, поля;
* `widgets` — таблица, форма, кнопки, подсказка, пустое состояние, диалог;
* `pills` — бейдж состояния решения;
* `ribbon` — лента навигации;
* `picker` — модальный выбор со строкой отбора.
"""

from . import tokens
from .focus import FocusHalo, FocusHaloController
from .direction import (
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
from .picker import PickerDialog, pick
from .pills import (
    DECISION_ROLE,
    DecisionPillDelegate,
    decision_badge,
    paint_badge,
)
from .ribbon import NavigationRibbon
from .theme import ROLE, apply_theme, font_family, palette, stylesheet
from .widgets import (
    Choice,
    boxed,
    button_row,
    column,
    danger,
    data_table,
    dialog_buttons,
    dialog_layout,
    dress_table,
    empty_state,
    error_box,
    form,
    hint,
    inline_table_height,
    primary,
    screen_layout,
    secondary,
    section_caption,
    section_header,
    set_empty_reason,
    set_section_caption,
    show_error,
    slice_tabs,
    split_row,
    status_label,
    stretching_form,
    subtitle,
    title,
)

__all__ = [
    "Choice",
    "DECISION_ROLE",
    "DirectionalDelegate",
    "DecisionPillDelegate",
    "LTR",
    "NavigationRibbon",
    "PickerDialog",
    "ROLE",
    "RTL",
    "apply_direction",
    "apply_rtl",
    "apply_theme",
    "base_direction",
    "bind_direction",
    "boxed",
    "button_row",
    "column",
    "danger",
    "data_table",
    "decision_badge",
    "dialog_buttons",
    "dialog_layout",
    "directional",
    "dress_table",
    "empty_state",
    "error_box",
    "FocusHalo",
    "FocusHaloController",
    "first_strong",
    "font_family",
    "form",
    "hint",
    "inline_table_height",
    "is_rtl",
    "iso",
    "joined",
    "numeric_field",
    "paint_badge",
    "palette",
    "pick",
    "primary",
    "screen_layout",
    "secondary",
    "section_caption",
    "section_header",
    "set_empty_reason",
    "set_section_caption",
    "show_error",
    "slice_tabs",
    "split_row",
    "status_label",
    "stretching_form",
    "strip_iso",
    "stylesheet",
    "subtitle",
    "title",
    "tokens",
]
