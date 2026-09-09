"""Диалог находки: размер, направление, величина, зона и тип отклонения.

Правки **не пишутся в базу** — диалог отдаёт заполненную строку форме
отклонения, а та сохраняет всё одной транзакцией по «Сохранить» (наряд 0004).
Поэтому здесь нет ни сессии на запись, ни `make_finding`: единственная точка
создания находки — домен, и зовёт её форма.

Направление обязательно (заметка Б): `direction` NOT NULL, знак берётся из слова
max/min источника. Качественные признаки (`GO`, пин) живут в комментарии, но знак
оператор всё равно выбирает осознанно — умолчания у переключателя нет.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import OUTCOME, Direction, Item, RefDeviationType, RefZone
from db.session import session_scope
from domain.revisions import current_revision
from domain.errors import ValidationError
from domain.reference import list_values

from . import kit
from .cg_dialog import parse_optional_number
from .common import NO_OUTCOME_LABEL, OUTCOME_LABELS, iso
from .kit import tokens

NOT_SET = "— not set —"

#: Что показывать в колонке «канон» и в подсказке диалога.
#:
#: Состояния «нет у детали (99)» здесь нет и быть не может: код 99 отмечает
#: g-позицию, которой у детали **нет**, а находка всегда про размер, который у
#: детали **есть** — он же и отклонился. Расхождение с описанием колонки в
#: наряде вынесено в отчёт исполнителя.
CANON_UNBOUND = "not bound"
CANON_NEW = "not created yet"


@dataclass
class FindingRow:
    """Находка в форме отклонения; `finding_id=None` — ещё не в базе.

    Размер держим **номером**, а не характеристикой: до сохранения детали может
    не быть самой характеристики — её создаст домен при записи
    (`get_or_create_characteristic`, `_overview.md` §6).
    """

    local_number: str
    direction: str
    value: float | None = None
    dimension_point: int | None = None
    comment: str | None = None
    zone_id: int | None = None
    deviation_type_id: int | None = None
    finding_id: int | None = None
    #: Исследования находки — **сами записи**, а не их число (§3.2 наряда `0036`).
    #: Колонка `Inspections` показывает сводку, и на обоих экранах одну и ту же:
    #: кортеж колонок общий, `FindingsPanel` решением 4 реестра QMS-025 одна на
    #: оба экрана, и одно значение не имеет права выглядеть по-разному.
    #: Счётчик, где он нужен, берётся длиной.
    inspections: tuple = ()
    #: Исход находки: `permitted` · `not_permitted` · `None` («ещё не решали»).
    #: Пусто по умолчанию — нормальное состояние свежей регистрации: находки
    #: заводятся при регистрации, суждение приходит позже (`Finding.md` rev 1.01).
    outcome: str | None = None
    canon: str = field(default=CANON_NEW)


class FindingDialog(QDialog):
    """Форма находки. Результат — `row` после `exec() == Accepted`."""

    def __init__(
        self,
        engine: Engine,
        item_id: int | None,
        row: FindingRow | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self._source = row
        self.row: FindingRow | None = None
        self.setWindowTitle("Finding — deviation on a characteristic")
        self.resize(tokens.DIALOG_NARROW, tokens.DIALOG_HEIGHT_MEDIUM)

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText("local number from the item drawing, e.g. 12")
        self.number_edit.textChanged.connect(self._refresh_canon)

        # Умолчания у направления нет: оператор выбирает знак осознанно (заметка Б).
        self.plus = QRadioButton(iso("+  above maximum"))
        self.minus = QRadioButton(iso("−  below minimum"))

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("deviation value, e.g. 0,08")
        self.point_edit = QLineEdit()
        self.point_edit.setPlaceholderText("measurement point index (not used in search)")
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setPlaceholderText("qualitative marks: GO / מדיד, pin…")
        self.comment_edit.setFixedHeight(tokens.TEXT_AREA_HEIGHT)
        # Свободный текст, чаще всего ивритский. Хелпер здесь не нужен:
        # направление абзаца Qt резолвит по содержимому сам (ревью Р-2).

        self.zone = QComboBox()
        self.deviation_type = QComboBox()

        self.canon_label = QLabel()
        self.canon_label.setWordWrap(True)

        # Исход — **суждение по размеру**, и форма его не блокирует: любое из трёх
        # состояний законно в любой момент (`Finding.md` rev 1.01). Пустое стоит
        # вариантом на экране, а не отсутствием выбора: «ещё не решали» — это
        # нормальное состояние свежей регистрации, и оператор должен видеть его
        # словами, а не догадываться по пустоте.
        self.outcome = kit.Choice()
        self.outcome.add(None, NO_OUTCOME_LABEL)
        for code in OUTCOME:
            self.outcome.add(code, OUTCOME_LABELS[code])
        self.outcome.set_value(None)

        self.buttons = kit.dialog_buttons(accept="Add finding")
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        # Через `kit.column`, а не голым `QVBoxLayout`: у голого свои отступы
        # по умолчанию (9 со всех сторон, замерено), и они уводили радиокнопки
        # вправо от левого края остальных полей формы (находка №19).
        self.direction_box = kit.boxed(kit.column(self.plus, self.minus))

        form = kit.stretching_form()
        form.addRow("Local number:", self.number_edit)
        form.addRow("Canon mapping:", self.canon_label)
        form.addRow("Direction:", self.direction_box)
        form.addRow("Value:", self.value_edit)
        form.addRow("Measurement point:", self.point_edit)
        form.addRow("Zone:", self.zone)
        form.addRow("Deviation type:", self.deviation_type)
        form.addRow("Comment:", self.comment_edit)
        # Исход — последним: сперва вводят измеренное, потом судят о нём.
        form.addRow("Outcome:", self.outcome)

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        # Свободная вертикаль уходит **вниз**, а не в строки формы. Без этого
        # растягивались ровно те две строки, чьи виджеты умеют расти —
        # переносимая подпись канона и контейнер направления, — и содержимое
        # центрировалось в выросшей строке: подпись сверху, значение сильно
        # ниже (находка №19, замерено: 138 px против 28 у соседних полей).
        layout.addStretch(1)
        layout.addWidget(self.buttons)

        self._load_reference()
        if row is not None:
            self._fill_from(row)
        self._refresh_canon()

    # --- наполнение ------------------------------------------------------------

    def _load_reference(self) -> None:
        """Зона и тип отклонения — обычные словари, пустое значение допустимо."""
        with session_scope(self._engine) as session:
            zones = [(value.zone_id, value.name) for value in list_values(session, RefZone)]
            kinds = [
                (value.deviation_type_id, value.name)
                for value in list_values(session, RefDeviationType)
            ]

        for combo, rows in ((self.zone, zones), (self.deviation_type, kinds)):
            combo.clear()
            combo.addItem(NOT_SET, None)
            for key, name in rows:
                combo.addItem(name, key)

    def _fill_from(self, row: FindingRow) -> None:
        self.number_edit.setText(row.local_number)
        # Номер размера правке не подлежит: находка адресована конкретному
        # размеру, смена номера — это другая находка (домен её и не меняет).
        if row.finding_id is not None:
            self.number_edit.setReadOnly(True)
            self.number_edit.setToolTip(
                "The characteristic of a finding does not change: "
                "another characteristic means another finding."
            )
        self.plus.setChecked(row.direction == Direction.PLUS)
        self.minus.setChecked(row.direction == Direction.MINUS)
        self.value_edit.setText("" if row.value is None else f"{row.value:g}")
        self.point_edit.setText("" if row.dimension_point is None else str(row.dimension_point))
        self.comment_edit.setPlainText(row.comment or "")
        _select(self.zone, row.zone_id)
        _select(self.deviation_type, row.deviation_type_id)
        self.outcome.set_value(row.outcome)

    def _refresh_canon(self) -> None:
        """Показать состояние привязки размера к канону (`g5` / 99 / нет)."""
        self.canon_label.setText(iso(canon_state(self._engine, self._item_id, self.number_edit.text())))

    # --- сохранение ------------------------------------------------------------

    def save(self) -> None:
        try:
            local_number = self.number_edit.text().strip()
            if not local_number:
                raise ValidationError("Local number is required.")
            if not (self.plus.isChecked() or self.minus.isChecked()):
                raise ValidationError(
                    "Direction is required: the sign comes from the max/min wording "
                    "of the source."
                )

            row = FindingRow(
                local_number=local_number,
                direction=Direction.PLUS if self.plus.isChecked() else Direction.MINUS,
                value=parse_optional_number(self.value_edit.text(), "Value"),
                dimension_point=_parse_point(self.point_edit.text()),
                comment=self.comment_edit.toPlainText().strip() or None,
                zone_id=self.zone.currentData(),
                deviation_type_id=self.deviation_type.currentData(),
                # Правка возвращает ту же находку — иначе форма сочла бы её
                # новой, а прежнюю удалила вместе с её исследованиями.
                finding_id=self._source.finding_id if self._source else None,
                inspections=self._source.inspections if self._source else (),
                outcome=self.outcome.value(),
            )
        except Exception as error:
            kit.show_error(self, error, title="Finding not accepted")
            return

        row.canon = canon_state(self._engine, self._item_id, row.local_number)
        self.row = row
        self.accept()


def canon_state(engine: Engine, item_id: int | None, local_number: str) -> str:
    """Состояние размера в каноне: `g5`, «нет у детали (99)» или «не привязан».

    Читается из готового канон-слоя S3 — маппинга и таблицы кода 99; ничего
    своего про канон здесь не считается.
    """
    local_number = (local_number or "").strip()
    if item_id is None or not local_number:
        return CANON_NEW

    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        if item is None:
            return CANON_NEW
        revision = current_revision(item)
        if revision is None:
            return CANON_NEW
        characteristic = next(
            (
                c
                for c in current_revision(item).characteristics
                if c.local_number == local_number
            ),
            None,
        )
        if characteristic is None:
            return CANON_NEW
        mapping = characteristic.mapping
        if mapping is not None:
            return f"g{mapping.g_position.g_index}"
        # Размер есть, привязки нет — «нет у детали» относится к позиции, а не к
        # размеру, поэтому здесь это именно «не привязан».
        return CANON_UNBOUND


def _parse_point(text: str) -> int | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if not cleaned.isdigit():
        raise ValidationError(f"Measurement point: “{cleaned}” is not a whole number.")
    return int(cleaned)


def _select(combo: QComboBox, key: int | None) -> None:
    index = combo.findData(key)
    combo.setCurrentIndex(index if index >= 0 else 0)
