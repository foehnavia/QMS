"""Тема приложения: стиль, шрифт и явная светлая палитра — всё из токенов.

Канон §0: приложение **не наследует системную тему**. Рабочая станция,
переключённая в тёмный режим Windows, иначе перекрашивает экраны в то, чего
никто не проектировал, а контраст и bidi-дефекты уходят в невидимое.

Собирается **из `tokens`**, а не из снимков экрана: стиль — это производная
канона, и второй копии значений здесь нет. Строковых литералов с цветом в этом
файле тоже нет — только подстановка имён токенов.

Что стилем задать нельзя (канон §9), делается кодом рядом:

* палитра `QPalette` — календарь `QDateEdit` и подсказки рисуются мимо QSS;
* направление текста — оно следует за значением, а стиль значений не видит;
* **ореол фокуса** — `outline` в QSS не поддерживается, и лист стиля объявлял
  ореол, которого на экране не было (замер наряда 0012). Рисует `focus`.

Единица кегля — **пиксель**: числа §2 канона это логические пиксели при
масштабе 100 %, и `pt` вместо `px` растил весь интерфейс на треть.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from . import tokens as t

#: Роли, которые экраны ставят виджету свойством `role` — по ним и красит стиль.
ROLE = "role"
ROLE_PRIMARY = "primary"
ROLE_SECONDARY = "secondary"
ROLE_DANGER = "danger"
ROLE_TITLE = "title"
ROLE_SUBTITLE = "subtitle"
ROLE_HINT = "hint"
ROLE_STATUS = "status"
ROLE_SECTION = "section"
ROLE_EMPTY_TITLE = "empty-title"
ROLE_EMPTY_BODY = "empty-body"
ROLE_RIBBON = "ribbon"
ROLE_RIBBON_BRAND = "ribbon-brand"
ROLE_RIBBON_STATUS = "ribbon-status"
ROLE_RIBBON_ITEM = "ribbon-item"
ROLE_RIBBON_MARK = "ribbon-mark"
ROLE_RIBBON_SEPARATOR = "ribbon-separator"


def font_family() -> str:
    """Шрифтовой стек канона §2 — подтверждён `QFontDatabase` на машине."""
    return t.FONT_FAMILY


def stylesheet() -> str:
    """Qt Style Sheet приложения, собранный из токенов.

    Один лист на приложение, а не по виджету: локальный `setStyleSheet` на
    экране — это и есть та копия значений, ради запрета которой заведён `kit`.
    """
    return f"""
/* --- base ---------------------------------------------------------------- */
QWidget {{
    background: {t.WHITE};
    color: {t.N_900};
    font-family: {t.FONT_FAMILY};
    font-size: {t.SIZE_BODY}px;
}}
QMainWindow, QDialog {{ background: {t.WHITE}; }}
/* A label never paints its own ground: on the ribbon it would be a white
   block with white text on it. The container owns the background. */
QLabel {{ background: transparent; }}
QToolTip {{
    background: {t.N_900};
    color: {t.WHITE};
    border: none;
    padding: {t.GAP_PILL_ICON}px;
}}

/* --- labels -------------------------------------------------------------- */
QLabel[{ROLE}="{ROLE_TITLE}"] {{
    font-size: {t.SIZE_TITLE}px;
    font-weight: {t.WEIGHT_TITLE};
    color: {t.N_900};
}}
QLabel[{ROLE}="{ROLE_SUBTITLE}"] {{
    font-size: {t.SIZE_SUBTITLE}px;
    color: {t.N_400};
}}
QLabel[{ROLE}="{ROLE_SECTION}"] {{
    font-size: {t.SIZE_CAPTION}px;
    font-weight: {t.WEIGHT_HEADER};
    color: {t.N_400};
}}
QLabel[{ROLE}="{ROLE_HINT}"] {{
    font-size: {t.SIZE_SUBTITLE}px;
    color: {t.N_500};
}}
QLabel[{ROLE}="{ROLE_STATUS}"] {{
    font-size: {t.SIZE_STATUS}px;
    color: {t.N_500};
}}
QLabel[{ROLE}="{ROLE_EMPTY_TITLE}"] {{
    font-size: {t.SIZE_EMPTY_TITLE}px;
    font-weight: {t.WEIGHT_EMPTY_TITLE};
    color: {t.N_900};
}}
QLabel[{ROLE}="{ROLE_EMPTY_BODY}"] {{
    font-size: {t.SIZE_EMPTY_BODY}px;
    color: {t.N_500};
}}

