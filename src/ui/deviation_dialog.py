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

from db.models import (
    Deviation,
    Finding,
    Inspection,
    Item,
    ItemRevision,
    RefDeviationType,
    RefInspectionType,
    RefZone,
)
from db.session import session_scope
from domain.reference import list_values
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
from domain.revisions import list_revisions
from domain.precedents import CANON_NEW, canon_labels_for_item

from . import kit
from .common import (
    bind_direction,
    outcome_label,
    dimension_sort_key,
    iso,
    numeric_field,
    optional_id,
    signed_label,
)
from .finding_dialog import FindingDialog, FindingRow
from .inspection_dialog import InspectionDialog
from .item_dialog import ItemDialog, _combo, complete_new_item, open_mapping
from .kit import tokens
from .mapping_dialog import MappingDialog
from .pickers import choose_cg_for_item

#: Знак и величина — **одна** колонка, как в таблице прецедентов (решение
#: Cowork). Раздельными колонками знак и его величина расходились по краям
#: соседних столбцов и переставали читаться как одно число; слияние
#: **отображательное** — таблица read-only, правка идёт диалогом находки.
#: `Local number` → `Dim.` — язык макета (наряд 0011 §4).
#:
#: `Outcome` появилась с QMS-025: суждение по размеру живёт на находке, и без
#: колонки таблица не говорила, **какой размер отклонил партию**. Стоит перед
#: счётчиком исследований намеренно — это суждение, а исследования лишь сведения
#: к нему; порядок колонок и есть порядок чтения.
FINDING_COLUMNS = (
    "Dim.",
    "Canon",
    "Sign · value",
    "Zone",
    "Deviation type",
    "Measurement point",
    "Outcome",
    "Inspections",
)

#: Колонки, **скрытые до набора статистики** (наряд `0032` §6).
#:
#: `Measurement point` скрыта, а не удалена: статистики по её нужности пока нет, а
#: место в таблице она занимает. Поле модели, миграция, домен и форма находки не
#: тронуты вовсе — данные пишутся и хранятся как раньше, скрыт только **показ**.
#:
#: Возврат стоит **одного изменения в одном месте**: убрать имя из этого кортежа.
#: Ни списки ширин, ни расчёт индексов, ни сборка строк не знают о сокрытии —
#: они по-прежнему перечисляют все колонки, и потому вычёркивать из них ничего не
#: придётся. Проверено исполнением: с пустым кортежем колонка возвращается на
#: своё место со своей шириной.
HIDDEN_FINDING_COLUMNS = ("Measurement point",)

#: Ширины таблицы находок — **пиксели, назначенные замером** (`CLAUDE.md` §9а.12).
#:
#: Переведены со знакомест на замер вместе с появлением колонки `Outcome`
#: (QMS-025, §4 наряда `0030`): прежняя сетка давала 1051 px при нужных по замеру
#: 854, и восьмая колонка вывела таблицу за край диалога — появилась
#: горизонтальная прокрутка, которой у таблицы карточки быть не должно.
#:
#: Замер на нативной платформе, «нужно тексту + 27 непечатаемого» (линия сетки,
#: отступы листа стиля, поля Qt), запас — до круглого числа:
#:   `Dim.`               53 (`19`; заголовок 46)          ->  64
#:   `Canon`              88 (`not bound`)                 ->  96
#:   `Sign · value`       93 (заголовок шире значения)     -> 100
#:   `Zone`              139 (`Internal Connection`)       -> 148
#:   `Deviation type`    138 (`Cutting-edge width`)        -> 148
#:   `Measurement point` 141 (заголовок; значение — цифра) -> 148
#:   `Outcome`           110 (`Not permitted`)             -> 120
#:   `Inspections`        92 (заголовок)                   -> 100
#: Сумма 924 из 1180 диалога; остаток — зона запаса.
#:
#: `Inspections` заодно перестала быть `FIT_LABEL`: та формула давала ей 85 px при
#: нужных 92 — недобор в 7 px, который есть у каждой колонки по заголовку и
#: чинится задачей **QMS-022**, а не здесь.
FINDING_WIDTHS = (
    kit.px(64),
    kit.px(96),
    kit.px(100),
    kit.px(148),
    kit.px(148),
    kit.px(148),
    kit.px(120),
    kit.px(100),
)

