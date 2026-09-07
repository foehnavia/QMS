"""Раздел «Отклонения»: список записей, раскрытие строки и четыре действия.

Решение вынесено в **отдельное действие** (кнопка «Decision…»), а не в форму
регистрации: порядок канона — регистрация шаг 3, решение шаг 8, после изучения
прецедентов. В S5 то же действие переехало в карточку отклонения без переделки —
`DecisionDialog` ничего про этот раздел не знает.

**QMS-018, наряд 0028: строка перестала быть счётчиком.** Она показывает сами
находки пилюлями и раскрывается в панель со своей шапкой и своей сеткой. Отсюда
три вещи, которых нет больше нигде в приложении:

* **строка плавает по высоте** — 40 / 66 / 82 (`design-system.md` §3, rev 1.7);
* **под строкой живёт служебная строка** на всю ширину: она не выбирается, не
  ловится стрелками и своих действий не имеет — единица действия остаётся
  отклонением (решение 13 реестра);
* **ширины объявлены в пикселях**, а не знакоместах: сетка нарисована в канве
  (`docs/design/canvas/MIS-QMS Deviations List.dc.html`), и выводить её заново
  через среднюю ширину знака значило бы разойтись с проверенной суммой.

Виджет при этом **не** стал деревом. У уровней разные наборы колонок, и
`QTreeView` заставил бы их жить в одной сетке — собирается только ценой пустых
ячеек (решение 13 реестра).

Механик эталонного макета — поиска, срезов, чипов фильтров, выбора колонок,
экспорта, кнопки `Find identical` — здесь по-прежнему нет: они остаются частью 2
`Q-14`, после импорта S6.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.models import Deviation
from db.session import session_scope
from domain.deviations import delete_deviation, list_deviations
from domain.findings import (
    findings_for_deviations,
    inspections_of_deviation,
    research_label,
)

from . import kit
from .card_dialog import CardDialog
from .common import (
    decision_dev_label,
    decision_insp_label,
    dimension_sort_key,
    iso,
    joined,
    signed_label,
    strip_iso,
)
from .decision_dialog import DecisionDialog
from .deviation_dialog import DeviationDialog
from .kit import tokens
from .kit.chips import (
    CHIPS_ROLE,
    CHIPS_SHOWN,
    EXPANDED_ROLE,
    Chip,
    ExpanderDelegate,
    FindingChipsDelegate,
    chips_text,
)
from .kit.pills import DECISION_ROLE, DecisionPillDelegate

#: Колонка раскрытия — своя, 23 px, всегда слева: шасси LTR (`CLAUDE.md` §9).
#: Подписи у неё нет — заголовок над стрелкой называл бы механику, а не данные.
EXPANDER = ""

COLUMNS = (
    EXPANDER,
    "Number",
    "Item",
    "Revision",
    "WO",
    "Date",
    "Dev. qty",
    "Findings",
    "Decision",
    "Explanation",
)

#: Полная сетка уровня отклонения — **пиксели канвы**, не знакоместа.
#: `Revision` в канве нет (колонка появилась нарядом `0025`), поэтому её ширина
#: берётся по заголовку — единственная в этой сетке, которую считает шрифт.
FULL_WIDTHS = {
    EXPANDER: 23,
    "Number": 200,
    "Item": 120,
    "WO": 92,
    "Date": 90,
    "Dev. qty": 80,
    "Findings": 280,
    "Decision": 180,
    "Explanation": 410,
}

#: Минимум `Explanation`: она сжимается, но не уходит — обоснование это главный
#: текст прецедента (наряд 0011 §4).
EXPLANATION_MIN = 367

#: Доля окна, которой таблица не превышает (§1 наряда): 1728 при 1920, 1152 при 1280.
TABLE_SHARE = 0.9

#: Порядок ухода при сжатии (§7 наряда), **одна** версия и ровно эта:
#: зона запаса → короткая дата → `Findings` → `Revision` → `Explanation` к минимуму.
#: `Findings` уходит раньше `Revision` потому, что на этой ширине находки
#: показывает раскрытие строками — сводка пилюлями становится лишней, а не
#: потерянной.
SHRINK_ORDER = ("Findings", "Revision")

#: Сетка панели находок — тоже пиксели канвы. `Find identical` (160 px) в наряд
#: не входит, и её ширина уходит в зону запаса (решение 14 реестра).
PANEL_INDENT = ""
PANEL_COLUMNS = (
    PANEL_INDENT,
    "Dim.",
    "Canon",
    "Sign · value",
    "Zone",
    "Deviation type",
    "Research",
    "Inspections",
)
PANEL_WIDTHS = {
    PANEL_INDENT: 30,
    "Dim.": 72,
    "Canon": 70,
    "Sign · value": 92,
    "Zone": 196,
    "Deviation type": 176,
    "Research": 168,
    "Inspections": 340,
}

#: Сколько исследований видно в ячейке; остальные — строкой `+N inspections`.
INSPECTIONS_SHOWN = 2

#: Колонки, которым направление задаётся не по содержимому, а принудительно LTR
#: (наряд 0007 §4а, канон §6): идентификаторы, наряд, дата, количество, исход.
#: `Item` и `Explanation` сюда не входят — там направление решает содержимое.
NUMERIC_COLUMNS = (1, 3, 4, 5, 6, 8)

#: Вправо — только `Dev. qty`: её и сравнивают по величине вниз по столбцу
#: (`CLAUDE.md` §9). Канва рисует её по центру — расхождение вынесено в отчёт.
MAGNITUDE_COLUMNS = (6,)

EXPANDER_COLUMN = COLUMNS.index(EXPANDER)
FINDINGS_COLUMN = COLUMNS.index("Findings")
DECISION_COLUMN = COLUMNS.index("Decision")
EXPLANATION_COLUMN = COLUMNS.index("Explanation")

#: Идентификатор отклонения — в ячейке номера, как и до наряда.
DEVIATION_ROLE = Qt.ItemDataRole.UserRole

NO_INSPECTIONS = "No inspections"

EMPTY_TITLE = "No deviations registered yet"
EMPTY_BODY = (
    "Registration is step 3 of the process: an item, a WO and at least one "
    "finding. Precedents start working from the first decided deviation."
)


def table_limit(window_width: int) -> int:
    """Ширина, которой таблица не превышает: 90 % окна (§1 наряда)."""
    return int(window_width * TABLE_SHARE)


def grid_widths(window_width: int, *, revision_width: int) -> dict[str, int]:
    """Сетка уровня отклонения при данной ширине окна — **одна** версия сжатия.

    Сторожит правило `docs/worklog/0028-deviations-list-expansion.md` §1:
    «Сумма при 1280: `23 + 200 + 120 + 92 + 90 + 80 + 180 + 367 = 1152`. Ровно
    90 % окна» — и §7, порядок ухода. Числа приходят из таблицы `grid`
    эталонной канвы; здесь только порядок, в котором они снимаются.

    Ширина `Revision` передаётся, а не берётся из таблицы, ровно потому, что
    она единственная считается шрифтом («по заголовку»): при 1280 колонка
    уходит, и на сумму 1152 её значение не влияет никак — это и есть причина,
    по которой сумма проверяема без шрифта.
    """
    widths = dict(FULL_WIDTHS)
    widths["Revision"] = revision_width
    limit = table_limit(window_width)

    if sum(widths.values()) <= limit:
        return widths
    # (1) зона запаса исчезла сама — она гибкая; (2) дата уходит в короткий
    # формат, что ширины не меняет; (3) и (4) — снятие колонок; (5) сжатие
    # обоснования до минимума. Сжатие ставим последним: колонка, которую можно
    # сузить, дешевле колонки, которую придётся убрать.
    for name in SHRINK_ORDER:
        widths.pop(name, None)
        if sum(widths.values()) <= limit:
            return widths
    widths["Explanation"] = EXPLANATION_MIN
    return widths


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

    Короткий вывод сюда не попадает намеренно (§4.2 наряда): 340 px это около
    45 знаков, а тип и позиция съедают их почти целиком. Вывод целиком уходит в
    подсказку — приём не новый, так уже сделано с обоснованием решения.
    """
    if not rows:
        return NO_INSPECTIONS
    shown = [
        strip_iso(joined(row.type_name, decision_insp_label(row.position)))
        for row in rows[:INSPECTIONS_SHOWN]
    ]
    hidden = len(rows) - len(shown)
    if hidden > 0:
        shown.append(f"+{hidden} inspection" + ("" if hidden == 1 else "s"))
    return "\n".join(shown)


