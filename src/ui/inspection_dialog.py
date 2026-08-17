"""Диалог исследования — вид, вердикт, протокол; заводится на находке.

Отдельного раздела «Исследования» нет (решение Cowork 2): цель исследования —
конкретная находка, и выбор её руками из общего списка добавлял бы только шанс
промахнуться. Поэтому находка сюда **передаётся**, а не выбирается, и показана
в шапке только для сверки.

Вердикт `decision_insp` независим от решения по отклонению (`Inspection.md`) —
никакой связи между двумя списками здесь нет намеренно.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import DECISION_INSP, Finding, Inspection, RefInspectionType
from db.session import session_scope
from domain.inspections import create_inspection, update_inspection
from domain.reference import list_values

from .common import DECISION_INSP_LABELS, iso, russian_buttons, show_error


class InspectionDialog(QDialog):
    """Заведение и правка исследования на конкретной находке."""

    def __init__(
        self,
        engine: Engine,
        finding_id: int,
        inspection_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._finding_id = finding_id
        self._inspection_id = inspection_id
        self.setWindowTitle("Исследование" if inspection_id is None else "Правка исследования")
        self.resize(560, 260)

        self.finding_label = QLabel()
        self.finding_label.setWordWrap(True)

        self.kind = QComboBox()
        self.verdict = QComboBox()
        for code in DECISION_INSP:
            self.verdict.addItem(DECISION_INSP_LABELS[code], code)

        self.protocol = QLineEdit()
        self.protocol.setPlaceholderText(r"ссылка на документ, например \\srv\qa\SW-2026-14.docx")
        browse = QPushButton(iso("Выбрать файл…"))
        browse.clicked.connect(self.pick_protocol)

        protocol_row = QHBoxLayout()
        protocol_row.addWidget(self.protocol, 1)
        protocol_row.addWidget(browse)

        self.hint = QLabel(
            "Строка заводится только когда есть письменный переиспользуемый анализ; "
            "рутинная сверка с чертежом исследованием не является."
        )
        self.hint.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        russian_buttons(self.buttons)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Находка:", self.finding_label)
        form.addRow("Вид исследования:", self.kind)
        form.addRow("Вердикт:", self.verdict)
        form.addRow("Протокол:", protocol_row)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addWidget(self.buttons)

        self.reload()

    @classmethod
    def run(
        cls,
        engine: Engine,
        finding_id: int,
        inspection_id: int | None = None,
        parent: QWidget | None = None,
    ) -> bool:
        dialog = cls(engine, finding_id, inspection_id, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            finding = session.get(Finding, self._finding_id)
            self.finding_label.setText(
                iso(
                    f"{finding.deviation.dev_number} · "
                    f"{finding.deviation.item.item_number} · "
                    f"размер №{finding.characteristic.local_number}"
                )
            )

            self.kind.clear()
            for value in list_values(session, RefInspectionType):
                self.kind.addItem(value.name, value.inspection_type_id)

            if self._inspection_id is not None:
                inspection = session.get(Inspection, self._inspection_id)
                _select(self.kind, inspection.type_id)
                _select(self.verdict, inspection.decision_insp)
                self.protocol.setText(inspection.protocol)

    def pick_protocol(self) -> None:
        """Путь к протоколу вставляем строкой: файлы в базу не копируются."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Протокол исследования", "", "Все файлы (*)")
        if path:
            self.protocol.setText(path)

    def save(self) -> None:
        try:
            with session_scope(self._engine) as session:
                kind = session.get(RefInspectionType, self.kind.currentData())
                if self._inspection_id is None:
                    create_inspection(
                        session,
                        session.get(Finding, self._finding_id),
                        inspection_type=kind,
                        decision_insp=self.verdict.currentData(),
                        protocol=self.protocol.text(),
                    )
                else:
                    update_inspection(
                        session,
                        session.get(Inspection, self._inspection_id),
                        inspection_type=kind,
                        decision_insp=self.verdict.currentData(),
                        protocol=self.protocol.text(),
                    )
        except Exception as error:
            show_error(self, error, title="Исследование не сохранено")
            return
        self.accept()


def _select(combo: QComboBox, key) -> None:
    index = combo.findData(key)
    if index >= 0:
        combo.setCurrentIndex(index)
