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
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from db.models import Deviation, Finding, Inspection, Item, RefDeviationType, RefZone
from db.session import session_scope
from domain.characteristics import get_or_create_characteristic
from domain.deviations import register, update_registration
from domain.findings import (
    inspection_counts,
    make_finding,
    remove_finding,
    update_finding,
)
from domain.inspections import remove_inspection
from domain.items import list_items
from domain.precedents import CANON_NEW, canon_labels_for_item

from . import kit
from .common import (
    DECISION_INSP_LABELS,
    bind_direction,
    dimension_sort_key,
    iso,
    numeric_field,
    signed_label,
)
from .finding_dialog import FindingDialog, FindingRow
from .inspection_dialog import InspectionDialog
from .item_dialog import ItemDialog
from .kit import tokens
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

#: Знак и величина — **одна** колонка, как в таблице прецедентов (решение
#: Cowork). Раздельными колонками знак и его величина расходились по краям
#: соседних столбцов и переставали читаться как одно число; слияние
#: **отображательное** — таблица read-only, правка идёт диалогом находки.
#: `Local number` → `Dim.` — язык макета (наряд 0011 §4). Колонки `Result`
#: здесь нет: она требует вердикта **на находку**, а исследование висит на
#: находке списком, и колонка появится вместе с раскрытием строки.
#: `Measurement point` с экрана тоже не снят — снятие сцеплено с раскрытием.
FINDING_COLUMNS = (
    "Dim.",
    "Canon",
    "Sign · value",
    "Zone",
    "Deviation type",
    "Measurement point",
    "Inspections",
)

#: Числовые колонки таблицы находок: величина со знаком, точка замера, счётчик.
#: Зона и тип отклонения сюда не входят потому, что это **текст**, а не число:
#: направление им считается по содержимому, как любой текстовой ячейке.
FINDING_NUMERIC_COLUMNS = (2, 5, 6)

#: Из них выравнивается вправо только **величина** (решение Cowork по ревью
#: наряда 0007): разряды встают в столбик, и разброс виден без чтения.
FINDING_MAGNITUDE_COLUMNS = (2,)

#: `Verdict` → `Result` (ратификация В-9): исследование отвечает «можно ли это
#: принять», а не «что решили», и слово «вердикт» рядом с исходом отклонения
#: читалось как второе решение по той же записи.
INSPECTION_COLUMNS = ("Number", "Characteristic", "Type", "Result", "Protocol")

