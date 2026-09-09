"""Редактор группы характеристик: чертёж во всю ширину, позиции — таблицей.

Правки копятся в форме и уходят в базу одной транзакцией по «Сохранить»
(наряд 0003). Исключение — удаление позиции: занятость проверяется сразу при
нажатии, чтобы оператор узнал о блокировке на месте, а не после сохранения.

**Баллонов здесь больше нет** (наряд 0014, находки №7 и №8 прогона QMS-016).
Чертёж приходит из конструкторского отдела уже размеченным — метки `G1…GN`
стоят на выносках, — поэтому расставлять их заново поверх картинки значило бы
делать работу дважды и в самом уязвимом месте: на этой привязке держится весь
перекрёстный поиск. Чертёж показывается как есть и крупно, канонические позиции
ведутся таблицей, координаты `x`/`y` не пишутся вовсе.
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
    QWidget,
)
from sqlalchemy import Engine

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
from .cg_dialog import parse_optional_number
from .common import iso, position_label
from .drawing_view import BROKEN_IMAGE, DrawingPane
from .kit import tokens

#: Подписи по ISO 286 (решение 2026-09-02) — те же, что в форме создания.
COLUMNS = ("g-position", "Nominal", "Upper deviation", "Lower deviation")

#: Индекс позиции — идентификатор, влево; вправо только величины.
NUMERIC_COLUMNS = (0,)
MAGNITUDE_COLUMNS = (1, 2, 3)

HINT = (
    "Positions — nominal and the limit deviations come from the drawing and may "
    "stay empty (a form tolerance has no nominal). Each deviation carries its "
    "own sign: an interference fit has both of them positive. The index of an "
    "existing position never changes, and a new one is issued as max + 1."
)


@dataclass
class _Row:
    """Строка правки: `position_id=None` — позиция ещё не в базе.

    Геометрия здесь — **сырой текст ячейки**, а не число (наряд 0016). Оператор
    жмёт «Add position» посреди набора, когда в ячейке стоит `0.` или `−`, и это
    не ошибка ввода, а середина слова. Разбор в число живёт там же, где и жил, —
    в `_collect()` на «Сохранить», где ошибку ввода и надо называть.
    """

    g_index: int
    nominal: str = ""
    tol_plus: str = ""
    tol_minus: str = ""
    position_id: int | None = None


@dataclass
class _Spec:
    """Строка, разобранная в числа — то, что уходит в домен на «Сохранить».

    Отдельный тип от `_Row`, а не то же имя с двумя смыслами: в форме поле
    `nominal` это текст `0.`, в домене — `None` или число, и путать их дороже,
    чем объявить второй тип.
    """

    g_index: int
    nominal: float | None
    tol_plus: float | None
    tol_minus: float | None
    position_id: int | None


class CgEditor(QDialog):
    """Редактор группы. Возвращает `True` из `exec()`, если что-то сохранено."""

    def __init__(
        self, engine: Engine, cg_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._cg_id = cg_id
        self._rows: list[_Row] = []
        self._drawing: bytes | None = None
        self._drawing_name: str | None = None
        self._drawing_changed = False
        self.setWindowTitle("Characteristic group editor")
        # Выше прежнего: чертёж стал главным элементом экрана и получил свою
        # вертикаль, а таблица позиций под ним осталась при своей.
        self.resize(tokens.DIALOG_FULL, tokens.DIALOG_HEIGHT_TALL)
        # Разворот на весь экран — по той же причине, что и в привязке (§3.4).
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        self.name_edit = QLineEdit()

        self.drawing = DrawingPane(editable=True)
        self.drawing.loadRequested.connect(self.load_drawing)
        self.drawing.removeRequested.connect(self.drop_drawing)

        self.table = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
            read_only=False,
        )

        add_row = kit.secondary("Add position")
        drop_row = kit.secondary("Remove position")
        add_row.clicked.connect(self.add_position)
        drop_row.clicked.connect(self.remove_position)

        self.status = kit.status_label()

        self.buttons = kit.dialog_buttons()
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        form = kit.stretching_form()
        form.addRow("Group name:", self.name_edit)

        positions = kit.boxed(
            kit.column(kit.hint(HINT), self.table, kit.button_row(add_row, drop_row))
        )

        # Разделитель вертикальный, а не горизонтальный: чертёж занимает ширину
        # окна целиком (решение 2026-09-02), а делить с ним ширину значило бы
        # вернуть ту самую картинку в углу, из-за которой выноску приходилось
        # разглядывать.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.drawing)
        splitter.addWidget(positions)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([tokens.DIALOG_HEIGHT_MEDIUM, tokens.DIALOG_HEIGHT_SHORT])

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.reload()

    # --- загрузка / отрисовка --------------------------------------------------

    def reload(self) -> None:
        """Перечитать группу из базы — **единственное** место, которое затирает
        набранное намеренно: это возврат к записанному, а не побочный эффект
        перерисовки (наряд 0016)."""
        with session_scope(self._engine) as session:
            group = session.get(CharacteristicGroup, self._cg_id)
            self.name_edit.setText(group.name)
            self._drawing = group.drawing
            self._drawing_name = group.drawing_name
            self._rows = [
                _Row(
                    g_index=position.g_index,
                    nominal=_text(position.nominal),
                    tol_plus=_text(position.tol_plus),
                    tol_minus=_text(position.tol_minus),
                    position_id=position.g_position_id,
                )
                for position in sorted(group.positions, key=lambda p: p.g_index)
            ]
        self._drawing_changed = False
        self._refresh()

    def _refresh(self) -> None:
        """Перерисовать таблицу из `self._rows`.

        Зовущий обязан **сперва** забрать набранное (`_take_typed`), иначе
        перерисовка вернёт в ячейки то, что было до правки. Ровно этим и был
        дефект №9: перерисовка верна сама по себе, но стоит на пути самого
        частого действия оператора.
        """
        readable = self.drawing.set_drawing(self._drawing)

        with kit.filling(self.table):
            self.table.setRowCount(len(self._rows))
            for index, row in enumerate(self._rows):
                self.table.setItem(index, 0, _index_cell(row))
                self.table.setItem(index, 1, QTableWidgetItem(row.nominal))
                self.table.setItem(index, 2, QTableWidgetItem(row.tol_plus))
                self.table.setItem(index, 3, QTableWidgetItem(row.tol_minus))

        self.status.setText(
            BROKEN_IMAGE if not readable else f"Positions: {len(self._rows)}"
        )

    def _take_typed(self) -> None:
        """Забрать набранное из ячеек в `self._rows` — перед любой перерисовкой.

        Текст **как есть**: ни разбора, ни проверок. Недобранное значение — не
        ошибка, а середина набора, и падать на нём посреди «Add position»
        значило бы наказывать за порядок действий.

        Индекс и `position_id` не трогаются: индекс выдаёт форма, в ячейке он
        только читается (ратификация В-8), а `position_id` в таблице не живёт
        вовсе. Правило «правки копятся до Save» этим не нарушается: в базу
        по-прежнему не уходит ничего — набранное лишь переезжает из ячейки в
        строку формы.
        """
        for index, row in enumerate(self._rows):
            if index >= self.table.rowCount():
                break
            row.nominal = self._cell(index, 1)
            row.tol_plus = self._cell(index, 2)
            row.tol_minus = self._cell(index, 3)

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item else ""

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

        # Набранное забираем до перерисовки: смена чертежа к значениям позиций
        # отношения не имеет и стирать их не вправе.
        self._take_typed()
        self._drawing, self._drawing_name = data, path.rsplit("/", 1)[-1]
        self._drawing_changed = True
        self._refresh()

    def drop_drawing(self) -> None:
        self._take_typed()
        self._drawing, self._drawing_name = None, None
        self._drawing_changed = True
        self._refresh()

    def add_position(self) -> None:
        self._take_typed()
        next_index = max((row.g_index for row in self._rows), default=0) + 1
        self._rows.append(_Row(g_index=next_index))
        self._refresh()

    def remove_position(self) -> None:
        current = self.table.currentRow()
        if not 0 <= current < len(self._rows):
            self.status.setText("Select a position in the table first.")
            return

        # До снятия строки: иначе набранное в **остальных** строках вернулось бы
        # к прочитанному из базы вместе с перерисовкой.
        self._take_typed()
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

    def _collect(self) -> list[_Spec]:
        """Разобрать набранное в числа — на «Сохранить», и только здесь.

        До этого момента форма носит сырой текст (`_Row`), поэтому недобранное
        значение живёт в ней сколько угодно; ошибка ввода называется тогда,
        когда оператор сказал «записываю», а не когда он добавил строку.

        Индекс из таблицы не читается вовсе (ратификация В-8): у существующей
        позиции он неизменен, у новой выдан формой как `max + 1`. Ячейка закрыта
        в обоих случаях, и взять оттуда можно было бы только то же значение.
        """
        self._take_typed()
        specs = [
            _Spec(
                g_index=row.g_index,
                nominal=parse_optional_number(row.nominal, f"Row {index + 1}, nominal"),
                tol_plus=parse_optional_number(
                    row.tol_plus, f"Row {index + 1}, upper deviation"
                ),
                tol_minus=parse_optional_number(
                    row.tol_minus, f"Row {index + 1}, lower deviation"
                ),
                position_id=row.position_id,
            )
            for index, row in enumerate(self._rows)
        ]
        indexes = [spec.g_index for spec in specs]
        if len(set(indexes)) != len(indexes):
            raise ValidationError("The g-position indexes inside a group must not repeat.")
        return specs

    def save(self) -> None:
        try:
            specs = self._collect()
            with session_scope(self._engine) as session:
                group = session.get(CharacteristicGroup, self._cg_id)
                update_group(session, group, name=self.name_edit.text())

                if self._drawing_changed:
                    set_drawing(session, group, self._drawing, self._drawing_name)

                kept = {spec.position_id for spec in specs if spec.position_id is not None}
                for position in list(group.positions):
                    if position.g_position_id not in kept:
                        remove_position(session, position)

                for spec in specs:
                    if spec.position_id is None:
                        add_position(
                            session,
                            group,
                            GPositionSpec(
                                spec.g_index, spec.nominal, spec.tol_plus, spec.tol_minus
                            ),
                        )
                    else:
                        position = session.get(GPosition, spec.position_id)
                        update_position(
                            session,
                            position,
                            nominal=spec.nominal,
                            tol_plus=spec.tol_plus,
                            tol_minus=spec.tol_minus,
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
    # Ярлык один на всё приложение — `g13` (Р-3 долга к шву).
    cell = QTableWidgetItem(position_label(row.g_index))
    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    cell.setToolTip(
        "The g-position index is issued as max + 1 and never changes: "
        "characteristic mappings and the drawing point at it."
    )
    return cell


def _text(value: float | None) -> str:
    """Число для ячейки: в изоляте и с минусом канона (Р-4 долга к шву).

    Редактор показывал `-0.05` дефисом, а привязка и карточка — `−0.05`
    (U+2212): одно и то же значение двумя знаками на соседних экранах. Ввод от
    этого не страдает — `parse_optional_number` принимает оба.
    """
    return "" if value is None else iso(f"{value:g}".replace("-", "−"))


def _in_use(g_index: int, used: int) -> Exception:
    from domain.errors import ValueInUse

    return ValueInUse(
        f"Position g{g_index} is used by {used} records "
        "(characteristic mappings or “absent from item” marks) — clear them first."
    )