FINDING_NUMERIC_COLUMNS = tuple(
    FINDING_COLUMNS.index(name)
    for name in ("Sign · value", "Measurement point", "Inspections")
)

#: Из них выравнивается вправо только **величина** (решение Cowork по ревью
#: наряда 0007): разряды встают в столбик, и разброс виден без чтения.
FINDING_MAGNITUDE_COLUMNS = (FINDING_COLUMNS.index("Sign · value"),)


def hide_finding_columns(table) -> None:
    """Спрятать колонки из `HIDDEN_FINDING_COLUMNS` в таблице находок.

    Прячется **показ**, а не данные: строка по-прежнему собирается со всеми
    значениями, и вернуть колонку стоит одного изменения в одном месте. Зовут
    оба экрана, показывающие находки, — иначе одна и та же колонка была бы видна
    на одном и скрыта на другом, а это ровно то расхождение, ради устранения
    которого списки колонок и общие.
    """
    for name in HIDDEN_FINDING_COLUMNS:
        table.setColumnHidden(FINDING_COLUMNS.index(name), True)


#: Колонка `Result` снята вместе с позицией исследования (QMS-025): исследование
#: суждения не несёт вовсе, и показывать было бы нечего. Суждение по размеру —
#: колонка `Outcome` в таблице находок выше.
INSPECTION_COLUMNS = ("Number", "Characteristic", "Type", "Protocol")

#: Ширины по правилу §8.3; чисел на эту таблицу §7.3 не давал — считаны здесь по
#: той же формуле max(заголовок, рекорд) × 1.25 на значениях базы прогона.
#: Повод объявить их сейчас: со сменой единицы (§8) `Implantation torque test`
#: стал резаться до «Implantation tor…», а угаданный по подписи класс этого не
#: покрывает. `Characteristic` — номер размера, счётчиком не является, но и не
#: растёт: его держит заголовок. `Protocol` — путь к файлу, предел с обрезкой.
#: `Number` — номер исследования, `Characteristic` — номер размера (счётчиком не
#: является); `Type` — закрытый список справочника, `Protocol` — путь к файлу,
#: то есть свободный текст (наряд `0034` §2).
INSPECTION_WIDTHS = (
    # Эталон — **настоящий** номер, а не похожий на него: формат
    # `INSP-YYMMDD-NNN`, пятнадцать знаков. Придуманный `INS-2609-0001`
    # (тринадцать) резал каждую строку таблицы, и поймала это сводная проверка
    # обрезки, а не тест (наряд `0035`, критерий 1).
    kit.fixed("INSP-260909-002"),
    kit.FIT_LABEL,
    kit.closed(()),
    kit.free(),
)

#: Подсказка пустого поля детали. Прежде это была строка списка со значением
#: `None`; у поля с отбором пустое состояние показывает сама строка ввода.
NO_ITEM = "— pick an item —"

#: Ревизия выбирается до находок: номер размера читается против чертежа.
REVISION_HINT = (
    "Pick the drawing revision the parts were made to. Local numbers below are "
    "read against it; parts of a previous issue keep arriving for two to three "
    "months after a change."
)


