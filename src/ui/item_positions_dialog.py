"""Позиции детали — раскрытие числа в колонке `Characteristics` (решение В-7).

**Диалог, а не сплиттер**, и на то четыре довода, из которых первый решает:
самый богатый детальный вид приложения — карточка отклонения — сделан
отдельным окном (ратификация S5), и мастер-деталь на экране деталей поставил бы
два несовместимых образца показа вложенного в одном приложении. Сплиттер
вдобавок платит вертикалью, которой нет, и заводит состояние (положение
разделителя, перезагрузка панели), а наряд 0011 масштабирует язык, не механики.

Только чтение. Состав колонок — как у таблицы позиций в форме новой детали:
`g-position` · `Local number` · `Nominal` · `Tolerance`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QTableWidgetItem, QWidget
from sqlalchemy import Engine

from db.models import Item
from db.session import session_scope
from domain.precedents import canon_labels

from . import kit
from .common import dimension_sort_key, iso, tolerance_label
from .kit import tokens

COLUMNS = ("g-position", "Local number", "Nominal", "Tolerance", "State")

#: Индекс позиции и номер размера — идентификаторы: направление им объявляем,
#: но влево. Вправо только номинал и допуск — их сравнивают по величине.
NUMERIC_COLUMNS = (0, 1)
MAGNITUDE_COLUMNS = (2, 3)

#: Состояние привязки — своей колонкой (макет S6). Прежде оно подменяло собой
#: индекс позиции: у непривязанного размера в колонке `g-position` стояло «not
#: bound», то есть колонка отвечала то на «какая позиция», то на «привязан ли».
STATE_BOUND = "bound"
STATE_UNBOUND = "not bound"

#: Позиции у непривязанного размера нет — прочерк, а не пустая ячейка.
NO_POSITION = "—"

EMPTY_TITLE = "This item has no characteristics yet"
EMPTY_BODY = (
    "Characteristics appear either with the item form — seeded from a "
    "characteristic group — or on their own, when a finding names a number "
    "that does not exist yet."
)


class ItemPositionsDialog(QDialog):
    """Размеры детали и их привязка к канону. Ничего не правит."""

    def __init__(self, engine: Engine, item_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self.resize(tokens.DIALOG_MEDIUM, tokens.DIALOG_HEIGHT_MEDIUM)

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
        )
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)
        self.status = kit.status_label()

        self.buttons = kit.dialog_buttons(accept="Close", reject="Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        # Диалог ничего не пишет, отменять нечего — остаётся один выход.
        self.buttons.button(self.buttons.StandardButton.Cancel).setVisible(False)

        layout = kit.dialog_layout(self)
        layout.addWidget(
            kit.hint(
                "Read only. Nominal and tolerance come from the canonical "
                "position; the local number is what the item drawing calls it."
            )
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, item_id: int, parent: QWidget | None = None) -> None:
        cls(engine, item_id, parent).exec()

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            self.setWindowTitle(f"Item positions — {item.item_number}")
            characteristics = sorted(
                item.characteristics, key=lambda c: dimension_sort_key(c.local_number)
            )
            labels = canon_labels(session, characteristics)
            # Каждая ячейка — атомарный токен и **ровно один** изолят на него
            # (канон §6): `tolerance_label` изолирует сама, поэтому второй раз
            # её оборачивать нельзя.
            rows = [
                (
                    iso(_g_label(labels, characteristic)),
                    iso(characteristic.local_number),
                    iso(_number(_position(characteristic, "nominal"))),
                    tolerance_label(
                        _position(characteristic, "tol_plus"),
                        _position(characteristic, "tol_minus"),
                    ),
                    STATE_BOUND if characteristic.mapping is not None else STATE_UNBOUND,
                )
                for characteristic in characteristics
            ]

        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

        bound = sum(1 for row in rows if row[4] == STATE_BOUND)
        self.status.setText(
            f"Characteristics: {len(rows)} · bound to the canon: {bound}. "
            "Binding is what finds the same design node on other items."
        )


def _g_label(labels: dict, characteristic) -> str:
    """Индекс позиции; у непривязанного размера позиции нет — прочерк."""
    if characteristic.mapping is None:
        return NO_POSITION
    return labels.get(characteristic.characteristic_id, NO_POSITION)


def _position(characteristic, attribute: str):
    """Значение канонической позиции размера; `None` — размер не привязан."""
    mapping = characteristic.mapping
    if mapping is None:
        return None
    return getattr(mapping.g_position, attribute)


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:g}"