def inspections_tooltip(rows) -> str:
    """Полный вывод каждого исследования — **без обрезки** (§4.2 наряда)."""
    lines = []
    for row in rows:
        head = strip_iso(joined(row.type_name, decision_insp_label(row.position)))
        lines.append(f"{head}\n{row.conclusion}" if row.conclusion else head)
    return "\n\n".join(lines)


class FindingsPanel(QTableWidget):
    """Панель находок под раскрытой строкой — своя шапка, своя сетка.

    Это **не** продолжение таблицы над ней: у уровней разные колонки, и панель
    живёт своей сеткой (решение 13 реестра). Ни выбора, ни фокуса она не берёт —
    единица действия остаётся отклонением, и клик внутри панели не меняет
    выбранное отклонение просто потому, что панели нечего выбирать.
    """

    def __init__(self, findings, inspections, parent: QWidget | None = None) -> None:
        super().__init__(0, len(PANEL_COLUMNS), parent)
        self.setHorizontalHeaderLabels(PANEL_COLUMNS)
        self.setObjectName("findingsPanel")

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
                research_label([item.position for item in found]),
                inspections_text(found),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == PANEL_COLUMNS.index("Inspections") and found:
                    cell.setToolTip(inspections_tooltip(found))
                self.setItem(index, column, cell)
            self.setRowHeight(index, finding_row_height(len(found)))

        self.setFixedHeight(panel_height([len(inspections.get(r.finding_id, [])) for r in ordered]))

    def sizeHint(self):  # noqa: N802 — имя от Qt
        size = super().sizeHint()
        size.setHeight(self.height())
        return size