/* --- buttons: one primary per screen, danger drawn as an outline --------- */
QPushButton {{
    min-height: {t.BUTTON_HEIGHT}px;
    max-height: {t.BUTTON_HEIGHT}px;
    padding: 0px {t.PAD_CELL}px;
    border-radius: {t.RADIUS_CONTROL}px;
    border: {t.BORDER_WIDTH}px solid {t.N_250};
    background: {t.WHITE};
    color: {t.N_700};
}}
QPushButton:hover {{ background: {t.N_50}; }}
QPushButton:pressed {{ background: {t.N_100}; }}
QPushButton:disabled {{
    background: {t.N_50};
    border-color: {t.N_250};
    color: {t.N_450};
}}
QPushButton[{ROLE}="{ROLE_PRIMARY}"] {{
    background: {t.BLUE_600};
    border-color: {t.BLUE_600};
    color: {t.WHITE};
}}
QPushButton[{ROLE}="{ROLE_PRIMARY}"]:hover {{ background: {t.BLUE_500}; }}
QPushButton[{ROLE}="{ROLE_PRIMARY}"]:pressed {{ background: {t.BLUE_700}; }}
QPushButton[{ROLE}="{ROLE_PRIMARY}"]:disabled {{
    background: {t.N_50};
    border-color: {t.N_250};
    color: {t.N_450};
}}
QPushButton[{ROLE}="{ROLE_DANGER}"] {{
    background: {t.WHITE};
    border-color: {t.DANGER_BORDER};
    color: {t.DANGER_TEXT};
}}
QPushButton[{ROLE}="{ROLE_DANGER}"]:hover {{ background: {t.N_50}; }}

/* --- inputs: focus never shifts anything by a pixel ---------------------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {{
    background: {t.WHITE};
    border: {t.BORDER_WIDTH}px solid {t.N_250};
    border-radius: {t.RADIUS_CONTROL}px;
    padding: 0px {t.GAP_PILL_ICON}px;
    min-height: {t.INPUT_HEIGHT}px;
    color: {t.N_900};
    selection-background-color: {t.BLUE_100};
    selection-color: {t.N_900};
}}
QPlainTextEdit, QTextEdit {{ padding: {t.GAP_PILL_ICON}px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border: {t.BORDER_WIDTH}px solid {t.BLUE_600};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled {{
    background: {t.N_50};
    color: {t.N_450};
}}
/* The indicator of a styled widget is drawn by whoever was asked last.
   A bare `border: none` on `::drop-down` looked harmless and took the drawing away
   from the native style, leaving no arrow at all — measured, zero dark pixels
   in the arrow zone. Describing it back as a QSS box gives a filled square:
   Qt fills the sub-control rectangle and knows nothing of the CSS border
   triangle. So the sub-control is left undescribed on purpose, and the native
   chevron does the drawing (17 px of it, verified the same way). The rule of
   §9 is satisfied by the measurement, not by the presence of a rule. */

QComboBox QAbstractItemView {{
    background: {t.WHITE};
    border: {t.BORDER_WIDTH}px solid {t.N_200};
    selection-background-color: {t.BLUE_50};
    selection-color: {t.N_900};
}}

/* --- radio: a styled widget must style its indicator too ------------------
   Qt draws the native indicator only while the widget is unstyled; the moment
   any rule matches it, a blank circle is what the operator gets. Measured on
   the decision dialog: four outcomes and no visible marks at all. */
