"""Карточка отклонения — рабочий экран и главный deliverable Этапа 1 (наряд 0005).

Смысл экрана один: инженер, глядя на отклонение, сразу видит, случалось ли такое
раньше, что тогда решили и как обосновали (`DeviationCard.md`, шаг 6 процесса).
Ради этого карточка открывается **сама** после регистрации нового отклонения.

Прецеденты показываются **по выбранной находке**, а не по отклонению целиком
(решение Cowork 2): отклонение с пятью размерами иначе свалило бы в одну кучу
разное, а инженер работает с конкретным размером.

Вкладки — уровни поиска (`Search.md`): «Точные (L1)» по паре «деталь + размер» и
по канонической позиции. Вкладка описательного уровня **списка не показывает**
(наряд 0022, ревизия ратификации S5): описательный прецедент — результат поиска,
который инженер собирает под конкретный случай из нескольких параметров, а не
строка, которую система выводит сама по одному признаку. Вкладка остаётся с
объяснением — пустая вкладка без слов читалась бы как «прецедентов нет».

Своего диалога решения здесь нет: `DecisionDialog` переехал из списка **как
есть** — S4 сделал его самостоятельным ровно для этого.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from db.models import (
    Characteristic,
    Deviation,
    Finding,
    Inspection,
    Item,
    RefDeviationType,
    RefZone,
)
from db.session import session_scope
from domain.findings import inspection_counts, update_finding
from domain.precedents import (
    CANON_NEW,
    CANON_UNBOUND,
    PrecedentRow,
    canon_labels,
    precedents_same_dimension,
    precedents_same_position,
)

from . import kit
from .common import (
    UNBOUND_MARK,
    decision_dev_label,
    outcome_label,
    dimension_sort_key,
    iso,
    joined,
    mark_other_revision,
    mark_unbound,
    signed_label,
    unbound_size_text,
)
from .kit import tokens
from .kit.pills import DECISION_ROLE, DecisionPillDelegate
from .decision_dialog import DecisionDialog
from .deviation_dialog import (
    FINDING_COLUMNS,
    FINDING_MAGNITUDE_COLUMNS,
    FINDING_NUMERIC_COLUMNS,
    FINDING_WIDTHS,
    DeviationDialog,
)
from .finding_dialog import FindingDialog, FindingRow
from .inspection_dialog import InspectionDialog
from .item_dialog import open_mapping
from .pickers import choose_cg_for_item

#: Исследования выбранной находки — тип · позиция · короткий вывод (наряд 0027 §3).
#:
#: Колонки «находка» здесь нет намеренно: таблица показывает исследования **одной**
#: находки — той, что выбрана выше, — и повторять её номер в каждой строке значило
#: бы объяснять то, что уже сказано выбором.
INSPECTION_COLUMNS = ("Type", "Conclusion")

#: Ширины по правилу §8.3 наряда 0020: `Type` — рекорд справочника
#: (`Implantation torque test`), `Conclusion` — предел с обрезкой, остальное в
#: подсказке. Колонка `Result` снята вместе с позицией (QMS-025); её знакоместа
#: **не отдаются** выводу — вывод и так на своём пределе с обрезкой, а лишняя
#: ширина у него отняла бы её у таблицы находок, где появилась колонка исхода.
INSPECTION_WIDTHS = (30, 46)

#: Индекс колонки вывода — адресуем по имени, а не по числу в теле цикла (§9а.9).
INSPECTION_CONCLUSION_COLUMN = INSPECTION_COLUMNS.index("Conclusion")

PRECEDENT_COLUMNS = (
    "Deviation",
    "Date",
    "Item",
    "Revision",
    "WO",
    "Characteristic",
    "Sign · value",
    "Decision",
    "Explanation",
    "Insp.",
)

#: Числовые колонки прецедента: дата, знак с величиной, счётчик исследований.
#: Ширины поимённо (§7.3 наряда 0020): max(заголовок, самое длинное реальное
#: значение) × 1.25; знакоместо — по самому широкому знаку шрифта канона.
#: `Characteristic` — составная ячейка `19 · C1 SP375 Int. Con. Zone`:
#: у неё предел с обрезкой, а не расчёт по рекорду.
#: `kit.FIT_LABEL` — счётчик (§8.3, класс 2): ширина равна заголовку,
#: запаса нет — не растёт ни содержимое, ни подпись.
#: `Revision` — обозначение как выпущено, обычно один-два знака; класс 2
#: (§8.3 наряда 0020): ширина по заголовку, запаса нет.
PRECEDENT_WIDTHS = (
    19,
    16,
    15,
    kit.FIT_LABEL,
    15,
    30,
    14,
    kit.pill(14),
    40,
    kit.FIT_LABEL,
)

#: Дата, «знак · величина», счётчик. Ревизия сюда **не входит**: обозначение —
#: идентификатор, а не величина, сравнивать по нему нечего, и левый край держит
#: его у подписи колонки (`CLAUDE.md` §9).
PRECEDENT_NUMERIC_COLUMNS = (1, 6, 9)

#: Вправо — только «знак · величина»: её и сравнивают вниз по столбцу.
PRECEDENT_MAGNITUDE_COLUMNS = (6,)

#: Колонка исхода — рисуется пилюлей (канон §1).
PRECEDENT_DECISION_COLUMN = 7

#: Колонка ревизии и колонка размера — на них садятся обе пометки `Search.md`.
PRECEDENT_REVISION_COLUMN = 3
PRECEDENT_SIZE_COLUMN = 5

#: Знак у не-канонного размера. Определение и смысл — в `ui.common`: одно значение
#: на всех экранах требует одного определения, иначе второй экран заведёт второй
#: смысл (`Search.md` v1.04). Здесь имя оставлено ради прежних точек ввоза.

UNBOUND_TITLE = "Search by canonical position is unavailable"
UNBOUND_HINT = (
    "This characteristic is not bound to the canon. Binding is exactly what "
    "finds the same design node on other items."
)

#: Заглушка вкладки описательного уровня — по образцу ленты, где поиск объявлен
#: словами «Search — not built yet». Место под будущую группу фильтров остаётся
#: видимым, а обещание несуществующего исчезает.
NOT_BUILT_TITLE = "Descriptive search — not built yet"
NOT_BUILT_HINT = (
    "Descriptive precedents are found by a search the engineer sets up: several "
    "parameters at once, for one case, not saved. A single parameter would return "
    "half the database."
)

NO_SELECTION_TITLE = "No finding selected"
NO_SELECTION_HINT = (
    "Pick a finding in the table above — precedents are searched by its characteristic."
)

#: Та же причина одной фразой — для компактных секций вкладки «точные».
NO_SELECTION_SHORT = "pick a finding above; precedents are searched by its characteristic"

#: Подписи вкладок. Счётчик на вкладке отвечает «сколько там есть» до того,
#: как оператор туда заглянул (макет S14), — иначе пустую вкладку он открывает,
#: чтобы это выяснить.
EXACT_TAB = "Exact precedents (L1)"
#: Счётчика у второй вкладки нет: считать нечего, пока запрос не собран человеком.
DESCRIPTIVE_TAB = "Descriptive precedents (L2)"

#: Пустая секция исследований. Две причины пустоты — «находка не выбрана» и
#: «исследований нет» — здесь **не** разводятся: обе секции стоят под таблицей
#: находок, и вторая фраза объясняет ровно то, что оператор и так видит.
#: Роль, под которой строка исследования несёт признак «файла нет».
#: Кнопку красит **код**, а не разбор текста ячейки (тот же приём, что у пилюли).
NO_PROTOCOL_ROLE = Qt.ItemDataRole.UserRole + 4

#: Почему у этой записи нечего открывать. Стоит и на строке, и на самой кнопке:
#: неактивная кнопка без объяснения читается как поломка (§4 наряда 0029).
NO_PROTOCOL_HINT = (
    "No protocol file — the drawing settles this one; the conclusion is the record."
)

NO_INSPECTIONS_TITLE = "No inspections"
NO_INSPECTIONS_HINT = (
    "an inspection is recorded only when a written, reusable analysis exists"
)

NO_PRECEDENTS_TITLE = "No precedents yet"
#: Компактная секция говорит одной фразой: читатель просматривает вкладку, а не
#: секцию, и абзац на каждую из двух пустых секций он всё равно не читает.
NO_PRECEDENTS_HINT = "only deviations that already carry a decision are listed"


class PrecedentTable(kit.DataTable):
    """Таблица прецедентов. Единица строки — **отклонение целиком** (`Search.md`)."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        columns = PRECEDENT_COLUMNS
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)
        # Одевается тем же кодом, что и всякая таблица данных: разошедшиеся
        # настройки двух таблиц — та самая болезнь, ради которой заведён `kit`.
        kit.dress_table(
            self,
            numeric_columns=PRECEDENT_NUMERIC_COLUMNS,
            magnitude_columns=PRECEDENT_MAGNITUDE_COLUMNS,
            widths=PRECEDENT_WIDTHS,
        )
        self.setItemDelegateForColumn(
            PRECEDENT_DECISION_COLUMN, DecisionPillDelegate(self)
        )

    def fill(self, rows: list[PrecedentRow], *, reference: str | None = None) -> None:
        """`reference` — ревизия, из которой смотрят: она попадает в подсказку
        пометки выпуска. Пометку ставит `mark_other_revision` — та же функция,
        что и в списке отклонений детали, чтобы один факт не выглядел на двух
        экранах по-разному."""
        # Выбор сбрасываем: строки другие, а уцелевшее выделение делало бы вид,
        # что оператор что-то выбрал в таблице, которую он ещё не смотрел.
        self.clearSelection()
        self.setCurrentCell(-1, -1)
        self.setRowCount(len(rows))
        for index, row in enumerate(rows):
            # Составная ячейка: номер размера и g-подпись — самостоятельные
            # токены, каждый в своём изоляте (наряд 0007, §4а).
            size = unbound_size_text(
                row.local_number, row.g_label, canon_bound=row.is_canon_bound
            )
            values = [
                iso(row.dev_number),
                iso(f"{row.date:%d.%m.%Y}"),
                iso(row.item_number),
                iso(row.revision),
                iso(row.wo),
                size,
                signed_label(row.direction, row.value),
                decision_dev_label(row.decision, short=True),
                _one_line(row.explanation),
                str(row.inspection_count),
            ]

            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
                if column == PRECEDENT_SIZE_COLUMN and row.g_label:
                    # Узкая колонка съедает имя группы — оно нужно, чтобы понять,
                    # по какому канону совпало; держим в подсказке.
                    cell.setToolTip(f"{row.local_number} · {row.g_label}")
                if column == PRECEDENT_SIZE_COLUMN and not row.is_canon_bound:
                    mark_unbound(cell)
                if column == PRECEDENT_REVISION_COLUMN and row.other_revision:
                    # Пометка выпуска — всегда при расхождении: совпадение через
                    # ревизию не отсеивается никогда, только помечается. Цвет здесь
                    # не ставится — он занят смыслом «нет канона» (`Search.md` v1.05).
                    mark_other_revision(cell, row.revision, reference)
                if column == PRECEDENT_DECISION_COLUMN:
                    # Код исхода рядом с подписью: пилюлю красит он. Домен
                    # отдаёт в `row.decision` именно **код** — подпись из него
                    # строит `decision_dev_label` строкой выше, и обратное
                    # преобразование здесь красило все пилюли как «нет решения».
                    cell.setData(DECISION_ROLE, row.decision)
                if column == 8:
                    # Обоснование в строке урезано, целиком — в подсказке: это
                    # главный текст прецедента, терять его нельзя.
                    cell.setToolTip(row.explanation)
                self.setItem(index, column, cell)

    def selected_deviation(self) -> int | None:
        row = self.currentRow()
        if row < 0:
            return None
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole)