class DeviationDialog(QDialog):
    """Регистрация и правка отклонения. Решение вносится отдельным действием."""

    def __init__(
        self,
        engine: Engine,
        deviation_id: int | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = optional_id(deviation_id, "deviation_id")
        self._rows: list[FindingRow] = []
        self.setWindowTitle(
            "New deviation" if self._deviation_id is None else "Deviation — edit"
        )
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_TALL)

        # --- шапка ---
        # Поле с отбором, а не обычный список: на производственном наборе
        # деталей выбирать `MF5-10375A-N` прокруткой нечем — первая буква
        # переставляла отметку, вторая начинала поиск заново (находка №17).
        self.item = kit.FilterCombo(NO_ITEM)
        self.new_item = kit.secondary("Create item…")
        self.new_item.clicked.connect(self.create_item)
        self.item.keyChanged.connect(self._refresh_actions)
        # Ревизии принадлежат детали: сменилась деталь — список обязан
        # перечитаться, иначе на экране остались бы чужие обозначения.
        self.item.keyChanged.connect(lambda *_: self.reload_revisions())

        item_row = QHBoxLayout()
        item_row.setSpacing(tokens.GAP_CONTROL)
        item_row.addWidget(self.item, 1)
        item_row.addWidget(self.new_item)

        # Ревизия выбирается **до** находок: локальный номер читается против
        # чертежа, и выбрать чертёж после номеров значило бы вводить их вслепую
        # (QMS-017). По умолчанию действующая — массовый случай; перевод на
        # прежнюю остаётся явным действием оператора, потому что детали прежнего
        # выпуска приходят из цеха ещё два-три месяца после смены.
        self.revision = _combo()
        self.revision.currentIndexChanged.connect(self._revision_changed)
        self.revision_hint = kit.hint(REVISION_HINT)

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
        header.addRow("Revision:", self.revision)
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
            widths=FINDING_WIDTHS,
        )
        hide_finding_columns(self.findings)
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
        self.inspections = kit.data_table(INSPECTION_COLUMNS, widths=INSPECTION_WIDTHS)
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
        layout.addWidget(self.revision_hint)
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
        dialog = cls(engine, deviation_id, parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    @property
    def deviation_id(self) -> int | None:
        """Id записи. У новой формы появляется только после успешного сохранения —
        по нему список открывает карточку (`card_dialog`, решение Cowork 1)."""
        return self._deviation_id

    # --- загрузка ---------------------------------------------------------------

    def reload_items(self, preselect: str | None = None) -> None:
        """Перечитать список деталей, сохранив выбор.

        Выбор держится **ключом**, а не подписью: номер детали правится формой
        (`update_item`), и искать по нему прежний выбор значило бы терять его
        ровно тогда, когда номер поправили.
        """
        with session_scope(self._engine) as session:
            rows = [(item.item_id, item.item_number) for item in list_items(session)]

        keep = self.item.current_key()
        self.item.set_rows(rows)
        if preselect is not None:
            self.item.setCurrentText(preselect)
        elif keep is not None:
            self.item.select_key(keep)
        # `set_rows` сигналов не поднимает, поэтому ревизии перечитываются
        # здесь явно: иначе после заведения детали список остался бы пустым.
        self.reload_revisions()

    def reload(self) -> None:
        """Прочитать существующее отклонение в форму."""
        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            self.item.select_key(deviation.item_id)
            self.reload_revisions()
            index = self.revision.findData(deviation.revision_id)
            if index >= 0:
                self.revision.setCurrentIndex(index)
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
                    outcome=finding.outcome,
                )
                for finding in findings
            ]

    # --- отрисовка ---------------------------------------------------------------

    def _refresh(self) -> None:
        self._refresh_findings()
        self._refresh_inspections()
        self._refresh_actions()

    def reload_revisions(self, keep: str | None = None) -> None:
        """Перечитать ревизии выбранной детали; по умолчанию — действующая.

        Зовётся при смене детали и после заведения новой. `keep` держит выбор
        оператора там, где деталь не менялась: перезагрузка справочника не имеет
        права молча вернуть его на действующую.
        """
        item_id = self.item.currentData()
        rows: list[tuple[int, str]] = []
        current_id = None
        with session_scope(self._engine) as session:
            item = session.get(Item, item_id) if item_id is not None else None
            if item is not None:
                for revision in list_revisions(item):
                    label = revision.designation + (
                        " (current)" if revision.is_current else ""
                    )
                    rows.append((revision.revision_id, label))
                    if revision.is_current:
                        current_id = revision.revision_id

        self.revision.blockSignals(True)
        self.revision.clear()
        for revision_id, label in rows:
            self.revision.addItem(label, revision_id)
        wanted = None
        if keep is not None:
            wanted = self.revision.findText(keep, Qt.MatchFlag.MatchStartsWith)
        if wanted is None or wanted < 0:
            wanted = self.revision.findData(current_id)
        self.revision.setCurrentIndex(max(wanted, 0))
        self.revision.blockSignals(False)
        self.revision.setEnabled(bool(rows))

    def _revision_changed(self) -> None:
        """Смена ревизии **ничего не пересчитывает** (ратификация 11).

        Введённые локальные номера остаются как введены; меняется только то,
        против чего они читаются. Не перецеплять, не сбрасывать, не спрашивать —
        оператор набрал номера с бланка, и подставлять вместо них чужие значит
        терять его работу. Номер, которого в выбранной ревизии нет, честно
        получает пометку «not in this revision» — и оператор видит её **до**
        сохранения, потому что такой размер попадёт под автосоздание.
        """
        self._refresh_findings()

    def _refresh_findings(self) -> None:
        item_id = self.item.currentData()
        with session_scope(self._engine) as session:
            zones = {value.zone_id: value.name for value in session.query(RefZone)}
            kinds = {
                value.deviation_type_id: value.name for value in session.query(RefDeviationType)
            }
            # Пакетно, а не построчно: прежний `canon_state` открывал сессию на
            # каждую находку (`docs/specs/deviation-entry.md` §8, N+1).
            revision_id = self.revision.currentData()
            revision = (
                session.get(ItemRevision, revision_id) if revision_id is not None else None
            )
            canon = canon_labels_for_item(
                session, revision, [row.local_number for row in self._rows]
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
                outcome_label(row.outcome),
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
                    inspection.protocol,
                )
                for inspection in sorted(
                    deviation.inspections, key=lambda i: i.insp_number
                )
            ]
            # Ширину `Type` задаёт **справочник**, а не показанные строки; набор
            # передаёт экран, `kit` к базе не ходит (§1.1 наряда `0035`).
            inspection_types = [
                value.name for value in list_values(session, RefInspectionType)
            ]

        self.inspections.setRowCount(len(rows))
        for index, (inspection_id, number, local, kind, protocol) in enumerate(rows):
            cells = (iso(number), iso(local), kind, iso(protocol or ""))
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, inspection_id)
                self.inspections.setItem(index, column, cell)

        # Второе из двух мест с `kit.free()` (§0.4 наряда `0035`): без пересчёта
        # `Protocol` сидел на полу по заголовку, а `Type` — на пустом наборе.
        # Предел полотна `refit_columns` берёт у самой таблицы.
        kit.refit_columns(
            self.inspections,
            (
                INSPECTION_WIDTHS[0],
                INSPECTION_WIDTHS[1],
                kit.closed(inspection_types),
                INSPECTION_WIDTHS[3],
            ),
        )

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
        """Деталь заводится по ходу — штатный путь, а не исключение (§6).

        Привязка к канону идёт тем же продолжением, что и на экране деталей
        (наряд 0018 §3.2): здесь она особенно к месту — R2 требует, чтобы канон
        был привязан **до** регистрации отклонения, а мы как раз внутри неё.
        Откат привязки отменяет заведение, и тогда подставлять в список нечего.
        """
        # `parent=` именем, а не позицией: вторым параметром у формы стоит
        # `item_id`, и `ItemDialog(engine, self)` открывал её «на правку вида».
        dialog = ItemDialog(self._engine, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.created_number:
            return

        created = complete_new_item(
            self._engine, self, dialog.created_item_id, dialog.created_group_id
        )
        self.reload_items(preselect=dialog.created_number if created else None)
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
        dialog = FindingDialog(self._engine, self.item.currentData(), None, parent=self)
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
        dialog = FindingDialog(self._engine, self.item.currentData(), row, parent=self)
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
        # Тот же помощник, что на экране деталей: ранняя привязка (R2) — та же
        # работа, и молчать о незакрытых позициях ей незачем (§3.2).
        open_mapping(self._engine, self, item_id, cg_id)
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

                revision = session.get(ItemRevision, self.revision.currentData())
                if self._deviation_id is None:
                    deviation = register(session, item=item, revision=revision, **header)
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
                    session, deviation.revision, row.local_number
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
                    outcome=row.outcome,
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
                    outcome=row.outcome,
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