#: Направление колонок панели: номер размера, канон и величина — принудительно
#: LTR. `Zone` и `Deviation type` берут направление по содержимому: значения
#: справочников бывают ивритскими (`CLAUDE.md` §9).
PANEL_NUMERIC_COLUMNS = (1, 2, 3)

#: Вправо — только «знак · величина»: её сравнивают по величине вниз по столбцу.
PANEL_MAGNITUDE_COLUMNS = (3,)


class DeviationView(QWidget):
    """Список отклонений — вход в регистрацию, правку, решение и удаление."""

    statusChanged = Signal(str)

    #: Счётчик раздела для ленты. Справочники его не имеют намеренно: их шесть
    #: списков, и одно число рядом с разделом ни на что не отвечало бы.
    countChanged = Signal(int)

    #: Что сейчас выбрано — это и показывает подвал окна (макет S1…S6).
    selectionChanged = Signal(str)

    def __init__(self, engine: Engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._summary = ""
        self._rows_shown = 0
        #: Набор раскрытых отклонений. **Переживает перечитывание списка**
        #: (§3 наряда): после правки, решения или регистрации раскрытые
        #: остаются раскрытыми — иначе сравнение двух записей рвалось бы на
        #: каждом действии, а ради него раскрытие и сделано множественным.
        self._expanded: set[int] = set()
        #: Строка таблицы → идентификатор отклонения, которому она принадлежит.
        #: Служебная строка панели принадлежит своему отклонению, но сама
        #: выбрана быть не может.
        self._row_owner: dict[int, int] = {}

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
            widths=tuple(_declared_width(name) for name in COLUMNS),
        )
        # Двойной клик ведёт в карточку, а не в правку: карточка — рабочий
        # экран отклонения, правка из неё в одном нажатии (решение Cowork 1).
        self.table.doubleClicked.connect(self.open_card)
        self.table.cellClicked.connect(self._on_cell_clicked)
        # Исход рисуется пилюлей, находки — пилюлями находок; обе колонки
        # английские и всегда LTR, спорить им с направлением не о чем.
        self.table.setItemDelegateForColumn(DECISION_COLUMN, DecisionPillDelegate(self.table))
        self.table.setItemDelegateForColumn(
            FINDINGS_COLUMN, FindingChipsDelegate(self.table)
        )
        # Стрелка раскрытия тоже рисуется, а не пишется текстом: колонка 23 px,
        # а лист стиля даёт ячейке `padding: 0 10px` — на подпись остаётся 3 px,
        # и текстовая стрелка исчезает совсем (замер на нативной платформе).
        self.table.setItemDelegateForColumn(
            EXPANDER_COLUMN, ExpanderDelegate(self.table)
        )

        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)

        # Одно основное действие на экран (канон §4): регистрация. Всё, что
        # действует на выбранную строку, — вторичное.
        self.add_button = kit.primary("New deviation")
        self.card_button = kit.secondary("Card…")
        self.open_button = kit.secondary("Open…")
        self.decision_button = kit.secondary("Decision…")
        self.delete_button = kit.danger("Delete")
        self.add_button.clicked.connect(self.add_deviation)
        self.card_button.clicked.connect(self.open_card)
        self.open_button.clicked.connect(self.open_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.delete_button.clicked.connect(self.delete_deviation)

        layout = kit.screen_layout(self)
        self.header = kit.section_header(
            "Deviations",
            "Production non-conformances — registration, decision, precedents",
        )
        layout.addWidget(self.header)
        layout.addLayout(
            kit.button_row(
                self.add_button,
                self.card_button,
                self.open_button,
                self.decision_button,
                self.delete_button,
            )
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)

        self.table.itemSelectionChanged.connect(self._announce_selection)
        self.reload()

    # --- сетка ------------------------------------------------------------------

    def apply_grid(self, window_width: int | None = None) -> None:
        """Раздать колонкам ширину по сетке и снять то, что на этой ширине уходит.

        Ширина берётся у окна, а не у таблицы: правило §1 наряда сформулировано
        от **окна** («90 % окна»), и таблица, уже сжатая прошлым проходом, дала
        бы каждый раз новый ответ.
        """
        width = window_width if window_width is not None else self.window().width()
        widths = grid_widths(width, revision_width=self._revision_width())
        header = self.table.horizontalHeader()
        # Qt держит собственный минимум секции (на этой платформе 34 px) и молча
        # расширяет до него всё, что уже. Колонка раскрытия объявлена в 23 px, и
        # без этой строки сетка расходилась бы с канвой на 11 px — при том что
        # объявленная сумма сходилась бы, а нарисованная нет. Замечено замером на
        # нативной платформе, тестом не ловится (`CLAUDE.md` §9а.8).
        header.setMinimumSectionSize(min(FULL_WIDTHS.values()))
        for index, name in enumerate(COLUMNS):
            if name in widths:
                self.table.setColumnHidden(index, False)
                self.table.setColumnWidth(index, widths[name])
            else:
                self.table.setColumnHidden(index, True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._stretch_panels(sum(widths.values()))

    def _stretch_panels(self, content_width: int) -> None:
        """Растянуть панели на всю ширину служебной строки.

        `setCellWidget` кладёт виджет в прямоугольник ячейки, и объединение
        (`setSpan`) он к моменту вставки ещё не учитывает: панель оставалась
        шириной первой колонки, а её собственная шапка — шириной в две подписи.
        На снимке это видно сразу, а тест на состав колонок панели был зелёным —
        колонки-то объявлены (`CLAUDE.md` §9а.8, «сверяй то, чем рисуют»).
        """
        for row in range(self.table.rowCount()):
            panel = self.panel_at(row)
            if panel is not None:
                panel.setFixedWidth(max(content_width, panel.minimumWidth()))
                self.table.setRowHeight(row, panel.height())

    def _revision_width(self) -> int:
        """`Revision` — единственная колонка сетки, которую считает шрифт.

        В канве её нет: колонка появилась нарядом `0025`, уже после того, как
        сетка была нарисована. Правило §1 наряда — «по заголовку», то есть
        ровно `kit.FIT_LABEL`.
        """
        from .kit.widgets import column_width  # noqa: PLC0415 — иначе круговой импорт

        return column_width(self.table, kit.FIT_LABEL, "Revision")

    # --- загрузка ---------------------------------------------------------------

    def reload(self) -> None:
        """Перечитать список. **Два** пакетных запроса, независимо от числа строк.

        Запрет §5 наряда: ни одного запроса на строку и ни одного на находку.
        Исследования сюда не читаются вовсе — они приходят ленивым запросом на
        раскрытие, и свёрнутой строке от них нужен один признак, «есть или нет»,
        который уже приехал счётчиком в `FindingRow.inspections`.
        """
        scroll = self.table.verticalScrollBar().value()
        selected = self._selected_id()

        with session_scope(self._engine) as session:
            rows = list_deviations(session)                                   # запрос 1
            by_deviation = findings_for_deviations(                           # запрос 2
                session, [row.deviation_id for row in rows]
            )
            panels = {
                deviation_id: inspections_of_deviation(session, deviation_id)
                for deviation_id in self._expanded
                if any(row.deviation_id == deviation_id for row in rows)
            }

        self.table.setRowCount(0)
        self._row_owner = {}
        for row in rows:
            findings = by_deviation.get(row.deviation_id, [])
            index = self.table.rowCount()
            self.table.insertRow(index)
            self._fill_deviation(index, row, findings)
            self._row_owner[index] = row.deviation_id
            if row.deviation_id in self._expanded:
                self._insert_panel(row.deviation_id, findings, panels.get(row.deviation_id, {}))

        # Пустая таблица без объяснения — то, как оператор заключает «записей
        # не было» из экрана, который просто ничего не показал (канон §8).
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        self.apply_grid()

        self._announce(rows, by_deviation)
        self._restore_selection(selected)
        self.table.verticalScrollBar().setValue(scroll)

    def _fill_deviation(self, index: int, row, findings) -> None:
        chips = [
            Chip(
                dimension=f"Dim. {finding.local_number}",
                value=strip_iso(signed_label(finding.direction, finding.value)),
                kind=finding.deviation_type or "",
                researched=bool(finding.inspections),
            )
            for finding in sorted(findings, key=lambda f: dimension_sort_key(f.local_number))
        ]
        values = (
            # Пусто: стрелку рисует делегат по роли, а подпись, которой никто не
            # рисует, врала бы и тесту, и замеру ширин.
            "",
            iso(row.dev_number),
            iso(row.item_number),
            # Номер детали без ревизии — дефект: он не говорит, по какому
            # чертежу читать номера размеров (наряд 0025 §6).
            iso(row.revision),
            iso(row.wo),
            iso(self._date_text(row.date)),
            iso(str(row.quantity)),
            chips_text(chips),
            decision_dev_label(row.decision_dev, short=True),
            _one_line(row.explanation),
        )
        for column, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if column == COLUMNS.index("Number"):
                cell.setData(DEVIATION_ROLE, row.deviation_id)
            if column == EXPANDER_COLUMN:
                # Состояние — **кодом** рядом с подписью: стрелку рисует делегат
                # по нему, а не разбором символа в тексте (тот же приём, что у
                # пилюли исхода).
                cell.setData(EXPANDED_ROLE, row.deviation_id in self._expanded)
            if column == FINDINGS_COLUMN:
                # Состав находок — рядом с подписью: пилюли рисует он, а не
                # разбор текста ячейки (тот же приём, что у пилюли исхода).
                cell.setData(CHIPS_ROLE, chips)
                if len(chips) > CHIPS_SHOWN:
                    cell.setToolTip("\n".join(chip.text() for chip in chips))
            if column == DECISION_COLUMN:
                cell.setData(DECISION_ROLE, row.decision_dev)
            if column == EXPLANATION_COLUMN and row.explanation:
                # Обоснование в строке урезано, целиком — в подсказке: это
                # главный текст прецедента, терять его нельзя.
                cell.setToolTip(row.explanation)
            self.table.setItem(index, column, cell)
        self.table.setRowHeight(index, kit.chips.row_height(len(chips)))

    def _insert_panel(self, deviation_id: int, findings, inspections) -> None:
        """Служебная строка на всю ширину с панелью находок (§3 наряда).

        Строка **не выбирается и не ловится стрелками**: у её ячейки сняты все
        флаги, а Qt пропускает такие при навигации клавиатурой. Виджет внутри
        фокуса тоже не берёт, поэтому клик по панели не уводит выбор с
        отклонения — единица действия остаётся отклонением.
        """
        index = self.table.rowCount()
        self.table.insertRow(index)
        holder = QTableWidgetItem()
        holder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.setItem(index, 0, holder)
        self.table.setSpan(index, 0, 1, len(COLUMNS))
        panel = FindingsPanel(findings, inspections, self.table)
        self.table.setCellWidget(index, 0, panel)
        self.table.setRowHeight(index, panel.height())
        self._row_owner[index] = deviation_id

    def _date_text(self, value) -> str:
        """Короткий формат при сжатии — шаг (2) порядка §7 наряда."""
        compact = "Findings" not in grid_widths(
            self.window().width(), revision_width=self._revision_width()
        )
        return f"{value:%d.%m.%y}" if compact else f"{value:%d.%m.%Y}"

    def _announce(self, rows, by_deviation) -> None:
        """Подвал говорит **двумя** числами — отклонения и находки (§6 наряда).

        Счётчики считают отклонения, а не находки: экран, показывающий «12» там,
        где отклонений семь, а находок двенадцать, обманывает. `N undecided`
        оставлен третьим — он был на экране до наряда и сторожится тестом.
        """
        findings = sum(len(by_deviation.get(row.deviation_id, [])) for row in rows)
        undecided = sum(1 for row in rows if row.decision_dev is None)
        self._summary = strip_iso(
            joined(
                f"{len(rows)} deviations / {findings} findings",
                f"{undecided} undecided" if undecided else "",
            )
        )
        kit.set_section_caption(self.header, self._summary)
        self.statusChanged.emit(self._summary)
        self._rows_shown = len(rows)
        self.countChanged.emit(self._rows_shown)

    # --- раскрытие ---------------------------------------------------------------

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == EXPANDER_COLUMN:
            self.toggle_expansion(row)

    def toggle_expansion(self, row: int) -> None:
        """Раскрыть или свернуть строку. Раскрытых может быть сколько угодно.

        Решение 6 реестра: гармошка (одно раскрытие за раз) делает невозможным
        то, ради чего раскрытие и заведено, — сравнение двух отклонений по одной
        детали между собой.
        """
        deviation_id = self._deviation_at(row)
        if deviation_id is None:
            return
        if deviation_id in self._expanded:
            self._expanded.discard(deviation_id)
        else:
            self._expanded.add(deviation_id)
        self.reload()

    def expanded(self) -> set[int]:
        """Какие отклонения сейчас раскрыты — состояние экрана, не таблицы."""
        return set(self._expanded)

    def is_panel_row(self, row: int) -> bool:
        """Служебная ли это строка. Отличается наличием виджета, а не догадкой."""
        return self.table.cellWidget(row, 0) is not None

    def panel_at(self, row: int) -> FindingsPanel | None:
        widget = self.table.cellWidget(row, 0)
        return widget if isinstance(widget, FindingsPanel) else None

    # --- выбор -------------------------------------------------------------------

    def _deviation_at(self, row: int) -> int | None:
        """Отклонение, которому принадлежит строка (в том числе служебная)."""
        return self._row_owner.get(row)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or self.is_panel_row(row):
            return None
        cell = self.table.item(row, COLUMNS.index("Number"))
        return None if cell is None else cell.data(DEVIATION_ROLE)

    def _restore_selection(self, deviation_id: int | None) -> None:
        """Вернуть выбор на ту же запись: раскрытие сдвигает номера строк."""
        if deviation_id is None:
            return
        for row, owner in self._row_owner.items():
            if owner == deviation_id and not self.is_panel_row(row):
                self.table.selectRow(row)
                return

    def selection_text(self) -> str:
        """Подпись выбранной строки для подвала; пусто — «ничего не выбрано»."""
        row = self.table.currentRow()
        if row < 0 or self.is_panel_row(row):
            return ""
        return f"Selected {strip_iso(self.table.item(row, COLUMNS.index('Number')).text())}"

    def _announce_selection(self) -> None:
        self.selectionChanged.emit(self.selection_text())

    def row_count(self) -> int:
        """Сколько отклонений в списке — то же число, что уходит в ленту."""
        return self._rows_shown

    def summary_text(self) -> str:
        """Сводка экрана — её показывает **подвал окна**, а не сам экран."""
        return self._summary

    # --- действия ---------------------------------------------------------------

    def _selected(self) -> int | None:
        deviation_id = self._selected_id()
        if deviation_id is None:
            QMessageBox.information(
                self, "Nothing selected", "Select a deviation in the list first."
            )
            return None
        return deviation_id

    def add_deviation(self) -> None:
        """Регистрация; карточка нового отклонения всплывает сама.

        Канон: «opens as soon as a deviation is entered» (`DeviationCard.md`) —
        именно тогда прецеденты и нужны. При правке существующего не открываем:
        оператор уже знает, что там.
        """
        dialog = DeviationDialog(self._engine, None, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.reload()
        if dialog.deviation_id is not None:
            CardDialog.run(self._engine, dialog.deviation_id, self)
            self.reload()

    def open_card(self) -> None:
        """Карточка выбранного отклонения — рабочий экран с прецедентами."""
        deviation_id = self._selected()
        if deviation_id is None:
            return
        CardDialog.run(self._engine, deviation_id, self)
        self.reload()

    def open_deviation(self) -> None:
        deviation_id = self._selected()
        if deviation_id is None:
            return
        DeviationDialog.run(self._engine, deviation_id, self)
        # Перечитываем всегда: исследования пишутся по действию, поэтому
        # состав находок меняется и когда форму закрыли «Отменой».
        self.reload()

    def set_decision(self) -> None:
        """Шаг 8 — отдельным действием, как требует порядок процесса."""
        deviation_id = self._selected()
        if deviation_id is None:
            return
        if DecisionDialog.run(self._engine, deviation_id, self):
            self.reload()

    def delete_deviation(self) -> None:
        deviation_id = self._selected()
        if deviation_id is None:
            return

        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, deviation_id)
            number = deviation.dev_number
            findings = len(deviation.findings)
            inspections = len(deviation.inspections)

        # Единица целостности — отклонение целиком, поэтому и удаляется целиком;
        # цену показываем до удаления, а не после.
        if (
            QMessageBox.question(
                self,
                "Delete deviation?",
                f"Delete {number}? It takes with it findings: {findings}, "
                f"inspections: {inspections}.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            with session_scope(self._engine) as session:
                delete_deviation(session, session.get(Deviation, deviation_id))
        except Exception as error:
            kit.show_error(self, error, title="Deviation not deleted")
            return
        self._expanded.discard(deviation_id)
        self.reload()

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя от Qt
        """Сетка пересчитывается при смене ширины: сжатие описано от окна."""
        super().resizeEvent(event)
        self.apply_grid()


def _declared_width(name: str):
    """Ширина колонки при сборке таблицы: пиксели канвы либо заголовок."""
    if name in FULL_WIDTHS:
        return kit.px(FULL_WIDTHS[name])
    return kit.FIT_LABEL


def _one_line(text: str | None) -> str:
    """Обоснование в одну строку — в таблице многострочный текст рвёт вёрстку."""
    return " ".join((text or "").split())
