"""Диалог решения по отклонению — шаг 8 процесса, отдельное действие.

Решение внесено **не** формой регистрации намеренно (решение Cowork 1): исход
принимается после изучения прецедентов (шаг 6) и исследований (шаг 7), а форма,
предлагающая выбрать его при регистрации, толкала бы решить раньше времени.

Виджет самостоятельный: в S5 он переезжает в карточку отклонения как есть,
поэтому ничего от раздела «Отклонения» не знает — только движок и id записи.

Пишет по «Сохранить» одной транзакцией, поэтому подписи кнопок обычные
(конвенция S3: «Готово»/«Закрыть» — только там, где пишут по действию).
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)
from sqlalchemy import Engine

from db.models import DECISION_DEV, Deviation
from db.session import session_scope
from domain.deviations import set_decision

from . import kit
from .common import DECISION_DEV_LABELS, joined, numeric_field
from .kit import tokens

NOT_DECIDED = "— no decision yet —"

#: Что означает каждый исход — строкой под ним. Формулировка исхода отвечает
#: «что сделано с деталями», а строка ниже — «что из этого следует»: инженер
#: выбирает, читая, а не вспоминая (канон §4).
OUTCOME_NOTES = {
    "approved": "the parts are used as they are; the explanation goes into אישור חריגה",
    "rejected": "the parts are scrapped; nothing is issued",
    "sorting": "every part of the batch is inspected, and the batch splits by the result",
    "repair": "the parts are reworked, and the deviation is legalised by the record",
}


class DecisionDialog(QDialog):
    """Внесение и смена решения. `True` из `run` — решение записано."""

    def __init__(self, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._deviation_id = deviation_id
        self.setWindowTitle("Deviation decision")
        self.resize(tokens.DIALOG_NARROW, tokens.DIALOG_HEIGHT_MEDIUM)

        # Четыре взаимоисключающих исхода, которые выбирают **читая
        # формулировки**, — радиокнопки (канон §4). Ничего не предвыбрано:
        # предвыбранный исход это решение, которого инженер не принимал, а
        # одобрение порождает документ.
        self.decision = kit.Choice()
        for code in DECISION_DEV:
            self.decision.add(code, DECISION_DEV_LABELS[code], OUTCOME_NOTES[code])
        for button in self.decision.buttons():
            button.toggled.connect(self._refresh_hint)

        self.explanation = QPlainTextEdit()
        self.explanation.setPlaceholderText(
            "explanation — on approval it goes into אישור חריגה"
        )
        # Обоснование пишут и на иврите, и по-английски. Хелпер не нужен:
        # текстовой области Qt резолвит направление по абзацу (ревью Р-2).
        self.ncr = QLineEdit()
        self.ncr.setPlaceholderText("NCR number (may arrive after the decision)")
        self.decision_date = numeric_field(QDateEdit())
        self.decision_date.setCalendarPopup(True)
        self.decision_date.setDisplayFormat("dd.MM.yyyy")

        self.header = QLabel()
        self.hint = kit.hint()

        self.buttons = kit.dialog_buttons(accept="Save decision")
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = kit.stretching_form()
        form.addRow("Deviation:", self.header)
        form.addRow("Outcome:", self.decision)
        form.addRow("Explanation:", self.explanation)
        form.addRow("NCR:", self.ncr)
        form.addRow("Decision date:", self.decision_date)

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addWidget(self.buttons)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, deviation_id: int, parent: QWidget | None = None) -> bool:
        """Открыть решение по отклонению; `True` — решение записано."""
        dialog = cls(engine, deviation_id, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            deviation = session.get(Deviation, self._deviation_id)
            self.header.setText(
                joined(
                    deviation.dev_number,
                    deviation.item.item_number,
                    f"WO {deviation.wo}",
                )
            )
            if deviation.decision_dev is not None:
                self.decision.set_value(deviation.decision_dev)
            self.explanation.setPlainText(deviation.explanation or "")
            self.ncr.setText(deviation.ncr or "")
            stamp = deviation.decision_date or datetime.now()
            self.decision_date.setDate(QDate(stamp.year, stamp.month, stamp.day))
        self._refresh_hint()

    def _refresh_hint(self, *_args) -> None:
        """Правило одобрения показываем до нажатия, а не только в ошибке."""
        if self.decision.value() == "approved":
            self.hint.setText(
                "Approval requires an explanation: the text goes into "
                "אישור חריגה (DS-QC.2-2)."
            )
        else:
            self.hint.setText(
                "The inspection result does not drive the outcome — the engineer decides."
            )

    def save(self) -> None:
        decision = self.decision.value()
        if decision is None:
            kit.show_error(self, _not_chosen(), title="Decision not saved")
            return

        chosen = self.decision_date.date()
        try:
            with session_scope(self._engine) as session:
                deviation = session.get(Deviation, self._deviation_id)
                set_decision(
                    session,
                    deviation,
                    decision=decision,
                    explanation=self.explanation.toPlainText(),
                    ncr=self.ncr.text(),
                    decision_date=_stamp(chosen),
                )
        except Exception as error:
            kit.show_error(self, error, title="Decision not saved")
            return
        self.accept()


def _stamp(chosen: QDate) -> datetime:
    """Дата из календаря + текущее время.

    Оператор выбирает день, а не секунду; время берём системное, чтобы порядок
    решений внутри дня оставался различимым.
    """
    now = datetime.now()
    return datetime(
        chosen.year(), chosen.month(), chosen.day(), now.hour, now.minute, now.second
    )


def _not_chosen() -> Exception:
    from domain.errors import ValidationError

    return ValidationError("Pick an outcome from the list — that is the decision.")
