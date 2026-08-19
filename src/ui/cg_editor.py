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
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
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

from .balloon_canvas import MODE_EDIT, Balloon, BalloonCanvas
from .cg_dialog import parse_optional_number
from .common import directional, iso, show_error, strip_iso

COLUMNS = ("g-position", "Nominal", "Tolerance +", "Tolerance −")


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
        self.resize(980, 620)

        self.name_edit = QLineEdit()
        self.canvas = BalloonCanvas(MODE_EDIT)
        self.canvas.balloonMoved.connect(self._on_moved)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.currentCellChanged.connect(
            lambda row, *_: self.canvas.select(self._rows[row].g_index if 0 <= row < len(self._rows) else None)
        )

        directional(self.table, numeric_columns=(0,), magnitude_columns=(1, 2, 3))

        load_drawing = QPushButton(iso("Load drawing…"))
        drop_drawing = QPushButton("Remove drawing")
        add_row = QPushButton("Add position")
        drop_row = QPushButton("Remove position")
        load_drawing.clicked.connect(self.load_drawing)
        drop_drawing.clicked.connect(self.drop_drawing)
        add_row.clicked.connect(self.add_position)
        drop_row.clicked.connect(self.remove_position)

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        drawing_buttons = QHBoxLayout()
        drawing_buttons.addWidget(load_drawing)
        drawing_buttons.addWidget(drop_drawing)
        drawing_buttons.addStretch(1)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_row)
        row_buttons.addWidget(drop_row)
        row_buttons.addStretch(1)

        form = QFormLayout()
        form.addRow("Group name:", self.name_edit)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addLayout(form)
        side_layout.addLayout(drawing_buttons)
        side_layout.addWidget(QLabel("Positions (nominal and tolerance come from the drawing):"))
        side_layout.addWidget(self.table, 1)
        side_layout.addLayout(row_buttons)
        side_layout.addWidget(self.status)

        splitter = QSplitter()
        splitter.addWidget(self.canvas)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)

        layout = QVBoxLayout(self)
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
            show_error(self, error, title="File not read")
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
                show_error(self, error, title="Position in use")
                return

        self._rows.pop(current)
        self._refresh()

    def _collect(self) -> list[_Row]:
        """Забрать правки геометрии из таблицы."""
        rows: list[_Row] = []
        for index, row in enumerate(self._rows):
            if row.position_id is None:
                # Индекс редактируется только у новой позиции — у существующей
                # ячейка закрыта (`_index_cell`), и её значение берём из модели.
                raw_index = strip_iso(
                    self.table.item(index, 0).text() if self.table.item(index, 0) else ""
                ).strip()
                if not raw_index.isdigit() or int(raw_index) < 1:
                    raise ValidationError(
                        f"Row {index + 1}: the position index must be a number ≥ 1."
                    )
                g_index = int(raw_index)
            else:
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
            show_error(self, error, title="Group not saved")
            return
        self.accept()


def _index_cell(row: _Row) -> QTableWidgetItem:
    """Ячейка индекса: у существующей позиции — только чтение.

    Индекс g-позиции — идентичность, на которую ссылаются привязки всех деталей
    (`domain.groups.update_position`). Перенумеровать её в форме значило бы
    переклеить ярлыки под готовыми привязками; у новой строки индекс ещё ничей,
    поэтому она остаётся редактируемой.
    """
    cell = QTableWidgetItem(str(row.g_index))
    if row.position_id is not None:
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cell.setToolTip(
            "The position number cannot be changed: characteristic mappings point at it. "
            "Need another number — add a position and drop the old one."
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
