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
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from db.models import CharacteristicGroup, GPosition, Item
from db.session import session_scope
from domain.mappings import bind, binding_state, clear, is_complete, mark_absent

from .balloon_canvas import MODE_SELECT, Balloon, BalloonCanvas
from .common import iso, russian_buttons, show_error

COLUMNS = ("Позиция", "Состояние", "Номер размера")

STATE_LABELS = {
    "linked": "привязан",
    "absent": "нет у детали (99)",
    "none": "не рассмотрено",
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
        self.resize(940, 600)

        self.canvas = BalloonCanvas(MODE_SELECT)
        self.canvas.balloonClicked.connect(self._on_balloon)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_row)

        self.bind_button = QPushButton(iso("Указать номер размера…"))
        self.absent_button = QPushButton("Нет у детали (99)")
        self.clear_button = QPushButton("Очистить")
        self.bind_button.clicked.connect(lambda: self._on_balloon(self._current_index()))
        self.absent_button.clicked.connect(self.mark_absent)
        self.clear_button.clicked.connect(self.clear_position)

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        russian_buttons(self.buttons)
        # Диалог пишет каждое действие в базу сразу, поэтому «Сохранить»/«Отмена»
        # врали бы: откатывать нечего. «Готово» лишь подтверждает, что все позиции
        # получили состояние (потому и включается по полноте), «Закрыть» — уход.
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Готово")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Закрыть")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(self.bind_button)
        actions.addWidget(self.absent_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)

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

        layout = QVBoxLayout(self)
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
            self.setWindowTitle(f"Привязка к канону — {item.item_number} · {group.name}")
            drawing = group.drawing
            self._states = binding_state(session, item, group)

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
                for state, (position_x, position_y) in zip(self._states, self._coordinates())
            ]
        )

        self.table.setRowCount(len(self._states))
        for row, state in enumerate(self._states):
            self.table.setItem(row, 0, QTableWidgetItem(iso(f"g{state.g_index}")))
            self.table.setItem(row, 1, QTableWidgetItem(STATE_LABELS[state.state]))
            self.table.setItem(row, 2, QTableWidgetItem(state.local_number or ""))

        complete = is_complete(self._states)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(complete)
        undecided = [f"g{s.g_index}" for s in self._states if not s.is_decided]
        self.status.setText(
            "Все позиции получили состояние — можно сохранять."
            if complete
            else "Ждут решения: " + ", ".join(iso(name) for name in undecided)
        )

    def _coordinates(self) -> list[tuple[float | None, float | None]]:
        with session_scope(self._engine) as session:
            return [
                (position.x, position.y)
                for position in sorted(
                    session.get(CharacteristicGroup, self._cg_id).positions,
                    key=lambda p: p.g_index,
                )
            ]

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
            self.status.setText("Сначала выберите позицию.")
            return
        self._sync_row(g_index)
        state = self._state_of(g_index)

        number, accepted = QInputDialog.getText(
            self,
            f"Позиция g{g_index}",
            "Номер размера детали (с чертежа):",
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
            show_error(self, error, title="Не привязано")
            return
        self.reload()

    def mark_absent(self) -> None:
        g_index = self._current_index()
        if g_index is None:
            self.status.setText("Сначала выберите позицию.")
            return
        state = self._state_of(g_index)
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                mark_absent(session, item, position)
        except Exception as error:
            show_error(self, error, title="Не отмечено")
            return
        self.reload()

    def clear_position(self) -> None:
        g_index = self._current_index()
        if g_index is None:
            self.status.setText("Сначала выберите позицию.")
            return
        state = self._state_of(g_index)
        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                clear(session, item, position)
        except Exception as error:
            show_error(self, error, title="Не очищено")
            return
        self.reload()

    def _sync_row(self, g_index: int) -> None:
        for row, state in enumerate(self._states):
            if state.g_index == g_index:
                self.table.setCurrentCell(row, 0)
                return