QRadioButton {{
    background: transparent;
    spacing: {t.GAP_PILL_ICON}px;
    color: {t.N_900};
}}
QRadioButton::indicator {{
    width: {t.INDICATOR_SIZE}px;
    height: {t.INDICATOR_SIZE}px;
    border-radius: {t.INDICATOR_SIZE // 2}px;
    border: {t.BORDER_WIDTH}px solid {t.N_250};
    background: {t.WHITE};
}}
QRadioButton::indicator:hover {{ border-color: {t.N_400}; }}
QRadioButton::indicator:checked {{
    border: {t.SELECTION_BAR_WIDTH * 2}px solid {t.BLUE_600};
    background: {t.WHITE};
}}
QRadioButton:disabled {{ color: {t.N_450}; }}
QRadioButton::indicator:disabled {{ background: {t.N_50}; border-color: {t.N_250}; }}

/* --- table: the row is the unit of selection, a cell never takes focus --- */
QTableView, QTableWidget, QListWidget {{
    background: {t.WHITE};
    border: {t.BORDER_WIDTH}px solid {t.N_200};
    border-radius: {t.RADIUS_PANEL}px;
    gridline-color: {t.N_100};
    color: {t.N_700};
    outline: none;
    selection-background-color: {t.BLUE_50};
    selection-color: {t.N_900};
}}
QTableView::item, QTableWidget::item, QListWidget::item {{
    padding: 0px {t.PAD_CELL}px;
    border: none;
}}
QTableView::item:hover, QTableWidget::item:hover, QListWidget::item:hover {{
    background: {t.N_50};
}}
QTableView::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: {t.BLUE_50};
    color: {t.N_900};
}}
QHeaderView::section {{
    background: {t.N_50};
    border: none;
    border-bottom: {t.BORDER_WIDTH}px solid {t.N_200};
    padding: 0px {t.PAD_CELL}px;
    height: {t.TABLE_HEADER_HEIGHT}px;
    font-size: {t.SIZE_HEADER}px;
    font-weight: {t.WEIGHT_HEADER};
    color: {t.N_500};
}}
QTableCornerButton::section {{
    background: {t.N_50};
    border: none;
    border-bottom: {t.BORDER_WIDTH}px solid {t.N_200};
}}

/* --- slice tabs ---------------------------------------------------------- */
QTabWidget::pane {{
    border: {t.BORDER_WIDTH}px solid {t.N_200};
    border-radius: {t.RADIUS_PANEL}px;
    top: -{t.BORDER_WIDTH}px;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: {t.SELECTION_BAR_WIDTH}px solid transparent;
    height: {t.TAB_STRIP_HEIGHT}px;
    padding: 0px {t.PAD_CELL}px;
    font-size: {t.SIZE_SUBTITLE}px;
    color: {t.N_500};
}}
QTabBar::tab:hover {{ color: {t.N_900}; }}
QTabBar::tab:selected {{
    color: {t.BLUE_600};
    border-bottom-color: {t.BLUE_600};
}}

/* --- frames, separators, bars -------------------------------------------- */
QGroupBox {{
    border: {t.BORDER_WIDTH}px solid {t.N_200};
    border-radius: {t.RADIUS_PANEL}px;
    margin-top: {t.PAD_CELL}px;
    padding-top: {t.PAD_CELL}px;
    font-size: {t.SIZE_HEADER}px;
    font-weight: {t.WEIGHT_HEADER};
    color: {t.N_500};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {t.PAD_CELL}px;
    padding: 0px {t.GAP_PILL_ICON}px;
}}
QStatusBar {{
    background: {t.N_50};
    border-top: {t.BORDER_WIDTH}px solid {t.N_200};
    min-height: {t.FOOTER_HEIGHT}px;
    color: {t.N_500};
    font-size: {t.SIZE_STATUS}px;
}}
QStatusBar::item {{ border: none; }}
QScrollBar:vertical {{
    background: {t.WHITE};
    width: {t.PAD_CELL}px;
    margin: 0px;
}}
QScrollBar:horizontal {{
    background: {t.WHITE};
    height: {t.PAD_CELL}px;
    margin: 0px;
}}
QScrollBar::handle {{
    background: {t.N_300};
    border-radius: {t.RADIUS_ROW_ACTION}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: {t.WHITE}; }}
QSplitter::handle {{ background: {t.N_200}; }}

