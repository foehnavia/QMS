"""Карточка отклонения — рабочий экран и главный deliverable Этапа 1 (наряд 0005).

Смысл экрана один: инженер, глядя на отклонение, сразу видит, случалось ли такое
раньше, что тогда решили и как обосновали (`DeviationCard.md`, шаг 6 процесса).
Ради этого карточка открывается **сама** после регистрации нового отклонения.

Прецеденты показываются **по выбранной находке**, а не по отклонению целиком
(решение Cowork 2): отклонение с пятью размерами иначе свалило бы в одну кучу
разное, а инженер работает с конкретным размером.

Вкладки — уровни поиска (`Search.md`): «Точные (L1)» по паре «деталь + размер» и
по канонической позиции, «Похожие (L2)» по зоне и типу. Если L1 пуст, карточка
открывается на L2 — так видно, что описательный поиск вообще есть.

Своего диалога решения здесь нет: `DecisionDialog` переехал из списка **как
есть** — S4 сделал его самостоятельным ровно для этого.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from db.models import Characteristic, Deviation, Direction, Finding, Item
from db.session import session_scope
from domain.findings import inspection_counts
from domain.precedents import (
    CANON_NEW,
    CANON_UNBOUND,
    PrecedentRow,
    canon_labels,
    precedents_descriptive,
    precedents_same_dimension,
    precedents_same_position,
)

from .common import (
    decision_dev_label,
    dimension_sort_key,
    direction_label,
    directional,
    iso,
    joined,
    number_label,
    show_error,
)
from .decision_dialog import DecisionDialog
from .deviation_dialog import (
    FINDING_COLUMNS,
    FINDING_NUMERIC_COLUMNS,
    DeviationDialog,
)
from .inspection_dialog import InspectionDialog
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

PRECEDENT_COLUMNS = (
    "Deviation",
    "Date",
    "Item",
    "WO",
    "Characteristic",
    "Sign · value",
    "Decision",
    "Explanation",
    "Insp.",
)

#: Числовые колонки прецедента: дата, знак с величиной, счётчик исследований.
PRECEDENT_NUMERIC_COLUMNS = (1, 5, 8)

#: Подписи для колонки «совпало по» вкладки L2.
MATCH_LABELS = {
    "zone+type": "zone and type",
    "zone": "zone",
    "type": "deviation type",
}

UNBOUND_HINT = (
    "This characteristic is not bound to the canon — search by position is "
    "unavailable. Binding is exactly what finds the same design node on other items."
)

NO_LABELS_HINT = (
    "The finding carries neither a zone nor a deviation type — descriptive search "
    "rests on exactly these two fields. Fill them in and this tab comes alive."
)

NO_SELECTION_HINT = (
    "Pick a finding in the table above — precedents are searched by its characteristic."
)


class PrecedentTable(QTableWidget):
    """Таблица прецедентов. Единица строки — **отклонение целиком** (`Search.md`)."""

    def __init__(self, *, with_match: bool = False, parent: QWidget | None = None) -> None:
        columns = PRECEDENT_COLUMNS + (("Matched on",) if with_match else ())
        super().__init__(0, len(columns), parent)
        self._with_match = with_match
        self.setHorizontalHeaderLabels(columns)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        directional(self, PRECEDENT_NUMERIC_COLUMNS)

    def fill(self, rows: list[PrecedentRow]) -> None:
        # Выбор сбрасываем: строки другие, а уцелевшее выделение делало бы вид,
        # что оператор что-то выбрал в таблице, которую он ещё не смотрел.
        self.clearSelection()
        self.setCurrentCell(-1, -1)
        self.setRowCount(len(rows))
        for index, row in enumerate(rows):
            # Составная ячейка: номер размера и g-подпись — самостоятельные
            # токены, каждый в своём изоляте (наряд 0007, §4а).
            size = joined(row.local_number, row.g_label)
            values = [
                iso(row.dev_number),
                iso(f"{row.date:%d.%m.%Y}"),
                iso(row.item_number),
                iso(row.wo),
                size,
                _signed(row.direction, row.value),
                decision_dev_label(row.decision),
                _one_line(row.explanation),
                str(row.inspection_count),
            ]
            if self._with_match:
                values.append(MATCH_LABELS.get(row.match, row.match))

            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row.deviation_id)
                if column == 4 and row.g_label:
                    # Узкая колонка съедает имя группы — оно нужно, чтобы понять,
                    # по какому канону совпало; держим в подсказке.
                    cell.setToolTip(f"{row.local_number} · {row.g_label}")
                if column == 7:
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

    def __init__(self, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = deviation_id
        self._finding_ids: list[int] = []
        # Автопереход на L2 — только при открытии карточки: иначе смена
        # находки выкидывала бы оператора с вкладки, выбранной руками.
        self._first_render = True
        self.resize(1180, 820)

        # --- шапка ---
        self.number = QLabel()
        self.item_label = QLabel()
        self.wo = QLabel()
        self.machine = QLabel()
        self.quantity = QLabel()
        self.date = QLabel()
        self.ncr = QLabel()
        self.attachment = QLabel()
        self.attachment.setWordWrap(True)
        self.decision = QLabel()
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)

        # Поля не растягиваются на всю ширину: иначе значение уезжает от своей
        # подписи через полэкрана и липнет к подписи соседней колонки.
        head_left = _compact_form()
        head_left.addRow("Deviation:", self.number)
        head_left.addRow("Item:", self.item_label)
        head_left.addRow("WO:", self.wo)
        head_left.addRow("Machine:", self.machine)
        head_right = _compact_form()
        head_right.addRow("Quantity:", self.quantity)
        head_right.addRow("Date:", self.date)
        head_right.addRow("NCR:", self.ncr)
        head_right.addRow("Attachments:", self.attachment)

        # Каждая колонка — в своём виджете: соседние QFormLayout иначе делят
        # ширину так, что значение левой оказывается вплотную к подписи правой.
        head_columns = QHBoxLayout()
        head_columns.addWidget(_boxed(head_left), 1)
        head_columns.addWidget(_boxed(head_right), 1)

        decision_form = _compact_form()
        decision_form.addRow("Decision:", self.decision)
        decision_form.addRow("Explanation:", self.explanation)

        self.edit_button = QPushButton(iso("Edit…"))
        self.decision_button = QPushButton(iso("Decision…"))
        self.close_button = QPushButton("Close")
        self.edit_button.clicked.connect(self.edit_deviation)
        self.decision_button.clicked.connect(self.set_decision)
        self.close_button.clicked.connect(self.reject)

        head_buttons = QHBoxLayout()
        head_buttons.addWidget(self.edit_button)
        head_buttons.addWidget(self.decision_button)
        head_buttons.addStretch(1)

        header_box = QGroupBox("Deviation")
        header_layout = QVBoxLayout(header_box)
        header_layout.addLayout(head_columns)
        header_layout.addLayout(decision_form)
        header_layout.addLayout(head_buttons)

        # --- находки ---
        self.findings = QTableWidget(0, len(FINDING_COLUMNS))
        self.findings.setHorizontalHeaderLabels(FINDING_COLUMNS)
        self.findings.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.findings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.findings.currentCellChanged.connect(lambda *_: self.refresh_precedents())
        directional(self.findings, FINDING_NUMERIC_COLUMNS)

        self.inspect_button = QPushButton(iso("Inspection…"))
        self.map_button = QPushButton(iso("Bind to canon…"))
        self.inspect_button.clicked.connect(self.open_inspection)
        self.map_button.clicked.connect(self.bind_canon)

        finding_buttons = QHBoxLayout()
        finding_buttons.addWidget(self.inspect_button)
        finding_buttons.addWidget(self.map_button)
        finding_buttons.addStretch(1)

        findings_box = QGroupBox(
            "Findings — pick a characteristic; precedents are searched by it"
        )
        findings_layout = QVBoxLayout(findings_box)
        findings_layout.addWidget(self.findings, 1)
        findings_layout.addLayout(finding_buttons)
        self.findings.setFixedHeight(150)

        # --- прецеденты ---
        self.same_dimension = PrecedentTable()
        self.same_position = PrecedentTable()
        self.descriptive = PrecedentTable(with_match=True)
        self._active_table: PrecedentTable | None = None
        self._syncing_selection = False
        for table in (self.same_dimension, self.same_position, self.descriptive):
            # Таблицу передаём явно: двойной клик во второй секции обязан открыть
            # строку второй секции, а не «первой, где что-то выбрано».
            table.doubleClicked.connect(
                lambda *_args, source=table: self.open_precedent(source)
            )
            table.itemSelectionChanged.connect(
                lambda source=table: self._on_table_selected(source)
            )

        self.same_dimension_title = QLabel()
        self.same_position_title = QLabel()
        self.position_hint = QLabel(UNBOUND_HINT)
        self.position_hint.setWordWrap(True)
        self.position_hint_button = QPushButton(iso("Bind to canon…"))
        self.position_hint_button.clicked.connect(self.bind_canon)
        hint_row = QHBoxLayout()
        hint_row.addWidget(self.position_hint, 1)
        hint_row.addWidget(self.position_hint_button)
        self.position_hint_box = QWidget()
        self.position_hint_box.setLayout(hint_row)

        exact = QWidget()
        exact_layout = QVBoxLayout(exact)
        exact_layout.addWidget(self.same_dimension_title)
        exact_layout.addWidget(self.same_dimension, 1)
        exact_layout.addWidget(self.same_position_title)
        exact_layout.addWidget(self.position_hint_box)
        exact_layout.addWidget(self.same_position, 1)

        self.descriptive_hint = QLabel(NO_LABELS_HINT)
        self.descriptive_hint.setWordWrap(True)
        similar = QWidget()
        similar_layout = QVBoxLayout(similar)
        similar_layout.addWidget(self.descriptive_hint)
        similar_layout.addWidget(self.descriptive, 1)

        self.tabs = QTabWidget()
        self.tabs.addTab(exact, "Exact precedents (L1)")
        self.tabs.addTab(similar, "Descriptive precedents (L2)")

        self.open_button = QPushButton(iso("Open precedent…"))
        self.open_button.clicked.connect(lambda: self.open_precedent())
        self.status = QLabel()
        self.status.setWordWrap(True)

        footer = QHBoxLayout()
        footer.addWidget(self.open_button)
        footer.addStretch(1)
        footer.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(header_box)
        layout.addWidget(findings_box)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> None:
        """Открыть карточку. Возврата не имеет: карточка ничего не решает сама."""
        cls(engine, deviation_id, parent).exec()

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
            self.wo.setText(iso(deviation.wo))
            self.machine.setText(iso(deviation.machine or "—"))
            self.quantity.setText(iso(str(deviation.quantity)))
            self.date.setText(iso(f"{deviation.date:%d.%m.%Y}"))
            self.ncr.setText(iso(deviation.ncr or "—"))
            self.attachment.setText(iso(deviation.attachment or "—"))
            self.decision.setText(decision_dev_label(deviation.decision_dev))
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
                )
                for finding in findings
            ]

        self._finding_ids = [row[0] for row in rows]
        self.findings.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                iso(row[1]),
                iso(row[2]),
                direction_label(row[3]),
                number_label(row[4]),
                "" if row[5] is None else iso(str(row[5])),
                row[6],
                row[7],
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
        """Перерисовать обе вкладки под выбранную находку."""
        finding_id = self._selected_finding_id()
        self._refresh_buttons(finding_id)

        if finding_id is None:
            for table in (self.same_dimension, self.same_position, self.descriptive):
                table.setRowCount(0)
            self.same_dimension_title.setText(NO_SELECTION_HINT)
            self.same_position_title.setText("")
            self.position_hint_box.setVisible(False)
            self.descriptive_hint.setVisible(True)
            self.descriptive_hint.setText(NO_SELECTION_HINT)
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
            descriptive = precedents_descriptive(
                session,
                zone=finding.zone,
                deviation_type=finding.deviation_type,
                exclude_deviation=deviation,
                exclude_characteristic=characteristic,
            )
            has_labels = finding.zone is not None or finding.deviation_type is not None
            local_number = characteristic.local_number

        self.same_dimension.fill(same_dimension)
        self.same_dimension_title.setText(
            iso(f"Same item, same characteristic no. {local_number} ({len(same_dimension)})")
        )

        self.same_position.fill(same_position)
        self.position_hint_box.setVisible(not bound)
        self.same_position.setVisible(bound)
        self.same_position_title.setText(
            iso(f"Other items, same position {position_label} ({len(same_position)})")
            if bound
            else "Other items, same position"
        )

        self.descriptive.fill(descriptive)
        self.descriptive.setVisible(has_labels)
        self.descriptive_hint.setVisible(not has_labels)
        self.descriptive_hint.setText(NO_LABELS_HINT)

        # Если точных совпадений нет — сразу показываем описательные: иначе
        # оператор видит две пустые таблицы и не догадывается про вторую вкладку.
        # Только при открытии: дальше вкладку выбирает оператор.
        exact_total = len(same_dimension) + len(same_position)
        if exact_total == 0 and self._first_render:
            self.tabs.setCurrentIndex(1)
        self._first_render = False

        self.status.setText(
            f"Exact matches: {exact_total} · descriptive: {len(descriptive)}. "
            "Only deviations that already carry a decision are listed."
        )

    def _refresh_buttons(self, finding_id: int | None) -> None:
        """Действия по находке — только при выбранной строке (закрытие Δ S4-в)."""
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
        MappingDialog.run(self._engine, item_id, cg_id, self)
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
            for other in (self.same_dimension, self.same_position, self.descriptive):
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
            show_error(self, error, title="Precedent not opened")

    def _current_table(self) -> PrecedentTable | None:
        """Таблица для кнопки: последняя, где меняли выбор, в пределах вкладки."""
        on_descriptive = self.tabs.currentIndex() == 1
        allowed = (
            (self.descriptive,)
            if on_descriptive
            else (self.same_dimension, self.same_position)
        )
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


def _compact_form() -> QFormLayout:
    """Форма, в которой поле остаётся рядом с подписью, а не растягивается."""
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    return form


def _boxed(layout: QFormLayout) -> QWidget:
    box = QWidget()
    box.setLayout(layout)
    return box


def _signed(direction: str, value: float | None) -> str:
    """Знак и величина одной ячейкой — **один** изолят на всю строку.

    Изолировать знак и число по отдельности мало: два изолята подряд остаются
    двумя runs, и в RTL-ячейке они раскладываются справа налево — `− 0.05`
    показывалось как `0.05 −`. Изолят вокруг собранной строки держит и знак при
    числе, и порядок токенов.
    """
    sign = "+" if direction == Direction.PLUS else "−"
    number = "" if value is None else f"{value:g}"
    return iso(f"{sign} {number}".strip())


def _one_line(text: str | None) -> str:
    """Обоснование в одну строку — в таблице многострочный текст рвёт вёрстку."""
    return " ".join((text or "").split())


__all__ = ["CANON_NEW", "CANON_UNBOUND", "CardDialog", "PrecedentTable"]