class CardDialog(QDialog):
    """Карточка одного отклонения с автообзором прецедентов."""

    def __init__(
        self, engine: Engine, deviation_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = deviation_id
        self._finding_ids: list[int] = []
        # Карточка — **окно**, а не диалог фиксированного размера: она держит
        # шапку, находки и две секции прецедентов сразу, и вертикали ей может не
        # хватить на любом наперёд заданном размере. Минимум — чтобы окно не
        # сжали в нечитаемое; область прецедентов ниже прокручивается.
        self.setMinimumSize(tokens.DIALOG_WIDE, tokens.WINDOW_MIN_HEIGHT)
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_CARD)

        # --- шапка ---
        self.number = QLabel()
        self.item_label = QLabel()
        # Ревизия рядом с деталью, только чтение: менять её — через `Edit`,
        # где выбор уже есть и работает (наряд 0024). Номер детали без
        # ревизии — дефект: он не говорит, по какому чертежу читать номера.
        self.revision_label = QLabel()
        self.wo = QLabel()
        self.machine = QLabel()
        self.quantity = QLabel()
        self.date = QLabel()
        self.ncr = QLabel()
        self.attachment = QLabel()
        self.attachment.setWordWrap(True)
        self.decision = kit.decision_badge("", None)
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)

        # Поля не растягиваются на всю ширину: иначе значение уезжает от своей
        # подписи через полэкрана и липнет к подписи соседней колонки.
        head_left = kit.form()
        head_left.addRow("Deviation:", self.number)
        head_left.addRow("Item:", self.item_label)
        head_left.addRow("Revision:", self.revision_label)
        head_left.addRow("WO:", self.wo)
        head_left.addRow("Machine:", self.machine)
        head_right = kit.form()
        head_right.addRow("Quantity:", self.quantity)
        head_right.addRow("Date:", self.date)
        head_right.addRow("NCR:", self.ncr)
        head_right.addRow("Attachments:", self.attachment)

        # Каждая колонка — в своём виджете: соседние QFormLayout иначе делят
        # ширину так, что значение левой оказывается вплотную к подписи правой.
        head_columns = QHBoxLayout()
        head_columns.addWidget(kit.boxed(head_left), 1)
        head_columns.addWidget(kit.boxed(head_right), 1)

        decision_form = kit.form()
        # Пилюля не растягивается на ширину формы: её край и есть её форма.
        decision_row = QHBoxLayout()
        decision_row.addWidget(self.decision)
        decision_row.addStretch(1)
        decision_form.addRow("Decision:", kit.boxed(decision_row))
        decision_form.addRow("Explanation:", self.explanation)

        self.edit_button = kit.secondary("Edit…")
        self.decision_button = kit.primary("Decision…")
        self.close_button = kit.secondary("Close")
        self.edit_button.clicked.connect(self.edit_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.close_button.clicked.connect(self.reject)

        head_buttons = kit.button_row(self.edit_button, self.decision_button)

        header_box = QGroupBox("Deviation")
        header_layout = QVBoxLayout(header_box)
        header_layout.addLayout(head_columns)
        header_layout.addLayout(decision_form)
        header_layout.addLayout(head_buttons)

        # --- находки ---
        self.findings = kit.data_table(
            FINDING_COLUMNS,
            numeric_columns=FINDING_NUMERIC_COLUMNS,
            magnitude_columns=FINDING_MAGNITUDE_COLUMNS,
            widths=FINDING_WIDTHS,
        )
        self.findings.currentCellChanged.connect(lambda *_: self.refresh_precedents())

        # Три кнопки названы по объекту, который открывают, и стоят в порядке
        # рассуждения: сама находка → её исследование → её привязка к канону.
        # `Edit…` для находки не годится — он уже занят наверху отклонением, и
        # два `Edit…` на одном экране значили бы разное (доводка `0030`, Д-1).
        self.finding_button = kit.secondary("Finding…")
        self.inspect_button = kit.secondary("Inspection…")
        self.map_button = kit.secondary("Mapping…")
        self.finding_button.clicked.connect(self.open_finding)
        self.inspect_button.clicked.connect(self.open_inspection)
        self.map_button.clicked.connect(self.bind_canon)

        finding_buttons = kit.button_row(
            self.finding_button, self.inspect_button, self.map_button
        )

        self.findings_box = findings_box = QGroupBox(
            "Findings — pick a characteristic; precedents are searched by it"
        )
        findings_layout = QVBoxLayout(findings_box)
        findings_layout.addWidget(self.findings, 1)
        findings_layout.addLayout(finding_buttons)
        kit.inline_table_height(self.findings)
        self.findings.setMinimumHeight(kit.tokens.INLINE_TABLE_HEIGHT)

        # --- исследования выбранной находки ---
        self.inspections = kit.data_table(INSPECTION_COLUMNS, widths=INSPECTION_WIDTHS)
        self.inspections.currentCellChanged.connect(lambda *_: self._refresh_protocol_button())
        # Двойной клик открывает протокол — та же идиома, что у прецедентов ниже:
        # строка таблицы открывается двойным кликом, кнопка рядом делает то же
        # для тех, кто её ищет глазами.
        self.inspections.doubleClicked.connect(lambda *_: self.open_protocol())
        self.protocol_button = kit.secondary("Open protocol…")
        self.protocol_button.clicked.connect(self.open_protocol)

        self.inspections_empty = kit.empty_state(
            NO_INSPECTIONS_TITLE, NO_INSPECTIONS_HINT, compact=True
        )
        inspections_box = QGroupBox("Inspections of the selected characteristic")
        inspections_layout = QVBoxLayout(inspections_box)
        inspections_layout.addWidget(self.inspections, 1)
        inspections_layout.addWidget(self.inspections_empty)
        inspections_layout.addLayout(kit.button_row(self.protocol_button))
        kit.inline_table_height(self.inspections, short=True)

        # --- прецеденты ---
        self.same_dimension = PrecedentTable()
        self.same_position = PrecedentTable()
        self._active_table: PrecedentTable | None = None
        self._syncing_selection = False
        for table in (self.same_dimension, self.same_position):
            # Таблицу передаём явно: двойной клик во второй секции обязан открыть
            # строку второй секции, а не «первой, где что-то выбрано».
            table.doubleClicked.connect(
                lambda *_args, source=table: self.open_precedent(source)
            )
            table.itemSelectionChanged.connect(
                lambda source=table: self._on_table_selected(source)
            )

        self.same_dimension_title = kit.section_caption("")
        self.same_position_title = kit.section_caption("")

        # Четыре пустых состояния карточки — текстом, а не пустой таблицей
        # (канон §8, наряд 0010 §4): пустая таблица без объяснения это то, как
        # оператор заключает «прецедентов не было» из экрана, который просто
        # ничего не искал.
        self.position_hint_button = kit.secondary("Mapping…")
        self.position_hint_button.clicked.connect(self.bind_canon)
        self.position_hint_box = kit.empty_state(
            UNBOUND_TITLE, UNBOUND_HINT, self.position_hint_button
        )
        # Секции L1a и L1b — соседи внутри одной вкладки, значит компактный
        # вариант (канон §8, ревизия 1.2): выход принадлежит вкладке, не секции.
        self.dimension_empty = kit.empty_state(
            NO_PRECEDENTS_TITLE, NO_PRECEDENTS_HINT, compact=True
        )
        self.position_empty = kit.empty_state(
            NO_PRECEDENTS_TITLE, NO_PRECEDENTS_HINT, compact=True
        )
        # Таблице прецедентов есть что показать — она не сжимается до полоски;
        # вертикали не хватило — прокручивается вкладка целиком.
        for table in (self.same_dimension, self.same_position):
            table.setMinimumHeight(tokens.INLINE_TABLE_HEIGHT)

        exact = QWidget()
        exact_layout = QVBoxLayout(exact)
        exact_layout.setContentsMargins(0, 0, 0, 0)
        exact_layout.addWidget(self.same_dimension_title)
        exact_layout.addWidget(self.same_dimension, 1)
        exact_layout.addWidget(self.dimension_empty)
        exact_layout.addWidget(self.same_position_title)
        exact_layout.addWidget(self.position_hint_box)
        exact_layout.addWidget(self.same_position, 1)
        exact_layout.addWidget(self.position_empty)

        # Вкладка описательного уровня: списка нет, есть объяснение почему.
        # Вкладка целиком — одна поверхность, значит полное пустое состояние.
        self.descriptive_hint = kit.empty_state(NOT_BUILT_TITLE, NOT_BUILT_HINT)
        similar = QWidget()
        similar_layout = QVBoxLayout(similar)
        similar_layout.setContentsMargins(0, 0, 0, 0)
        similar_layout.addWidget(self.descriptive_hint)
        similar_layout.addStretch(1)

        self.tabs = kit.slice_tabs()
        self.tabs.addTab(_scrolling(exact), EXACT_TAB)
        self.tabs.addTab(_scrolling(similar), DESCRIPTIVE_TAB)

        self.open_button = kit.secondary("Open precedent…")
        self.open_button.clicked.connect(lambda: self.open_precedent())
        self.status = kit.status_label()

        footer = QHBoxLayout()
        footer.setSpacing(tokens.GAP_CONTROL)
        footer.addWidget(self.open_button)
        footer.addStretch(1)
        footer.addWidget(self.close_button)

        layout = kit.dialog_layout(self)
        layout.addWidget(header_box)
        # Вкладки прецедентов — главный deliverable карточки, и вертикаль им
        # достаётся первой. Секция исследований (QMS-018) добавилась к уже
        # полному экрану, и без этого минимума она съедала у прецедентов всё до
        # полосы прокрутки — видно на снимке, не в тесте. Минимум поднимает и
        # минимальную высоту окна: карточка изменяема по высоте (ревью 0011,
        # О-6), поэтому запрошенные `DIALOG_HEIGHT_TALL` Qt увеличит до влезающих.
        self.tabs.setMinimumHeight(tokens.INLINE_TABLE_HEIGHT)

        layout.addWidget(findings_box)
        layout.addWidget(inspections_box)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> None:
        """Открыть карточку. Возврата не имеет: карточка ничего не решает сама."""
        cls(engine, deviation_id, parent=parent).exec()

    # --- загрузка ---------------------------------------------------------------

    def reload(self) -> None:
        """Перечитать шапку и находки; выбор строки сохраняем, если можем."""
        previous = self._selected_finding_id()

        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            self.setWindowTitle(
                f"Deviation card — {deviation.dev_number} · {deviation.item.item_number}"
            )
            self.number.setText(iso(deviation.dev_number))
            self.item_label.setText(iso(deviation.item.item_number))
            self.revision_label.setText(iso(deviation.revision.designation))
            self.wo.setText(iso(deviation.wo))
            self.machine.setText(iso(deviation.machine or "—"))
            self.quantity.setText(iso(str(deviation.quantity)))
            self.date.setText(iso(f"{deviation.date:%d.%m.%Y}"))
            self.ncr.setText(iso(deviation.ncr or "—"))
            self.attachment.setText(iso(deviation.attachment or "—"))
            code = deviation.decision_dev
            # Пилюля — тот же компонент, что и в колонке списка: одно значение
            # не имеет права выглядеть на двух экранах по-разному.
            kit.paint_badge(self.decision, decision_dev_label(code), code)
            self.explanation.setText(deviation.explanation or "—")

            findings = _load_findings(session, deviation)
            counts = inspection_counts(session, findings)
            canon = canon_labels(session, [f.characteristic for f in findings])
            rows = [
                (
                    finding.finding_id,
                    finding.characteristic.local_number,
                    canon.get(finding.characteristic_id, CANON_NEW),
                    finding.direction,
                    finding.value,
                    finding.dimension_point,
                    finding.zone.name if finding.zone else "",
                    finding.deviation_type.name if finding.deviation_type else "",
                    counts.get(finding.finding_id, 0),
                    finding.outcome,
                )
                for finding in findings
            ]

        self._finding_ids = [row[0] for row in rows]
        self.findings.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                iso(row[1]),
                iso(row[2]),
                signed_label(row[3], row[4]),
                row[6],
                row[7],
                "" if row[5] is None else iso(str(row[5])),
                # Исход — перед счётчиком исследований, тем же порядком, что и в
                # форме отклонения: суждение, а исследования лишь сведения к нему.
                outcome_label(row[9]),
                str(row[8]),
            )
            for column, value in enumerate(values):
                self.findings.setItem(index, column, QTableWidgetItem(value))

        if rows:
            restored = self._finding_ids.index(previous) if previous in self._finding_ids else 0
            # Сигнал глушим: иначе выбор строки и явный вызов ниже дают две
            # перерисовки прецедентов, то есть два лишних похода в базу.
            self.findings.blockSignals(True)
            self.findings.setCurrentCell(restored, 0)
            self.findings.blockSignals(False)
        self.refresh_precedents()

    def refresh_precedents(self) -> None:
        """Перерисовать обе вкладки и таблицу исследований под выбранную находку."""
        finding_id = self._selected_finding_id()
        self._refresh_buttons(finding_id)
        self._refresh_inspections(finding_id)

        if finding_id is None:
            for table in (self.same_dimension, self.same_position):
                table.setRowCount(0)
                table.setVisible(False)
            self.same_dimension_title.setText(NO_SELECTION_TITLE)
            self.same_position_title.setText("")
            self.position_hint_box.setVisible(False)
            # Причина пустоты здесь другая — «находка не выбрана», а не
            # «прецедентов нет»; подменять одно другим значит объяснять
            # оператору не то, что он видит.
            kit.set_empty_reason(
                self.dimension_empty, NO_SELECTION_TITLE, NO_SELECTION_SHORT
            )
            self.dimension_empty.setVisible(True)
            self.position_empty.setVisible(False)
            # Заглушка описательной вкладки от выбора находки не зависит вовсе:
            # там нечего искать ни при какой выбранной строке.
            self.status.setText(NO_SELECTION_HINT)
            return

        with session_scope(self._engine) as session:
            finding = session.get(Finding, finding_id)
            characteristic = finding.characteristic
            deviation = finding.deviation
            bound = characteristic.mapping is not None
            position_label = (
                f"g{characteristic.mapping.g_position.g_index}" if bound else None
            )

            same_dimension = precedents_same_dimension(
                session, characteristic, exclude_deviation=deviation
            )
            same_position = precedents_same_position(
                session, characteristic, exclude_deviation=deviation
            )
            local_number = characteristic.local_number
            reference_revision = characteristic.revision.designation

        self.same_dimension.fill(same_dimension, reference=reference_revision)
        self.same_dimension.setVisible(bool(same_dimension))
        kit.set_empty_reason(
            self.dimension_empty, NO_PRECEDENTS_TITLE, NO_PRECEDENTS_HINT
        )
        self.dimension_empty.setVisible(not same_dimension)
        # Заголовки называют **как совпало**, а не чья деталь (`Search.md` v1.04).
        # Прежний «Other items…» начал бы врать: канонная секция теперь отдаёт и
        # другие ревизии своей детали.
        self.same_dimension_title.setText(
            iso(
                f"By number: no. {local_number}, all revisions of this item "
                f"({len(same_dimension)})"
            )
        )

        self.same_position.fill(same_position, reference=reference_revision)
        self.position_hint_box.setVisible(not bound)
        self.same_position.setVisible(bound and bool(same_position))
        self.position_empty.setVisible(bound and not same_position)
        self.same_position_title.setText(
            iso(
                f"By canon: position {position_label} — other items and other "
                f"revisions ({len(same_position)})"
            )
            if bound
            else "By canon: same position"
        )

        self.tabs.setTabText(0, f"{EXACT_TAB}  {len(same_dimension) + len(same_position)}")

        # Автоперехода на вторую вкладку больше нет: там нет выдачи, и уводить
        # туда оператора при пустом L1 значит показывать ему объяснение вместо
        # ответа на вопрос «случалось ли такое».
        exact_total = len(same_dimension) + len(same_position)

        self.status.setText(
            f"Exact matches: {exact_total}. "
            "Only deviations that already carry a decision are listed."
        )

    def _refresh_inspections(self, finding_id: int | None) -> None:
        """Исследования выбранной находки: **тип и короткий вывод**.

        Позиции здесь больше нет (`Inspection.md` rev 1.03): суждение по размеру
        переехало на находку и живёт колонкой в таблице находок выше.

        Читаются на выбор строки, а не на открытие карточки: свёрнутому экрану
        от исследования нужен один признак — счётчик в колонке находок, он уже
        посчитан пакетом (решение 7 QMS-018).
        """
        rows: list[tuple[int, str, str, str]] = []
        if finding_id is not None:
            with session_scope(self._engine) as session:
                finding = session.get(Finding, finding_id)
                rows = [
                    (
                        inspection.inspection_id,
                        inspection.type.name,
                        inspection.conclusion or "",
                        bool(inspection.no_protocol),
                    )
                    for inspection in sorted(
                        finding.inspections, key=lambda i: i.insp_number
                    )
                ]

        self.inspections.setRowCount(len(rows))
        for index, (inspection_id, kind, conclusion, no_protocol) in enumerate(rows):
            values = (kind, _one_line(conclusion))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, inspection_id)
                if column == INSPECTION_CONCLUSION_COLUMN and conclusion:
                    # Вывод в строке урезан, целиком — в подсказке: тот же приём,
                    # что у обоснования решения, отдельного механизма нет.
                    cell.setToolTip(conclusion)
                if column == 0:
                    cell.setData(NO_PROTOCOL_ROLE, no_protocol)
                self.inspections.setItem(index, column, cell)
            if no_protocol:
                # Запись без протокола читается **полноценно** (§4 наряда 0029):
                # тип, позиция, вывод. Пометка ставится приглушённой подсказкой у
                # типа, а не отдельной колонкой: колонка ради признака у одной
                # записи из десяти — это счётчик там, где показано содержимое.
                self.inspections.item(index, 0).setToolTip(NO_PROTOCOL_HINT)

        self.inspections.setVisible(bool(rows))
        self.inspections_empty.setVisible(not rows)
        self._refresh_protocol_button()

    def _refresh_protocol_button(self) -> None:
        """Кнопка неактивна там, где **файла нет**, а не там, где выбор пуст.

        §4 наряда 0029: у записи без протокола открывать нечего, и это не отказ, а
        отсутствие. Причину неактивности объясняет подсказка самой кнопки —
        неактивная кнопка без слов читается как поломка.
        """
        row = self.inspections.currentRow()
        cell = self.inspections.item(row, 0) if row >= 0 else None
        without = bool(cell.data(NO_PROTOCOL_ROLE)) if cell is not None else False
        self.protocol_button.setEnabled(
            self._selected_inspection_id() is not None and not without
        )
        self.protocol_button.setToolTip(NO_PROTOCOL_HINT if without else "")

    def _selected_inspection_id(self) -> int | None:
        # На видимость таблицы не смотрим: у ребёнка непоказанного окна
        # `isVisible()` ложно всегда, и кнопка «открыть протокол» оказалась бы
        # мёртвой в любом тесте (`CLAUDE.md` §9а.5). Пустая таблица и так даёт
        # `currentRow() == -1`.
        row = self.inspections.currentRow()
        if row < 0:
            return None
        cell = self.inspections.item(row, 0)
        return None if cell is None else cell.data(Qt.ItemDataRole.UserRole)

    def open_protocol(self) -> None:
        """Открыть файл протокола системным приложением.

        Существование проверяется **здесь**, а не при вводе: канон запрещает
        проверку на входе (протокол может лежать на недоступном в тот момент
        ресурсе, `Inspection.md` rev 1.01), но ссылка, которую нельзя открыть и
        которая об этом молчит, — просто текст.
        """
        inspection_id = self._selected_inspection_id()
        if inspection_id is None:
            return
        with session_scope(self._engine) as session:
            protocol = session.get(Inspection, inspection_id).protocol

        path = Path(protocol)
        if not path.exists():
            kit.show_error(self, _protocol_missing(protocol), title="Protocol not opened")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            kit.show_error(self, _protocol_not_opened(protocol), title="Protocol not opened")

    def _refresh_buttons(self, finding_id: int | None) -> None:
        """Действия по находке — только при выбранной строке (закрытие Δ S4-в)."""
        self.finding_button.setEnabled(finding_id is not None)
        self.inspect_button.setEnabled(finding_id is not None)
        self.map_button.setEnabled(finding_id is not None)

    def _selected_finding_id(self) -> int | None:
        row = self.findings.currentRow()
        if 0 <= row < len(self._finding_ids):
            return self._finding_ids[row]
        return None

    # --- действия ---------------------------------------------------------------

    def edit_deviation(self) -> None:
        """Правка — существующая форма S4; карточка перечитывается по возврату."""
        DeviationDialog.run(self._engine, self._deviation_id, self)
        self.reload()

    def set_decision(self) -> None:
        """Тот же `DecisionDialog`, что и в списке, — без единой правки."""
        if DecisionDialog.run(self._engine, self._deviation_id, self):
            self.reload()

    def open_finding(self) -> None:
        """Правка находки прямо отсюда — **та же** форма, что и в форме отклонения.

        Повод (доводка `0030`, Д-1): колонка `Outcome` показывала `Not decided`, а
        проставить исход из карточки было нечем — путь шёл через закрытие карточки,
        `Open…`, поиск находки и вход в неё. Четыре действия и уход с экрана, на
        котором инженер как раз изучает прецеденты; смысл карточки в том, чтобы
        ввод стоял там же, где происходит рассуждение.

        Второй формы не заводится — `FindingDialog` уже умеет сохранённую находку:
        номер размера она запирает, потому что другой размер это другая находка.
        Отличие от формы отклонения одно и существенное: там правки копятся в
        таблице и уходят в базу разом при сохранении отклонения, а здесь запись
        **немедленная**, и идёт она через `update_finding` — единственный путь в
        базу проходит доменом (`CLAUDE.md` §9а.18), иначе инвариант, который
        держит домен, обходится молча.

        Он же здесь и срабатывает: перевод находки в `not_permitted` под
        `approved` отбивается доменом, и отказ обязан дойти до оператора окном, а
        не пропасть — правка при этом не применяется.
        """
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return

        with session_scope(self._engine) as session:
            finding = session.get(Finding, finding_id)
            item_id = finding.deviation.item_id
            row = FindingRow(
                local_number=finding.characteristic.local_number,
                direction=finding.direction,
                value=finding.value,
                dimension_point=finding.dimension_point,
                comment=finding.comment,
                zone_id=finding.zone_id,
                deviation_type_id=finding.deviation_type_id,
                finding_id=finding.finding_id,
                inspections=len(finding.inspections),
                outcome=finding.outcome,
            )

        dialog = FindingDialog(self._engine, item_id, row, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.row is None:
            return

        edited = dialog.row
        try:
            with session_scope(self._engine) as session:
                update_finding(
                    session,
                    session.get(Finding, finding_id),
                    direction=edited.direction,
                    value=edited.value,
                    dimension_point=edited.dimension_point,
                    comment=edited.comment,
                    zone=(
                        session.get(RefZone, edited.zone_id) if edited.zone_id else None
                    ),
                    deviation_type=(
                        session.get(RefDeviationType, edited.deviation_type_id)
                        if edited.deviation_type_id
                        else None
                    ),
                    outcome=edited.outcome,
                )
        except Exception as error:
            kit.show_error(self, error, title="Finding not saved")
            return
        self.reload()

    def open_inspection(self) -> None:
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return
        if InspectionDialog.run(self._engine, finding_id, None, self):
            self.reload()

    def bind_canon(self) -> None:
        """Ранняя привязка R2 — тот же диалог, что везде.

        После возврата карточка перечитывается целиком: привязка меняет и колонку
        «канон», и секцию L1b — ради неё привязку и делают.
        """
        finding_id = self._selected_finding_id()
        if finding_id is None:
            return
        with session_scope(self._engine) as session:
            item_id = session.get(Finding, finding_id).deviation.item_id

        cg_id = choose_cg_for_item(self, self._engine, item_id)
        if cg_id is None:
            return
        open_mapping(self._engine, self, item_id, cg_id)
        self.reload()

    def _on_table_selected(self, table: PrecedentTable) -> None:
        """Выбор строки: запомнить таблицу и снять выбор в соседних.

        Три таблицы независимы, поэтому без этого выбранными оказывались строки
        сразу в двух секциях, и кнопка «Открыть прецедент…» открывала **первую**
        непустую — молча и неотличимо от нормы.

        Одного лишь запоминания мало: повторный клик по уже выбранной строке
        сигнала не даёт, и «активной» осталась бы прежняя таблица. Поэтому выбор
        физически держится в одной таблице — заодно и на экране подсвечена ровно
        одна строка. Флаг гасит рекурсию: `clearSelection` соседей сам приводит
        сюда же.
        """
        if self._syncing_selection or table.currentRow() < 0:
            return
        self._syncing_selection = True
        try:
            self._active_table = table
            for other in (self.same_dimension, self.same_position):
                if other is not table:
                    other.clearSelection()
                    other.setCurrentCell(-1, -1)
        finally:
            self._syncing_selection = False

    def open_precedent(self, table: PrecedentTable | None = None) -> None:
        """Открыть карточку прецедента поверх текущей — глубина не ограничена.

        `table` приходит от двойного клика — это таблица, по которой кликнули.
        Кнопка источника не имеет, поэтому берёт последнюю, где меняли выбор.
        """
        source = table if isinstance(table, PrecedentTable) else self._current_table()
        deviation_id = source.selected_deviation() if source else None
        if deviation_id is None:
            self.status.setText("Select a precedent row in the table first.")
            return
        try:
            CardDialog.run(self._engine, deviation_id, self)
        except Exception as error:  # pragma: no cover - защита от битой ссылки
            kit.show_error(self, error, title="Precedent not opened")

    def _current_table(self) -> PrecedentTable | None:
        """Таблица для кнопки: последняя, где меняли выбор, в пределах вкладки."""
        # На второй вкладке выдачи нет вовсе — открывать нечего, и брать строку
        # с невидимой вкладки кнопка не должна.
        if self.tabs.currentIndex() != 0:
            return None
        allowed = (self.same_dimension, self.same_position)
        if self._active_table in allowed and self._active_table.currentRow() >= 0:
            return self._active_table
        for table in allowed:
            if table.currentRow() >= 0:
                return table
        return None


def _load_findings(session, deviation: Deviation) -> list[Finding]:
    """Находки со всем, что рисует строка, — фиксированным числом запросов.

    Размер, его привязка к канону, зона и тип тянутся `selectinload`: обращение
    к связи в цикле и есть `N+1`, снятие которого — отдельный критерий наряда.
    """
    findings = session.scalars(
        select(Finding)
        .where(Finding.deviation_id == deviation.deviation_id)
        .options(
            selectinload(Finding.characteristic).selectinload(Characteristic.mapping),
            selectinload(Finding.zone),
            selectinload(Finding.deviation_type),
        )
    ).all()
    return sorted(findings, key=lambda f: dimension_sort_key(f.characteristic.local_number))


def _scrolling(content: QWidget) -> QScrollArea:
    """Обернуть вкладку в прокрутку: секции сохраняют свою высоту, а не делят её.

    Без этого две секции прецедентов делили остаток вертикали, и второй
    доставалась строка с половиной (ревью 0011, О-6). Полоса появляется только
    когда содержимое действительно не помещается.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(content)
    return area


def _one_line(text: str | None) -> str:
    """Обоснование в одну строку — в таблице многострочный текст рвёт вёрстку."""
    return " ".join((text or "").split())


def _protocol_missing(protocol: str) -> Exception:
    """Файла нет по записанному пути — говорим это словами, а не молчим."""
    from domain.errors import ValidationError

    return ValidationError(
        f"The protocol file is not there:\n{protocol}\n\n"
        "The path is stored as it was typed and is never checked on entry — the "
        "file may have moved, or the share may be unreachable from this machine. "
        "Open the inspection and correct the link."
    )


def _protocol_not_opened(protocol: str) -> Exception:
    """Файл на месте, но система его не открыла — обычно нечем."""
    from domain.errors import ValidationError

    return ValidationError(
        f"The system could not open this file:\n{protocol}\n\n"
        "There is probably no application associated with this file type."
    )


__all__ = ["CANON_NEW", "CANON_UNBOUND", "CardDialog", "PrecedentTable"]
