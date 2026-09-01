"""Диалог привязки размеров детали к g-позициям — переиспользуемый.

Поведение по Session-03 §4: клик по баллону → ввод локального номера размера →
баллон ярко-зелёный; «нет у детали (99)» красит баллон серым; **«Готово»
активна только когда каждый баллон получил состояние**.

Каждое действие уходит в базу сразу — случайно закрытое окно не теряет уже
введённое. Поэтому кнопки называются «Готово» / «Закрыть», а не
«Сохранить» / «Отмена»: откатывать сеанс привязки нечем.

Точка вызова из другого кода — `MappingDialog.run(engine, item_id, cg_id, parent)`;
на неё S4 повесит «ранние кнопки» формы ввода отклонения (R2: канон-привязка
делается до регистрации отклонения).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import CharacteristicGroup, GPosition, Item
from db.session import session_scope
from domain.mappings import bind, binding_state, clear, is_complete, mark_absent

from . import kit
from .balloon_canvas import MODE_SELECT, Balloon, BalloonCanvas
from .common import canon_geometry_label, iso
from .kit import tokens

COLUMNS = ("Position", "State", "Local number", "Canon geometry")

#: Индекс позиции, номер размера и геометрия — направление объявлено, потому что
#: сильных символов в них нет (канон §6).
#:
#: Выравнивание у всех трёх **левое**, включая геометрию. Канон §6 отправляет
#: вправо `Nominal` и `Tolerance ±` — там, где они стоят **отдельными** колонками
#: и сравниваются по величине вниз по столбцу. Здесь это одна составная ячейка:
#: сравнивают в ней номинал, а он у левого края токена — правый край держал бы в
#: столбик хвост допуска, то есть не то, на что смотрят.
NUMERIC_COLUMNS = (0, 2, 3)

STATE_LABELS = {
    "linked": "bound",
    "absent": "absent from item (99)",
    "none": "not decided",
}


class MappingDialog(QDialog):
    """Привязка детали к канону. Пишет в базу сразу по действию оператора."""

    def __init__(
        self, engine: Engine, item_id: int, cg_id: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self._cg_id = cg_id
        self._states: list = []
        # Шире прежнего: с колонкой геометрии (В-6) таблица перестала помещаться
        # в панель — подписи колонок обрезались, а ячейки переносились в две
        # строки. Чертёж при этом не ужимается: он остаётся тем, по чему
        # оператор узнаёт позицию.
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_MEDIUM)

        self.canvas = BalloonCanvas(MODE_SELECT)
        self.canvas.balloonClicked.connect(self._on_balloon)

        self.table = kit.data_table(COLUMNS, numeric_columns=NUMERIC_COLUMNS)
        self.table.currentCellChanged.connect(self._on_row)
        #: Геометрия позиции по её индексу — заполняется вместе с состояниями.
        self._geometry: dict[int, tuple] = {}

        self.bind_button = kit.primary("Set local number…")
        self.absent_button = kit.secondary("Absent from item (99)")
        self.clear_button = kit.secondary("Clear")
        self.bind_button.clicked.connect(lambda: self._on_balloon(self._current_index()))
        self.absent_button.clicked.connect(self.mark_absent)
        self.clear_button.clicked.connect(self.clear_position)

        self.status = kit.status_label()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        # Диалог пишет каждое действие в базу сразу, поэтому «Сохранить»/«Отмена»
        # врали бы: откатывать нечего. «Готово» лишь подтверждает, что все позиции
        # получили состояние (потому и включается по полноте), «Закрыть» — уход.
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Done")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Close")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        actions = kit.button_row(
            self.bind_button, self.absent_button, self.clear_button
        )

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.table, 1)
        side_layout.addLayout(actions)
        side_layout.addWidget(self.status)

        splitter = QSplitter()
        splitter.addWidget(self.canvas)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([tokens.DIALOG_MEDIUM, tokens.DIALOG_NARROW])

        layout = kit.dialog_layout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.buttons)

        self.reload()

    # --- публичный вход --------------------------------------------------------

    @classmethod
    def run(
        cls, engine: Engine, item_id: int, cg_id: int, parent: QWidget | None = None
    ) -> bool:
        """Открыть привязку детали к группе; `True` — оператор нажал «Сохранить».

        Публичная точка вызова: раздел «Группы характеристик», карточка детали и
        (в S4) «ранние кнопки» формы ввода отклонения зовут именно её.
        """
        dialog = cls(engine, item_id, cg_id, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    # --- отрисовка -------------------------------------------------------------

    def reload(self) -> None:
        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            group = session.get(CharacteristicGroup, self._cg_id)
            self.setWindowTitle(f"Mapping — {item.item_number} · {group.name}")
            drawing = group.drawing
            self._states = binding_state(session, item, group)
            # Координаты и геометрию берём из той же коллекции, которую уже
            # обошёл `binding_state`: новых запросов не нужно, а прежний
            # `_coordinates` открывал вторую сессию ради тех же строк.
            positions = sorted(group.positions, key=lambda p: p.g_index)
            coordinates = [(position.x, position.y) for position in positions]
            self._geometry = {
                position.g_index: (
                    position.nominal,
                    position.tol_plus,
                    position.tol_minus,
                )
                for position in positions
            }

        self.canvas.set_drawing(drawing)
        self.canvas.set_balloons(
            [
                Balloon(
                    g_index=state.g_index,
                    x=position_x,
                    y=position_y,
                    state=state.state,
                    label=state.local_number,
                )
                for state, (position_x, position_y) in zip(self._states, coordinates)
            ]
        )

        self.table.setRowCount(len(self._states))
        for row, state in enumerate(self._states):
            self.table.setItem(row, 0, QTableWidgetItem(iso(f"g{state.g_index}")))
            self.table.setItem(row, 1, QTableWidgetItem(STATE_LABELS[state.state]))
            self.table.setItem(row, 2, QTableWidgetItem(state.local_number or ""))
            self.table.setItem(row, 3, QTableWidgetItem(self._canon_cell(state.g_index)))

        complete = is_complete(self._states)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(complete)
        undecided = [f"g{s.g_index}" for s in self._states if not s.is_decided]
        self.status.setText(
            "Every position has a state — the mapping can be finished."
            if complete
            else "Awaiting a decision: " + ", ".join(iso(name) for name in undecided)
        )

    def _canon_cell(self, g_index: int) -> str:
        """Номинал и допуск позиции — то, **по чему** оператор решает (В-6).

        Привязка — момент, когда он сопоставляет баллон на чертеже с локальным
        номером детали; без геометрии канона это выбор вслепую, а отправлять за
        числом в соседний диалог хуже, чем показать его здесь. Дублирование
        показа не грех; грех — дублирование источника, а источник один.
        """
        nominal, plus, minus = self._geometry.get(g_index, (None, None, None))
        return canon_geometry_label(nominal, plus, minus)

    # --- действия --------------------------------------------------------------

    def _current_index(self) -> int | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._states):
            return self._states[row].g_index
        return self.canvas.selected

    def _state_of(self, g_index: int):
        return next(state for state in self._states if state.g_index == g_index)

    def _on_row(self, row: int, *_args) -> None:
        if 0 <= row < len(self._states):
            self.canvas.select(self._states[row].g_index)

    def _on_balloon(self, g_index: int | None) -> None:
        """Клик по баллону — ввод локального номера размера (§4)."""
        if g_index is None:
            self.status.setText("Select a position first.")
            return
        self._sync_row(g_index)
        state = self._state_of(g_index)

        number, accepted = QInputDialog.getText(
            self,
            f"Position g{g_index}",
            "Item local number (from the drawing):",
            text=state.local_number or "",
        )
        if not accepted:
            return
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                bind(session, item, position, number)
        except Exception as error:
            kit.show_error(self, error, title="Not bound")
            return
        self.reload()

    def mark_absent(self) -> None:
        g_index = self._current_index()
        if g_index is None:
            self.status.setText("Select a position first.")
            return
        state = self._state_of(g_index)
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                mark_absent(session, item, position)
        except Exception as error:
            kit.show_error(self, error, title="Not marked")
            return
        self.reload()

    def clear_position(self) -> None:
        g_index = self._current_index()
        if g_index is None:
            self.status.setText("Select a position first.")
            return
        state = self._state_of(g_index)
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                clear(session, item, position)
        except Exception as error:
            kit.show_error(self, error, title="Not cleared")
            return
        self.reload()

    def _sync_row(self, g_index: int) -> None:
        for row, state in enumerate(self._states):
            if state.g_index == g_index:
                self.table.setCurrentCell(row, 0)
                return
