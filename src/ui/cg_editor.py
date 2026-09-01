"""Визуальный редактор группы характеристик: баллоны поверх чертежа.

Правки копятся в форме и уходят в базу одной транзакцией по «Сохранить»
(наряд 0003). Исключение — удаление позиции: занятость проверяется сразу при
нажатии, чтобы оператор узнал о блокировке на месте, а не после сохранения.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLineEdit,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, select

from db.models import CharacteristicGroup, GPosition
from db.session import session_scope
from domain.errors import ValidationError
from domain.groups import (
    GPositionSpec,
    add_position,
    position_usage,
    remove_position,
    set_drawing,
    update_group,
    update_position,
)

from . import kit
from .balloon_canvas import MODE_EDIT, Balloon, BalloonCanvas
from .cg_dialog import parse_optional_number
from .common import iso
from .kit import tokens

COLUMNS = ("g-position", "Nominal", "Tolerance +", "Tolerance −")

#: Индекс позиции — идентификатор, влево; вправо только величины.
NUMERIC_COLUMNS = (0,)
MAGNITUDE_COLUMNS = (1, 2, 3)


@dataclass
class _Row:
    """Строка правки: `position_id=None` — позиция ещё не в базе."""

    g_index: int
    nominal: float | None = None
    tol_plus: float | None = None
    tol_minus: float | None = None
    x: float | None = None
    y: float | None = None
    position_id: int | None = None


class CgEditor(QDialog):
    """Редактор группы. Возвращает `True` из `exec()`, если что-то сохранено."""

    def __init__(self, engine: Engine, cg_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._cg_id = cg_id
        self._rows: list[_Row] = []
        self._drawing: bytes | None = None
        self._drawing_name: str | None = None
        self._drawing_changed = False
        self.setWindowTitle("Characteristic group editor")
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_MEDIUM)

        self.name_edit = QLineEdit()
        self.canvas = BalloonCanvas(MODE_EDIT)
        self.canvas.balloonMoved.connect(self._on_moved)

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
            read_only=False,
        )
        self.table.currentCellChanged.connect(
            lambda row, *_: self.canvas.select(self._rows[row].g_index if 0 <= row < len(self._rows) else None)
        )

        load_drawing = kit.secondary("Load drawing…")
        drop_drawing = kit.secondary("Remove drawing")
        add_row = kit.secondary("Add position")
        drop_row = kit.secondary("Remove position")
        load_drawing.clicked.connect(self.load_drawing)
        drop_drawing.clicked.connect(self.drop_drawing)
        add_row.clicked.connect(self.add_position)
        drop_row.clicked.connect(self.remove_position)

        self.status = kit.status_label()

        self.buttons = kit.dialog_buttons()
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        drawing_buttons = kit.button_row(load_drawing, drop_drawing)
        row_buttons = kit.button_row(add_row, drop_row)

        form = kit.stretching_form()
        form.addRow("Group name:", self.name_edit)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addLayout(form)
        side_layout.addLayout(drawing_buttons)
        side_layout.addWidget(
            kit.hint(
                "Positions — nominal and tolerance come from the drawing. "
                "The index of an existing position never changes, and a new one "
                "is issued as max + 1."
            )
        )
        side_layout.addWidget(self.table, 1)
        side_layout.addLayout(row_buttons)
        side_layout.addWidget(self.status)

        splitter = QSplitter()
        splitter.addWidget(self.canvas)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        # Панель геометрии не уже своей таблицы: при делении пополам подписи
        # колонок обрезались до «-positio», и оператор читал не их, а догадку.
        splitter.setSizes([tokens.DIALOG_MEDIUM, tokens.DIALOG_NARROW])

        layout = kit.dialog_layout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.buttons)

        self.reload()

    # --- загрузка / отрисовка --------------------------------------------------

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            group = session.get(CharacteristicGroup, self._cg_id)
            self.name_edit.setText(group.name)
            self._drawing = group.drawing
            self._drawing_name = group.drawing_name
            self._rows = [
                _Row(
                    g_index=position.g_index,
                    nominal=position.nominal,
                    tol_plus=position.tol_plus,
                    tol_minus=position.tol_minus,
                    x=position.x,
                    y=position.y,
                    position_id=position.g_position_id,
                )
                for position in sorted(group.positions, key=lambda p: p.g_index)
            ]
        self._drawing_changed = False
        self._refresh()

    def _refresh(self) -> None:
        if not self.canvas.set_drawing(self._drawing):
            self.status.setText("The drawing could not be displayed — is the file damaged?")

        self.canvas.set_balloons(
            [Balloon(g_index=row.g_index, x=row.x, y=row.y) for row in self._rows]
        )

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            self.table.setItem(index, 0, _index_cell(row))
            self.table.setItem(index, 1, QTableWidgetItem(_text(row.nominal)))
            self.table.setItem(index, 2, QTableWidgetItem(_text(row.tol_plus)))
            self.table.setItem(index, 3, QTableWidgetItem(_text(row.tol_minus)))
        self.table.blockSignals(False)

        placed = sum(1 for row in self._rows if row.x is not None)
        self.status.setText(
            f"Positions: {len(self._rows)} · placed on the drawing: {placed}. "
            "Drag the balloons with the mouse; coordinates are stored on Save."
        )

    def _on_moved(self, g_index: int, x: float, y: float) -> None:
        for row in self._rows:
            if row.g_index == g_index:
                row.x, row.y = x, y
                break

    # --- действия --------------------------------------------------------------

    def load_drawing(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Group drawing", "", "Images (*.png *.jpg *.jpeg);;All files (*)"
        )
        if not path:
            return
        try:
            data = open(path, "rb").read()
        except OSError as error:
            kit.show_error(self, error, title="File not read")
            return

        self._drawing, self._drawing_name = data, path.rsplit("/", 1)[-1]
        self._drawing_changed = True
        # Координаты баллонов не сбрасываем (заметка Б): оператор поправит их сам.
        self._refresh()

    def drop_drawing(self) -> None:
        self._drawing, self._drawing_name = None, None
        self._drawing_changed = True
        self._refresh()

    def add_position(self) -> None:
        next_index = max((row.g_index for row in self._rows), default=0) + 1
        self._rows.append(_Row(g_index=next_index, x=0.5, y=0.5))
        self._refresh()

    def remove_position(self) -> None:
        current = self.table.currentRow()
        if not 0 <= current < len(self._rows):
            self.status.setText("Select a position in the table first.")
            return

        row = self._rows[current]
        if row.position_id is not None:
            # Занятость проверяем сразу — блокировка не должна всплыть при сохранении.
            try:
                with session_scope(self._engine) as session:
                    position = session.get(GPosition, row.position_id)
                    used = position_usage(session, position)
                    if used:
                        raise _in_use(position.g_index, used)
            except Exception as error:
                kit.show_error(self, error, title="Position in use")
                return

        self._rows.pop(current)
        self._refresh()

    def _collect(self) -> list[_Row]:
        """Забрать правки геометрии из таблицы.

        Индекс из таблицы не читается вовсе (ратификация В-8): у существующей
        позиции он неизменен, у новой выдан формой как `max + 1`. Ячейка закрыта
        в обоих случаях, и взять оттуда можно было бы только то же значение.
        """
        rows: list[_Row] = []
        for index, row in enumerate(self._rows):
            g_index = row.g_index

            def cell(column: int) -> str:
                item = self.table.item(index, column)
                return item.text() if item else ""

            rows.append(
                _Row(
                    g_index=g_index,
                    nominal=parse_optional_number(cell(1), f"Row {index + 1}, nominal"),
                    tol_plus=parse_optional_number(cell(2), f"Row {index + 1}, tolerance +"),
                    tol_minus=parse_optional_number(cell(3), f"Row {index + 1}, tolerance −"),
                    x=row.x,
                    y=row.y,
                    position_id=row.position_id,
                )
            )
        indexes = [row.g_index for row in rows]
        if len(set(indexes)) != len(indexes):
            raise ValidationError("The g-position indexes inside a group must not repeat.")
        return rows

    def save(self) -> None:
        try:
            rows = self._collect()
            with session_scope(self._engine) as session:
                group = session.get(CharacteristicGroup, self._cg_id)
                update_group(session, group, name=self.name_edit.text())

                if self._drawing_changed:
                    set_drawing(session, group, self._drawing, self._drawing_name)

                kept = {row.position_id for row in rows if row.position_id is not None}
                for position in list(group.positions):
                    if position.g_position_id not in kept:
                        remove_position(session, position)

                for row in rows:
                    if row.position_id is None:
                        add_position(
                            session,
                            group,
                            GPositionSpec(row.g_index, row.nominal, row.tol_plus, row.tol_minus, row.x, row.y),
                        )
                    else:
                        position = session.get(GPosition, row.position_id)
                        update_position(
                            session,
                            position,
                            nominal=row.nominal,
                            tol_plus=row.tol_plus,
                            tol_minus=row.tol_minus,
                            x=row.x,
                            y=row.y,
                        )
        except Exception as error:
            kit.show_error(self, error, title="Group not saved")
            return
        self.accept()


def _index_cell(row: _Row) -> QTableWidgetItem:
    """Ячейка индекса — только чтение, и у новой позиции тоже (В-8).

    Индекс g-позиции — идентичность, на которую ссылаются привязки всех деталей
    (`domain.groups.update_position`). Перенумеровать её в форме значило бы
    переклеить ярлыки под готовыми привязками. У новой строки индекс тоже не
    вводится: он выдаётся как `max + 1` и не переиспользуется — `g5` живёт не
    только в таблице, а ещё на чертеже и в протоколе контроля.
    """
    cell = QTableWidgetItem(str(row.g_index))
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    cell.setToolTip(
        "The g-position index is issued as max + 1 and never changes: "
        "characteristic mappings and the drawing point at it."
    )
    return cell


def _text(value: float | None) -> str:
    """Число для ячейки: в изоляте, иначе ведущий минус в RTL уезжает в хвост."""
    return "" if value is None else iso(f"{value:g}")


def _in_use(g_index: int, used: int) -> Exception:
    from domain.errors import ValueInUse

    return ValueInUse(
        f"Position g{g_index} is used by {used} records "
        "(characteristic mappings or “absent from item” marks) — clear them first."
    )
