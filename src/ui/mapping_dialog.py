"""Диалог привязки размеров детали к g-позициям — переиспользуемый.

Строка таблицы = одна g-позиция канона; оператор вписывает **прямо в строку**
локальный номер размера детали либо отмечает «нет у детали (99)». Баллонов на
чертеже приложение не расставляет (наряд 0014): чертёж приходит из
конструкторского отдела уже размеченным, показывается здесь как есть и служит
тем, по чему оператор сверяет индекс `g5` с выноской.

Каждое действие уходит в базу сразу — случайно закрытое окно не теряет уже
введённое. Поэтому кнопки называются «Done» / «Close», а не «Save» / «Cancel»:
откатывать сеанс привязки нечем. «Done» активна только когда **каждая** позиция
получила состояние.

Точка вызова из другого кода — `MappingDialog.run(engine, item_id, cg_id, parent)`;
на неё S4 повесил «ранние кнопки» формы ввода отклонения (R2: канон-привязка
делается до регистрации отклонения). Сигнатура не менялась и меняться не должна.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QDialog,
    QDialogButtonBox,
    QSplitter,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.models import CharacteristicGroup, GPosition, Item
from db.session import session_scope
from domain.revisions import current_revision
from domain.mappings import bind, binding_state, clear, is_complete, mark_absent

from . import kit
from .common import canon_geometry_label, iso, position_label, strip_iso
from .drawing_view import DrawingPane
from .kit import tokens

COLUMNS = ("Position", "State", "Local number", "Canon geometry")

#: Подписи колонки `State` — закрытый набор, из него же берётся её ширина.
STATE_LABELS = {
    "linked": "linked",
    "absent": "absent (99)",
    "none": "undecided",
}

#: Колонка, которую оператор правит прямо в строке. Остальные — чтение:
#: индекс это идентичность позиции, состояние и геометрия — производные.
LOCAL_NUMBER = COLUMNS.index("Local number")

#: Индекс позиции, номер размера и геометрия — направление объявлено, потому что
#: сильных символов в них нет (канон §6).
#:
#: Выравнивание у всех трёх **левое**, включая геометрию. Канон §6 отправляет
#: вправо `Nominal` и предельные отклонения — там, где они стоят **отдельными**
#: колонками и сравниваются по величине вниз по столбцу. Здесь одна ячейка:
#: сравнивают в ней номинал, а он у левого края токена — правый край держал бы в
#: столбик хвост допуска, то есть не то, на что смотрят.
NUMERIC_COLUMNS = (0, 2, 3)

#: Классы содержимого объявлены явно (§3.1 наряда 0020): угадать по подписи
#: «Canon geometry» нельзя — это не свободный текст, а компактная составная
#: ячейка `3.75 +0.05 / −0.05`.
#: Ширины поимённо (§7.3 наряда 0020): max(заголовок, самое длинное реальное
#: значение) × 1.25; знакоместо — по самому широкому знаку шрифта канона.
#: `Position` и `Local number` — номера размеров, жёсткий формат.
#: `State` — закрытый набор подписей привязки.
#: `Canon geometry` — составная ячейка `3.75 +0.05 / −0.05`, тоже жёсткий формат
#: (свободным текстом она не является: длина у неё своя и постоянная).
WIDTHS = (
    kit.fixed("g13"),
    kit.closed(STATE_LABELS.values()),
    kit.fixed("10375-12"),
    kit.fixed("3.75 +0.05 / −0.05"),
)

#: Класс остаётся умолчанием, если ширина почему-то не объявлена.
CONTENT = ("identifier", "state", "identifier", "state")


HINT = (
    "Type the item's local dimension number straight into the row — the "
    "g-index matches the callout on the drawing above. A position the item "
    "does not have is marked absent (99). Every action is written at once; "
    "Done only confirms that no position was left undecided."
)


class MappingDialog(QDialog):
    """Привязка детали к канону. Пишет в базу сразу по действию оператора."""

    def __init__(
        self, engine: Engine, item_id: int, cg_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self._cg_id = cg_id
        self._states: list = []
        #: Пока True, правка ячеек идёт от кода, а не от оператора: `reload`
        #: переписывает всю таблицу, и без флага каждая её ячейка выглядела бы
        #: как ввод и уходила бы в базу.
        # Чертёж занял верх окна и требует высоты; таблица под ним осталась при
        # своей ширине — с колонкой геометрии (В-6) уже узкой она не бывает.
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_TALL)
        # Чертёж — рабочая поверхность, а не иллюстрация: окно обязано
        # разворачиваться на весь экран (находка №16). Диалогу на Windows
        # кнопку разворота дают явно.
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        self.drawing = DrawingPane()

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            content=CONTENT,
            widths=WIDTHS,
            read_only=False,
        )
        self.table.itemChanged.connect(self._on_edit)
        #: Геометрия позиции по её индексу — заполняется вместе с состояниями.
        self._geometry: dict[int, tuple] = {}

        self.absent_button = kit.secondary("Absent from item (99)")
        self.clear_button = kit.secondary("Clear")
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
        # «Done» **проверяет**, а не заблокирована (§3.3 наряда 0020): она
        # доступна всегда, а полноту спрашивает нажатие.
        self.buttons.accepted.connect(self.finish)
        self.buttons.rejected.connect(self.reject)

        side = kit.boxed(
            kit.column(
                kit.hint(HINT),
                self.table,
                kit.button_row(self.absent_button, self.clear_button),
                self.status,
            )
        )

        # Вертикально, как в редакторе группы: чертёж — то, по чему оператор
        # узнаёт позицию, и делить с таблицей ширину ему нечем.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.drawing)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([tokens.DIALOG_HEIGHT_MEDIUM, tokens.DIALOG_HEIGHT_SHORT])

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
        dialog = cls(engine, item_id, cg_id, parent=parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

    # --- отрисовка -------------------------------------------------------------

    def reload(self) -> None:
        """Пересобрать таблицу целиком — на открытии и по нажатию кнопки.

        **Из обработчика `itemChanged` не зовётся** (наряд `0039`): пересборка
        внутри эмиссии сносит тот самый `QTableWidgetItem`, который Qt передал в
        слот аргументом, и оставляет открытый редактор указывающим в никуда.
        Обработчик обновляет строки на месте — `_refresh_rows`.
        """
        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            group = session.get(CharacteristicGroup, self._cg_id)
            self.setWindowTitle(f"Mapping — {item.item_number} · {group.name}")
            drawing = group.drawing
            self._read_states(session, item, group)

        self.drawing.set_drawing(drawing)

        with kit.filling(self.table):
            self.table.setRowCount(len(self._states))
            for row, state in enumerate(self._states):
                self.table.setItem(row, 0, _read_only(position_label(state.g_index)))
                self.table.setItem(row, 1, _read_only(STATE_LABELS[state.state]))
                self.table.setItem(row, 2, QTableWidgetItem(state.local_number or ""))
                self.table.setItem(row, 3, _read_only(self._canon_cell(state.g_index)))

        self._show_status()

    def _read_states(self, session, item, group) -> None:
        """Состояния позиций и геометрия канона — одним обходом коллекции.

        Привязка ведётся в **действующей** ревизии детали (QMS-017). Разрешение
        здесь, а не в подписи диалога: оба входа — заведение детали и
        «Add revision» — оставляют действующей ровно ту ревизию, которую оператор
        сейчас правит, а прошлые не редактируются вовсе.
        """
        self._states = binding_state(session, current_revision(item), group)
        # Геометрию берём из той же коллекции, которую уже обошёл
        # `binding_state`: новых запросов не нужно.
        self._geometry = {
            position.g_index: (
                position.nominal,
                position.tol_plus,
                position.tol_minus,
            )
            for position in group.positions
        }

    def _show_status(self) -> None:
        """Строка состояния: всё решено либо чего именно не хватает."""
        undecided = [f"g{s.g_index}" for s in self._states if not s.is_decided]
        complete = is_complete(self._states)
        self.status.setText(
            "Every position has a state — the mapping can be finished."
            if complete
            else "Awaiting a decision: " + ", ".join(iso(name) for name in undecided)
        )

    def _refresh_rows(self) -> None:
        """Обновить строки **на месте**, не пересобирая таблицу.

        Ячейки правятся `setText`, а не `setItem`: `setItem` **уничтожает**
        прежний `QTableWidgetItem`, и когда обновление идёт из обработчика
        `itemChanged`, уничтожается ровно тот объект, который Qt передал в слот и
        чей метод ещё на стеке. Ниже границы Python ↔ C++ это тот же класс
        дефекта, что стоп-дефект раскрытия наряда `0028`.

        Число строк здесь не меняется по построению: привязка не заводит и не
        убирает g-позиции группы. Обход идёт по фактическому пересечению — если
        инвариант когда-нибудь нарушится, строки просто не разъедутся, а
        пересборку закажет `reload` из своего, безопасного места.
        """
        with kit.filling(self.table):
            for row, state in enumerate(self._states[: self.table.rowCount()]):
                self.table.item(row, 1).setText(STATE_LABELS[state.state])
                self.table.item(row, 2).setText(state.local_number or "")

    def finish(self) -> None:
        """Нажали «Done»: досчитать набранное, проверить полноту, назвать пробел.

        Прежде полнота была закодирована в **доступности** кнопки, и оператор,
        набравший номер в последнюю позицию, тянулся к мёртвой кнопке: набранное
        лежало в открытом редакторе ячейки и в состояние ещё не ушло (находка
        №15). Теперь порядок обратный — сперва закрываем редактор, потом
        спрашиваем.

        Смысл конвенции S3 сохраняется: подтвердить, что ни одна позиция не
        забыта. Меняется способ — с запрета на проверку (ратифицировано Cowork).
        Тем же движением снимается Р-2/0018: у пустой группы кнопка была мертва
        навсегда.
        """
        self._commit_open_editor()
        undecided = [state for state in self._states if not state.is_decided]
        if not undecided:
            self.accept()
            return

        names = ", ".join(iso(f"g{state.g_index}") for state in undecided)
        self.status.setText(f"Not finished — no state for {names}.")

    def _commit_open_editor(self) -> None:
        """Закрыть открытый редактор ячейки, чтобы набранное ушло в состояние.

        Тот самый шаг, которого не хватало: без него последнее набранное
        значение существует только в редакторе и в полноту не попадает.
        """
        editor = self.table.viewport().focusWidget()
        if editor is None:
            return
        self.table.commitData(editor)
        self.table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def _canon_cell(self, g_index: int) -> str:
        """Номинал и допуск позиции — то, **по чему** оператор решает (В-6).

        Привязка — момент, когда он сопоставляет индекс на чертеже с локальным
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
        return None

    def _state_of(self, g_index: int):
        return next(state for state in self._states if state.g_index == g_index)

    def _on_edit(self, item: QTableWidgetItem) -> None:
        """Номер размера, вписанный в строку, — это и есть действие привязки.

        Пустая ячейка привязку **не снимает**: у снятия есть своя кнопка, а
        стереть готовую привязку случайным `Backspace` по выделенной строке —
        потеря данных, которую оператор заметит не сразу. Строка возвращается к
        тому, что записано в базе.
        """
        if item.column() != LOCAL_NUMBER:
            return

        state = self._states[item.row()]
        number = strip_iso(item.text()).strip()
        if not number:
            # Возвращаем строку к тому, что записано в базе, — на месте, без
            # пересборки: мы внутри эмиссии `itemChanged` этой самой ячейки.
            self._refresh_rows()
            return

        try:
            with session_scope(self._engine) as session:
                session_item = session.get(Item, self._item_id)
                position = session.get(GPosition, state.g_position_id)
                if state.state == "linked" and state.local_number != number:
                    # Правка номера на привязанной строке — это **перепривязка**,
                    # а не ошибка (Р-1 долга к шву). Прежде она отбивалась
                    # доменным «позиция уже занята», и оператор должен был
                    # сперва нажать «Clear»: два действия там, где он делает
                    # одно. Снимаем прежнюю связь и ставим новую в одной
                    # транзакции — инвариант «один индекс = один размер» цел.
                    clear(session, current_revision(session_item), position)
                bind(session, current_revision(session_item), position, number)
        except Exception as error:
            kit.show_error(self, error, title="Not bound")

        # **Строки обновляются на месте, таблица не пересобирается** (наряд
        # `0039`). Прежде здесь стоял `reload()`, то есть обработчик сигнала
        # сносил и собирал заново свой же виджет, **находясь внутри эмиссии**:
        # `setRowCount` и `setItem` уничтожали объект, переданный в слот, а
        # `_commit_open_editor` следом закрывал редактор, которого в модели уже
        # не было. Достижимый путь шёл через кнопку `Done`, которую оператор
        # нажимает каждый раз.
        #
        # Чертёж группы заодно перестал декодироваться на каждый введённый
        # номер: его перечитывает только `reload`.
        with session_scope(self._engine) as session:
            self._read_states(
                session,
                session.get(Item, self._item_id),
                session.get(CharacteristicGroup, self._cg_id),
            )
        self._refresh_rows()
        self._show_status()

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
                mark_absent(session, current_revision(item), position)
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
                clear(session, current_revision(item), position)
        except Exception as error:
            kit.show_error(self, error, title="Not cleared")
            return
        self.reload()


def _read_only(text: str) -> QTableWidgetItem:
    """Ячейка, которую правит не оператор: индекс, состояние, геометрия канона.

    Таблица открыта на правку целиком — иначе номер размера не вписать в
    строку, — поэтому закрывать приходится **остальные** ячейки поимённо.
    """
    cell = QTableWidgetItem(text)
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return cell
