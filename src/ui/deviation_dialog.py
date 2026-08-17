"""Форма отклонения: шапка + находки + ранние кнопки канона (наряд 0004).

Сохранение — **одной транзакцией** по «Сохранить»: отклонение и все его находки.
Отсюда два следствия, которые видны в коде:

* находки копятся в форме строками `FindingRow` и держат номер размера, а не
  характеристику — характеристики создаст домен при записи;
* исследование на **несохранённой** находке завести нельзя: оно ссылается на
  строку в базе. Кнопка «Исследование…» для такой находки неактивна, причина
  написана в статусе.

Ранние кнопки R2 (`decisions.md`): «Привязать к канону…» зовёт тот же
`MappingDialog.run`, что и раздел «Детали», — привязка делается **до**
регистрации, ретроактивная привязка теряется. Диалог привязки пишет сразу, это
осознанно вне общей транзакции формы: канон-слой живёт независимо от того,
сохранит оператор отклонение или передумает.
"""

from __future__ import annotations

from datetime import date as date_type

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import Deviation, Finding, Inspection, Item, RefDeviationType, RefZone
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, update_registration
from domain.findings import inspection_count, make_finding, remove_finding, update_finding
from domain.inspections import remove_inspection
from domain.items import list_items

from .common import (
    DECISION_INSP_LABELS,
    direction_label,
    iso,
    ltr_field,
    number_label,
    russian_buttons,
    show_error,
)
from .finding_dialog import FindingDialog, FindingRow, canon_state
from .inspection_dialog import InspectionDialog
from .item_dialog import ItemDialog
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

FINDING_COLUMNS = (
    "Номер размера",
    "Канон",
    "Направление",
    "Величина",
    "Точка",
    "Зона",
    "Тип отклонения",
    "Исследований",
)

INSPECTION_COLUMNS = ("Номер", "Размер", "Вид", "Вердикт", "Протокол")

NO_ITEM = "— выберите деталь —"