/* --- navigation ribbon: the only dark surface ---------------------------- */
QWidget[{ROLE}="{ROLE_RIBBON}"] {{
    background: {t.RIBBON};
    border-bottom: {t.BORDER_WIDTH}px solid {t.RIBBON_BORDER};
}}
QLabel[{ROLE}="{ROLE_RIBBON_BRAND}"] {{
    color: {t.RIBBON_TEXT};
    font-size: {t.SIZE_SUBTITLE}px;
    font-weight: {t.WEIGHT_HEADER};
}}
QLabel[{ROLE}="{ROLE_RIBBON_STATUS}"] {{
    color: {t.RIBBON_MUTED};
    font-size: {t.SIZE_STATUS}px;
}}
QPushButton[{ROLE}="{ROLE_RIBBON_ITEM}"] {{
    background: transparent;
    border: none;
    border-radius: {t.RADIUS_CONTROL}px;
    min-height: {t.NAV_ITEM_HEIGHT}px;
    max-height: {t.NAV_ITEM_HEIGHT}px;
    /* Width follows content: the Windows style gives a button a minimum of
       80 px, and five sections with it do not fit the 1280 minimum window. */
    min-width: 0px;
    padding: 0px {t.PAD_NAV_ITEM}px;
    color: {t.RIBBON_MUTED};
    font-size: {t.SIZE_SUBTITLE}px;
}}
QPushButton[{ROLE}="{ROLE_RIBBON_ITEM}"]:hover {{ color: {t.RIBBON_TEXT}; }}
QPushButton[{ROLE}="{ROLE_RIBBON_ITEM}"]:checked {{
    background: {t.RIBBON_ACTIVE};
    color: {t.RIBBON_TEXT};
    font-weight: {t.WEIGHT_PILL};
}}
QPushButton[{ROLE}="{ROLE_RIBBON_ITEM}"]:disabled {{ color: {t.RIBBON_MUTED}; }}
QLabel[{ROLE}="{ROLE_RIBBON_MARK}"] {{
    background: {t.BLUE_600};
    color: {t.RIBBON_TEXT};
    border-radius: {t.RADIUS_ROW_ACTION}px;
    font-size: {t.SIZE_HEADER}px;
    font-weight: {t.WEIGHT_HEADER};
}}
QFrame[{ROLE}="{ROLE_RIBBON_SEPARATOR}"] {{
    background: {t.RIBBON_ACTIVE};
    border: none;
}}
"""


def palette() -> QPalette:
    """Явная светлая палитра — то, до чего QSS не дотягивается (канон §9).

    Календарь `QDateEdit`, подсказки и системные виджеты рисуются палитрой; без
    неё они остаются в цветах Windows, и в тёмной теме читаются белым по белому.
    """
    colours = QPalette()
    colours.setColor(QPalette.ColorRole.Window, QColor(t.WHITE))
    colours.setColor(QPalette.ColorRole.WindowText, QColor(t.N_900))
    colours.setColor(QPalette.ColorRole.Base, QColor(t.WHITE))
    colours.setColor(QPalette.ColorRole.AlternateBase, QColor(t.N_50))
    colours.setColor(QPalette.ColorRole.Text, QColor(t.N_900))
    colours.setColor(QPalette.ColorRole.Button, QColor(t.WHITE))
    colours.setColor(QPalette.ColorRole.ButtonText, QColor(t.N_700))
    colours.setColor(QPalette.ColorRole.Highlight, QColor(t.BLUE_50))
    colours.setColor(QPalette.ColorRole.HighlightedText, QColor(t.N_900))
    colours.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.N_900))
    colours.setColor(QPalette.ColorRole.ToolTipText, QColor(t.WHITE))
    colours.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.N_450))
    colours.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.N_450)
    )
    colours.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.N_450)
    )
    return colours


def application_font() -> QFont:
    """Шрифт приложения: первое семейство стека, остальные — как fallback.

    Размер — **в пикселях**, а не в пунктах. Числа канона §2 это логические
    пиксели при масштабе Windows 100 %; объявленные пунктами, они давали на
    треть более крупный текст (13 pt ≈ 17 px), и всё приложение рисовалось
    плотнее задуманного — кнопки ленты не помещались в минимум окна 1280.
    Найдено замером ширин в наряде 0012.

    `tnum` не включается намеренно: замер на машине (наряд 0011 §1) показал, что
    все семейства стека уже дают цифрам равную ширину, и фича ничего не меняет.
    """
    font = QFont()
    font.setFamilies([name.strip('"') for name in t.FONT_STACK])
    font.setPixelSize(round(t.SIZE_BODY))
    return font


def apply_theme(app: QApplication) -> QApplication:
    """Одеть приложение: шасси LTR, светлая палитра, шрифт, стиль.

    Зовётся **один раз** на запуске (`app.py`) и в снимках экрана. Виджеты своих
    листов стиля не заводят — иначе значения канона расползаются копиями.
    """
    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    app.setPalette(palette())
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    # Ореол фокуса — виджетом, а не стилем: канон §3 требует его, а `outline`
    # в QSS не рисуется (наряд 0012, замер).
    from .focus import install as install_focus_halo

    install_focus_halo(app)
    return app