NO_ITEM = "— pick an item —"


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
            "New deviation" if deviation_id is None else "Deviation — edit"
        )
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_TALL)

        # --- шапка ---
        self.item = QComboBox()
        self.new_item = kit.secondary("Create item…")
        self.new_item.clicked.connect(self.create_item)
        self.item.currentIndexChanged.connect(self._refresh_actions)

        item_row = QHBoxLayout()
        item_row.setSpacing(tokens.GAP_CONTROL)
        item_row.addWidget(self.item, 1)
        item_row.addWidget(self.new_item)

        self.wo = QLineEdit()
        self.wo.setPlaceholderText('פק"ע — e.g. W26007336')
        self.machine = QLineEdit()
        self.machine.setPlaceholderText("machine (optional)")
        # WO и станок приходят с ивритского бланка — направление за текстом.
        bind_direction(self.wo)
        bind_direction(self.machine)
        self.quantity = numeric_field(QSpinBox())
        # Потолок с запасом: 9999 — сентинел выборки из импорта S6 (заметка А),
        # он должен вводиться и руками, а не упираться в границу.
        self.quantity.setRange(1, 999_999)
        self.quantity.setValue(1)
        self.date = numeric_field(QDateEdit())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.date.setDate(QDate.currentDate())
        self.date.setMaximumDate(QDate.currentDate())  # дата не в будущем
        self.ncr = QLineEdit()
        self.ncr.setPlaceholderText("NCR number (may arrive later)")

        self.attachment = QPlainTextEdit()
        self.attachment.setPlaceholderText("one link per line")
        self.attachment.setFixedHeight(tokens.TEXT_AREA_HEIGHT)
        # Направление текстовой области резолвит Qt по абзацу — вложения
        # бывают и ивритскими, и путями сразу (ревью Р-2).
        attach_button = kit.secondary("Choose file…")
        attach_button.clicked.connect(self.pick_attachment)
        attach_row = QVBoxLayout()
        attach_row.setSpacing(tokens.GAP_CONTROL)
        attach_row.addWidget(self.attachment)
        attach_row.addLayout(kit.button_row(attach_button))
        attach_box = kit.boxed(attach_row)

        header = kit.stretching_form()
        header.addRow("Item:", item_row)
        header.addRow("WO:", self.wo)
        header.addRow("Machine:", self.machine)
        # Подпись количества — как в списке (`Dev. qty`): это средний из трёх
        # уровней количества, а не размер партии (наряд 0011 §4).
        header.addRow("Deviating quantity:", self.quantity)
        header.addRow("Date:", self.date)
        header.addRow("NCR:", self.ncr)
        header.addRow("Attachments:", attach_box)

        # --- находки ---
        self.findings = kit.data_table(
            FINDING_COLUMNS,
            numeric_columns=FINDING_NUMERIC_COLUMNS,
            magnitude_columns=FINDING_MAGNITUDE_COLUMNS,
        )
        self.findings.currentCellChanged.connect(lambda *_: self._refresh_actions())
        # Таблица находок — то, ради чего форма открыта: она не имеет права
        # схлопнуться в одну шапку, когда шапка отклонения разрослась.
        self.findings.setMinimumHeight(tokens.INLINE_TABLE_HEIGHT)

        self.add_finding = kit.primary("Add finding…")
        self.edit_finding = kit.secondary("Edit…")
        self.drop_finding = kit.danger("Remove")
        self.map_canon = kit.secondary("Mapping…")
        self.inspect = kit.secondary("Inspection…")
        self.add_finding.clicked.connect(self.on_add_finding)
        self.edit_finding.clicked.connect(self.on_edit_finding)
        self.drop_finding.clicked.connect(self.on_drop_finding)
        self.map_canon.clicked.connect(self.on_map_canon)
        self.inspect.clicked.connect(self.on_inspect)

        finding_buttons = kit.button_row(
            self.add_finding,
            self.edit_finding,
            self.drop_finding,
            self.map_canon,
            self.inspect,
        )

        findings_box = QGroupBox("Findings — deviations by characteristic")
        findings_layout = QVBoxLayout(findings_box)
        findings_layout.addWidget(self.findings, 1)
        findings_layout.addLayout(finding_buttons)

        # --- исследования ---
        self.inspections = kit.data_table(INSPECTION_COLUMNS)
        self.inspections.currentCellChanged.connect(lambda *_: self._refresh_actions())
        self.edit_inspection = kit.secondary("Edit inspection…")
        self.drop_inspection = kit.danger("Delete inspection")
        self.edit_inspection.clicked.connect(self.on_edit_inspection)
        self.drop_inspection.clicked.connect(self.on_drop_inspection)

        inspection_buttons = kit.button_row(
            self.edit_inspection, self.drop_inspection
        )

        inspections_box = QGroupBox("Inspections of this deviation")
        inspections_layout = QVBoxLayout(inspections_box)
        inspections_layout.addWidget(self.inspections, 1)
        inspections_layout.addLayout(inspection_buttons)
        kit.inline_table_height(self.inspections, short=True)

        self.status = kit.status_label()

        self.buttons = kit.dialog_buttons(accept="Save deviation")
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        layout = kit.dialog_layout(self)
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

    @property
    def deviation_id(self) -> int | None:
        """Id записи. У новой формы появляется только после успешного сохранения —
        по нему список открывает карточку (`card_dialog`, решение Cowork 1)."""
        return self._deviation_id

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
            self.item.setToolTip(
                "The item of a deviation does not change — "
                "the characteristics of its findings belong to it."
            )

            self.wo.setText(deviation.wo)
            self.machine.setText(deviation.machine or "")
            self.quantity.setValue(deviation.quantity)
            self.date.setMaximumDate(_qdate(max(deviation.date, date_type.today())))
            self.date.setDate(_qdate(deviation.date))
            self.ncr.setText(deviation.ncr or "")
            self.attachment.setPlainText(deviation.attachment or "")

            findings = _load_findings(session, deviation)
            counts = inspection_counts(session, findings)
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
                    inspections=counts.get(finding.finding_id, 0),
                )
                for finding in findings
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
            # Пакетно, а не построчно: прежний `canon_state` открывал сессию на
            # каждую находку (`docs/specs/deviation-entry.md` §8, N+1).
            item = session.get(Item, item_id) if item_id is not None else None
            canon = canon_labels_for_item(
                session, item, [row.local_number for row in self._rows]
            )

        self.findings.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            row.canon = canon.get(row.local_number, CANON_NEW)
            values = (
                iso(row.local_number),
                iso(row.canon),
                signed_label(row.direction, row.value),
                zones.get(row.zone_id, ""),
                kinds.get(row.deviation_type_id, ""),
                "" if row.dimension_point is None else iso(str(row.dimension_point)),
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
        # По выбранной строке, а не по «в таблице есть строки»: иначе кнопка
        # активна, а в ответ говорит «Сначала выберите» (Δ S4-в).
        selected = self.inspections.currentRow() >= 0
        self.edit_inspection.setEnabled(selected)
        self.drop_inspection.setEnabled(selected)

        complete = has_item and bool(self._rows)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(complete)

        if not has_item:
            self.status.setText(
                "Pick an item — a deviation without an item cannot be addressed."
            )
        elif not self._rows:
            self.status.setText(
                "Add at least one finding: a deviation with no characteristic is "
                "invisible to precedent search."
            )
        elif row is not None and row.finding_id is None:
            self.status.setText(
                "An inspection is created on a saved finding — save the deviation first."
            )
        else:
            self.status.setText(
                f"Findings: {len(self._rows)}. The decision is entered as a separate "
                "action from the deviation list."
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
        path, _ = QFileDialog.getOpenFileName(self, "Attachment", "", "All files (*)")
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
                    "Characteristic already listed",
                    f"A finding on characteristic no. {dialog.row.local_number} "
                    "already exists in this deviation.",
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
                "Finding is in use",
                f"The finding on characteristic no. {row.local_number} carries "
                f"inspections: {row.inspections} — delete them first.",
            )
            return
        if len(self._rows) == 1:
            QMessageBox.warning(
                self,
                "Last finding",
                "A deviation must keep at least one finding — "
                "delete the whole deviation from the list instead.",
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
                self, "Nothing selected", "Select an inspection in the list first."
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
                self, "Nothing selected", "Select an inspection in the list first."
            )
            return
        if (
            QMessageBox.question(
                self, "Delete inspection?", "Delete the selected inspection?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            with session_scope(self._engine) as session:
                remove_inspection(session, session.get(Inspection, inspection_id))
        except Exception as error:
            kit.show_error(self, error, title="Inspection not deleted")
            return
        self._reload_inspection_counts()
        self._refresh()

    def _reload_inspection_counts(self) -> None:
        saved = [row for row in self._rows if row.finding_id is not None]
        if not saved:
            return
        with session_scope(self._engine) as session:
            counts = inspection_counts(
                session, [session.get(Finding, row.finding_id) for row in saved]
            )
        for row in saved:
            row.inspections = counts.get(row.finding_id, 0)

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
            kit.show_error(self, error, title="Deviation not saved")
            return
        self.accept()

    def _write_findings(self, session, deviation: Deviation) -> None:
        """Свести таблицу формы с базой: **сначала записать, потом убрать**.

        Порядок здесь — не вкусовщина. Если удалять первым, замена всех находок
        сразу упирается в доменный гард «должна остаться хотя бы одна»: новых в
        базе ещё нет, и последнее удаление отбивается, хотя замена в форме есть.
        А это штатный путь — номер размера у сохранённой находки не правится, и
        «добавить правильную, убрать неправильную» единственный способ исправить
        опечатку в номере.

        Множество `keep` собирается **по ходу записи**, а не из `self._rows`
        заранее: у новой строки `finding_id` ещё `None`, и посчитанное до записи
        множество не содержало бы только что созданных находок — цикл удаления
        снёс бы их следом.

        Удаление и дальше идёт через `remove_finding`: оба гарда — по
        исследованиям и «последняя» — остаются в силе, но теперь видят уже
        записанные новые находки.
        """
        keep: set[int] = set()

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
                finding = make_finding(
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
                finding = update_finding(
                    session,
                    session.get(Finding, row.finding_id),
                    direction=row.direction,
                    value=row.value,
                    dimension_point=row.dimension_point,
                    comment=row.comment,
                    zone=zone,
                    deviation_type=kind,
                )
            # `make_finding` уже сделал flush, так что id проставлен.
            keep.add(finding.finding_id)

        for finding in list(deviation.findings):
            if finding.finding_id not in keep:
                remove_finding(session, finding)


def _load_findings(session, deviation: Deviation) -> list[Finding]:
    """Находки отклонения вместе с размером — фиксированным числом запросов.

    Сортировать по `finding.characteristic.local_number` без `selectinload`
    значит подгружать характеристику на каждую строку: обращение к связи и есть
    тот самый `N+1`, который наряд 0005 велит снять. `selectinload` добавляет
    один запрос на связь — независимо от числа находок.
    """
    findings = session.scalars(
        select(Finding)
        .where(Finding.deviation_id == deviation.deviation_id)
        .options(selectinload(Finding.characteristic))
    ).all()
    return sorted(findings, key=lambda f: dimension_sort_key(f.characteristic.local_number))


def _qdate(value: date_type) -> QDate:
    return QDate(value.year, value.month, value.day)