class DeviationDialog(QDialog):
    """Регистрация и правка отклонения. Решение вносится отдельным действием."""

    def __init__(
        self, engine: Engine, deviation_id: int | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = deviation_id
        self._rows: list[FindingRow] = []
        self.setWindowTitle(
            "Новое отклонение" if deviation_id is None else "Отклонение — правка"
        )
        self.resize(1040, 720)

        # --- шапка ---
        self.item = QComboBox()
        self.new_item = QPushButton(iso("Создать деталь…"))
        self.new_item.clicked.connect(self.create_item)
        self.item.currentIndexChanged.connect(self._refresh_actions)

        item_row = QHBoxLayout()
        item_row.addWidget(self.item, 1)
        item_row.addWidget(self.new_item)

        self.wo = QLineEdit()
        self.wo.setPlaceholderText('פק"ע — например W26007336')
        self.machine = QLineEdit()
        self.machine.setPlaceholderText("станок (необязательно)")
        self.quantity = ltr_field(QSpinBox())
        # Потолок с запасом: 9999 — сентинел выборки из импорта S6 (заметка А),
        # он должен вводиться и руками, а не упираться в границу.
        self.quantity.setRange(1, 999_999)
        self.quantity.setValue(1)
        self.date = ltr_field(QDateEdit())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.date.setDate(QDate.currentDate())
        self.date.setMaximumDate(QDate.currentDate())  # дата не в будущем
        self.ncr = QLineEdit()
        self.ncr.setPlaceholderText("номер NCR (может прийти позже)")

        self.attachment = QPlainTextEdit()
        self.attachment.setPlaceholderText("по одной ссылке на строку")
        self.attachment.setFixedHeight(60)
        attach_button = QPushButton(iso("Выбрать файл…"))
        attach_button.clicked.connect(self.pick_attachment)
        attach_row = QVBoxLayout()
        attach_row.addWidget(self.attachment)
        attach_row.addWidget(attach_button)
        attach_box = QWidget()
        attach_box.setLayout(attach_row)

        header = QFormLayout()
        header.addRow("Деталь:", item_row)
        header.addRow("WO:", self.wo)
        header.addRow("Станок:", self.machine)
        header.addRow("Количество:", self.quantity)
        header.addRow("Дата:", self.date)
        header.addRow("NCR:", self.ncr)
        header.addRow("Вложения:", attach_box)

        # --- находки ---
        self.findings = QTableWidget(0, len(FINDING_COLUMNS))
        self.findings.setHorizontalHeaderLabels(FINDING_COLUMNS)
        self.findings.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.findings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings.currentCellChanged.connect(lambda *_: self._refresh_actions())

        self.add_finding = QPushButton(iso("Добавить находку…"))
        self.edit_finding = QPushButton(iso("Править…"))
        self.drop_finding = QPushButton("Убрать")
        self.map_canon = QPushButton(iso("Привязать к канону…"))
        self.inspect = QPushButton(iso("Исследование…"))
        self.add_finding.clicked.connect(self.on_add_finding)
        self.edit_finding.clicked.connect(self.on_edit_finding)
        self.drop_finding.clicked.connect(self.on_drop_finding)
        self.map_canon.clicked.connect(self.on_map_canon)
        self.inspect.clicked.connect(self.on_inspect)

        finding_buttons = QHBoxLayout()
        for button in (
            self.add_finding,
            self.edit_finding,
            self.drop_finding,
            self.map_canon,
            self.inspect,
        ):
            finding_buttons.addWidget(button)
        finding_buttons.addStretch(1)

        findings_box = QGroupBox("Находки — отклонения по размерам")
        findings_layout = QVBoxLayout(findings_box)
        findings_layout.addWidget(self.findings, 1)
        findings_layout.addLayout(finding_buttons)

        # --- исследования ---
        self.inspections = QTableWidget(0, len(INSPECTION_COLUMNS))
        self.inspections.setHorizontalHeaderLabels(INSPECTION_COLUMNS)
        self.inspections.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.inspections.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.edit_inspection = QPushButton(iso("Править исследование…"))
        self.drop_inspection = QPushButton("Удалить исследование")
        self.edit_inspection.clicked.connect(self.on_edit_inspection)
        self.drop_inspection.clicked.connect(self.on_drop_inspection)

        inspection_buttons = QHBoxLayout()
        inspection_buttons.addWidget(self.edit_inspection)
        inspection_buttons.addWidget(self.drop_inspection)
        inspection_buttons.addStretch(1)

        inspections_box = QGroupBox("Исследования отклонения")
        inspections_layout = QVBoxLayout(inspections_box)
        inspections_layout.addWidget(self.inspections, 1)
        inspections_layout.addLayout(inspection_buttons)
        self.inspections.setFixedHeight(130)

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        russian_buttons(self.buttons)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(findings_box, 1)
        layout.addWidget(inspections_box)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.reload_items()
        if deviation_id is not None:
            self.reload()
        self._refresh()

    @classmethod
    def run(
        cls, engine: Engine, deviation_id: int | None = None, parent: QWidget | None = None
    ) -> bool:
        dialog = cls(engine, deviation_id, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    # --- загрузка ---------------------------------------------------------------

    def reload_items(self, preselect: str | None = None) -> None:
        with session_scope(self._engine) as session:
            rows = [(item.item_id, item.item_number) for item in list_items(session)]

        current = preselect or self.item.currentText()
        self.item.blockSignals(True)
        self.item.clear()
        self.item.addItem(NO_ITEM, None)
        for item_id, number in rows:
            self.item.addItem(number, item_id)
        index = self.item.findText(current)
        self.item.setCurrentIndex(index if index >= 0 else 0)
        self.item.blockSignals(False)

    def reload(self) -> None:
        """Прочитать существующее отклонение в форму."""
        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            index = self.item.findData(deviation.item_id)
            self.item.setCurrentIndex(index if index >= 0 else 0)
            # Деталь после регистрации неизменна: размеры находок принадлежат
            # ей, перенос осиротил бы их (`Characteristic.md`).
            self.item.setEnabled(False)
            self.new_item.setEnabled(False)
            self.item.setToolTip("Деталь отклонения не меняется — размеры находок её.")

            self.wo.setText(deviation.wo)
            self.machine.setText(deviation.machine or "")
            self.quantity.setValue(deviation.quantity)
            self.date.setMaximumDate(_qdate(max(deviation.date, date_type.today())))
            self.date.setDate(_qdate(deviation.date))
            self.ncr.setText(deviation.ncr or "")
            self.attachment.setPlainText(deviation.attachment or "")

            self._rows = [
                FindingRow(
                    local_number=finding.characteristic.local_number,
                    direction=finding.direction,
                    value=finding.value,
                    dimension_point=finding.dimension_point,
                    comment=finding.comment,
                    zone_id=finding.zone_id,
                    deviation_type_id=finding.deviation_type_id,
                    finding_id=finding.finding_id,
                    inspections=inspection_count(session, finding),
                )
                for finding in sorted(
                    deviation.findings, key=lambda f: f.characteristic.local_number
                )
            ]

    # --- отрисовка ---------------------------------------------------------------

    def _refresh(self) -> None:
        self._refresh_findings()
        self._refresh_inspections()
        self._refresh_actions()

    def _refresh_findings(self) -> None:
        item_id = self.item.currentData()
        with session_scope(self._engine) as session:
            zones = {value.zone_id: value.name for value in session.query(RefZone)}
            kinds = {
                value.deviation_type_id: value.name for value in session.query(RefDeviationType)
            }

        self.findings.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            row.canon = canon_state(self._engine, item_id, row.local_number)
            values = (
                iso(row.local_number),
                iso(row.canon),
                direction_label(row.direction),
                number_label(row.value),
                "" if row.dimension_point is None else iso(str(row.dimension_point)),
                zones.get(row.zone_id, ""),
                kinds.get(row.deviation_type_id, ""),
                str(row.inspections),
            )
            for column, value in enumerate(values):
                self.findings.setItem(index, column, QTableWidgetItem(value))

    def _refresh_inspections(self) -> None:
        if self._deviation_id is None:
            self.inspections.setRowCount(0)
            return

        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            rows = [
                (
                    inspection.inspection_id,
                    inspection.insp_number,
                    inspection.finding.characteristic.local_number,
                    inspection.type.name,
                    DECISION_INSP_LABELS.get(
                        inspection.decision_insp, inspection.decision_insp
                    ),
                    inspection.protocol,
                )
                for inspection in sorted(
                    deviation.inspections, key=lambda i: i.insp_number
                )
            ]

        self.inspections.setRowCount(len(rows))
        for index, (inspection_id, number, local, kind, verdict, protocol) in enumerate(rows):
            cells = (iso(number), iso(local), kind, verdict, iso(protocol))
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, inspection_id)
                self.inspections.setItem(index, column, cell)

    def _refresh_actions(self) -> None:
        """Доступность кнопок и объяснение, почему «Сохранить» неактивна."""
        has_item = self.item.currentData() is not None
        row = self._current_row()

        self.add_finding.setEnabled(has_item)
        self.edit_finding.setEnabled(row is not None)
        self.drop_finding.setEnabled(row is not None)
        self.map_canon.setEnabled(has_item)
        # Исследование ссылается на строку находки в базе — на несохранённой
        # находке его завести нечем.
        self.inspect.setEnabled(row is not None and row.finding_id is not None)
        self.edit_inspection.setEnabled(self.inspections.rowCount() > 0)
        self.drop_inspection.setEnabled(self.inspections.rowCount() > 0)

        complete = has_item and bool(self._rows)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(complete)

        if not has_item:
            self.status.setText("Выберите деталь — отклонение без детали не адресуемо.")
        elif not self._rows:
            self.status.setText(
                "Добавьте хотя бы одну находку: отклонение без размера невидимо "
                "для поиска прецедентов."
            )
        elif row is not None and row.finding_id is None:
            self.status.setText(
                "Исследование заводится на сохранённой находке — сначала сохраните отклонение."
            )
        else:
            self.status.setText(
                f"Находок: {len(self._rows)}. Решение вносится отдельным действием "
                "из списка отклонений."
            )

    def _current_row(self) -> FindingRow | None:
        index = self.findings.currentRow()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    # --- действия шапки ----------------------------------------------------------

    def create_item(self) -> None:
        """Деталь заводится по ходу — штатный путь, а не исключение (§6)."""
        dialog = ItemDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_number:
            self.reload_items(preselect=dialog.created_number)
            self._refresh()

    def pick_attachment(self) -> None:
        """Путь вставляем строкой: файлы в базу не копируются (`architecture.md` §4)."""
        path, _ = QFileDialog.getOpenFileName(self, "Вложение", "", "Все файлы (*)")
        if not path:
            return
        existing = self.attachment.toPlainText().rstrip()
        self.attachment.setPlainText(f"{existing}\n{path}" if existing else path)

    # --- действия по находкам ----------------------------------------------------

    def on_add_finding(self) -> None:
        dialog = FindingDialog(self._engine, self.item.currentData(), None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.row is not None:
            if any(row.local_number == dialog.row.local_number for row in self._rows):
                QMessageBox.warning(
                    self,
                    "Размер уже в списке",
                    f"Находка по размеру №{dialog.row.local_number} в этом отклонении уже есть.",
                )
                return
            self._rows.append(dialog.row)
            self._refresh()

    def on_edit_finding(self) -> None:
        index = self.findings.currentRow()
        row = self._current_row()
        if row is None:
            return
        dialog = FindingDialog(self._engine, self.item.currentData(), row, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.row is not None:
            self._rows[index] = dialog.row
            self._refresh()

    def on_drop_finding(self) -> None:
        index = self.findings.currentRow()
        row = self._current_row()
        if row is None:
            return

        # Занятость проверяем сразу, а не при сохранении (образец S2/S3):
        # блокировка не должна всплывать через десять действий.
        if row.finding_id is not None and row.inspections:
            QMessageBox.warning(
                self,
                "Находка занята",
                f"На находке по размеру №{row.local_number} висит исследований: "
                f"{row.inspections} — сначала удалите их.",
            )
            return
        if len(self._rows) == 1:
            QMessageBox.warning(
                self,
                "Последняя находка",
                "У отклонения должна остаться хотя бы одна находка — "
                "удалите отклонение целиком из списка.",
            )
            return

        self._rows.pop(index)
        self._refresh()

    def on_map_canon(self) -> None:
        """Ранняя привязка R2 — тот же диалог, что и в разделе «Детали»."""
        item_id = self.item.currentData()
        if item_id is None:
            return
        cg_id = choose_cg_for_item(self, self._engine, item_id)
        if cg_id is None:
            return
        MappingDialog.run(self._engine, item_id, cg_id, self)
        # Колонка «канон» пересчитывается здесь же — форму переоткрывать не надо.
        self._refresh()

    def on_inspect(self) -> None:
        row = self._current_row()
        if row is None or row.finding_id is None:
            return
        if InspectionDialog.run(self._engine, row.finding_id, None, self):
            self._reload_inspection_counts()
            self._refresh()

    # --- действия по исследованиям ------------------------------------------------

    def _selected_inspection(self) -> int | None:
        row = self.inspections.currentRow()
        if row < 0:
            return None
        return self.inspections.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def on_edit_inspection(self) -> None:
        inspection_id = self._selected_inspection()
        if inspection_id is None:
            QMessageBox.information(
                self, "Не выбрано", "Сначала выберите исследование в списке."
            )
            return
        with session_scope(self._engine) as session:
            finding_id = session.get(Inspection, inspection_id).finding_id
        if InspectionDialog.run(self._engine, finding_id, inspection_id, self):
            self._refresh()

    def on_drop_inspection(self) -> None:
        inspection_id = self._selected_inspection()
        if inspection_id is None:
            QMessageBox.information(
                self, "Не выбрано", "Сначала выберите исследование в списке."
            )
            return
        if (
            QMessageBox.question(self, "Удалить исследование?", "Удалить выбранное исследование?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            with session_scope(self._engine) as session:
                remove_inspection(session, session.get(Inspection, inspection_id))
        except Exception as error:
            show_error(self, error, title="Исследование не удалено")
            return
        self._reload_inspection_counts()
        self._refresh()

    def _reload_inspection_counts(self) -> None:
        with session_scope(self._engine) as session:
            for row in self._rows:
                if row.finding_id is not None:
                    row.inspections = inspection_count(
                        session, session.get(Finding, row.finding_id)
                    )

    # --- сохранение --------------------------------------------------------------

    def save(self) -> None:
        """Отклонение и его находки — одной транзакцией."""
        item_id = self.item.currentData()
        chosen = self.date.date()
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, item_id)
                header = dict(
                    wo=self.wo.text(),
                    quantity=self.quantity.value(),
                    date=date_type(chosen.year(), chosen.month(), chosen.day()),
                    machine=self.machine.text(),
                    ncr=self.ncr.text(),
                    attachment=self.attachment.toPlainText(),
                )

                if self._deviation_id is None:
                    deviation = register(session, item=item, **header)
                else:
                    deviation = session.get(Deviation, self._deviation_id)
                    update_registration(session, deviation, **header)

                self._write_findings(session, deviation)
                self._deviation_id = deviation.deviation_id
        except Exception as error:
            show_error(self, error, title="Отклонение не сохранено")
            return
        self.accept()

    def _write_findings(self, session, deviation: Deviation) -> None:
        """Свести таблицу формы с базой: убрать, обновить, добавить."""
        kept = {row.finding_id for row in self._rows if row.finding_id is not None}
        for finding in list(deviation.findings):
            if finding.finding_id not in kept:
                remove_finding(session, finding)

        for row in self._rows:
            zone = session.get(RefZone, row.zone_id) if row.zone_id else None
            kind = (
                session.get(RefDeviationType, row.deviation_type_id)
                if row.deviation_type_id
                else None
            )
            if row.finding_id is None:
                # Размера у детали может ещё не быть — домен создаёт его без
                # формы (`_overview.md` §6), находку строит `make_finding`.
                characteristic, _ = get_or_create_characteristic(
                    session, deviation.item, row.local_number
                )
                make_finding(
                    session,
                    deviation,
                    characteristic,
                    direction=row.direction,
                    value=row.value,
                    dimension_point=row.dimension_point,
                    comment=row.comment,
                    zone=zone,
                    deviation_type=kind,
                )
            else:
                update_finding(
                    session,
                    session.get(Finding, row.finding_id),
                    direction=row.direction,
                    value=row.value,
                    dimension_point=row.dimension_point,
                    comment=row.comment,
                    zone=zone,
                    deviation_type=kind,
                )


def _qdate(value: date_type) -> QDate:
    return QDate(value.year, value.month, value.day)
