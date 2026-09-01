"""Форма «Добавить деталь»: классификаторы + привязка к CG с сидом размеров.

`connection_type` и `size` предвыбраны как `General` — деталь заводится и когда
специфика ещё не важна (`Item.md`). При выборе группы её g-позиции показываются
таблицей: номер размера оператор проставляет сам на каждую позицию — он берётся
с чертежа детали и с индексом g-позиции совпадает редко (решение Cowork по
заметке Б наряда 0002), поэтому автоподстановки нет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine, select

from db.models import (
    GENERAL,
    CharacteristicGroup,
    Item,
    RefConnectionType,
    RefItemType,
    RefSize,
)
from db.session import session_scope
from domain.groups import list_groups
from domain.items import create_item, seed_cg_characteristics, update_item
from domain.reference import list_values

from . import kit
from .cg_dialog import CgDialog
from .common import bind_direction, tolerance_label
from .kit import tokens

NO_GROUP = "— no group —"
NO_TYPE = "— not set —"
COLUMNS = ("g-position", "Local number", "Nominal", "Tolerance")

#: Индекс позиции и номер размера — идентификаторы, влево; вправо величины.
NUMERIC_COLUMNS = (0, 1)
MAGNITUDE_COLUMNS = (2, 3)


class ItemDialog(QDialog):
    """Форма детали: заведение и правка. После accept() номер — в `created_number`.

    **Правка появилась потому, что номер был неисправим** (ревью наряда 0012,
    В-2): форма умела только создавать, и опечатка в реальном каталожном номере
    лечилась перезаливкой базы — то есть останавливала прогон на шаге 5.

    В правке засев размеров не показывается. Он относится к заведению детали:
    размеры уже есть, их локальные номера правятся привязкой к канону, а второй
    засев по той же группе домен и не позволит (номер размера уникален внутри
    детали). Показывать таблицу, которая при сохранении ничего не делает, —
    обещать несуществующее.
    """

    def __init__(
        self,
        engine: Engine,
        item_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self.created_number: str | None = None
        self.setWindowTitle("New item" if item_id is None else "Edit item")
        self.resize(tokens.DIALOG_MEDIUM, tokens.DIALOG_HEIGHT_MEDIUM)

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText('e.g. C1-08375A (מק"ט)')
        bind_direction(self.number_edit)

        self.item_type = _combo()
        self.connection_type = _combo()
        self.size = _combo()
        self.group = _combo()
        self.group.currentIndexChanged.connect(self.reload_positions)

        new_group = kit.secondary("Create group…")
        new_group.clicked.connect(self.create_group)

        group_row = QHBoxLayout()
        group_row.setSpacing(tokens.GAP_CONTROL)
        group_row.addWidget(self.group, 1)
        group_row.addWidget(new_group)

        self.positions = kit.data_table(
            COLUMNS,
            numeric_columns=NUMERIC_COLUMNS,
            magnitude_columns=MAGNITUDE_COLUMNS,
            read_only=False,
        )

        self.buttons = kit.dialog_buttons(
            accept="Create item" if item_id is None else "Save item"
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        self.seed_hint = kit.hint(
            "Group positions — set the local number from the item drawing for "
            "each. The number is not prefilled: it comes from the drawing and "
            "rarely equals the g-position index."
        )
        self.group_row = kit.boxed(group_row)

        form = kit.stretching_form()
        form.addRow("Item number:", self.number_edit)
        form.addRow("Item type:", self.item_type)
        form.addRow("Connection type:", self.connection_type)
        form.addRow("Size class:", self.size)
        self.group_label = "Characteristic group:"
        form.addRow(self.group_label, self.group_row)

        layout = kit.dialog_layout(self)
        layout.addLayout(form)
        layout.addWidget(self.seed_hint)
        layout.addWidget(self.positions, 1)
        layout.addWidget(
            kit.hint(
                "Dimensions of an existing item are not seeded twice: their local "
                "numbers are edited in Mapping, the geometry — in the group editor."
            )
            if item_id is not None
            else kit.hint("")
        )
        layout.addWidget(self.buttons)

        self.reload_reference()
        if item_id is not None:
            self._load(item_id)

    @classmethod
    def run(
        cls, engine: Engine, item_id: int | None = None, parent: QWidget | None = None
    ) -> bool:
        """Открыть форму; `True` — деталь заведена или правка сохранена."""
        return cls(engine, item_id, parent).exec() == QDialog.DialogCode.Accepted

    # --- наполнение ------------------------------------------------------------

    def _load(self, item_id: int) -> None:
        """Прочитать деталь в форму и убрать засев: он относится к заведению."""
        with session_scope(self._engine) as session:
            item = session.get(Item, item_id)
            self.number_edit.setText(item.item_number)
            _select_text(self.item_type, item.item_type.name if item.item_type else NO_TYPE)
            _select_text(self.connection_type, item.connection_type.name)
            _select_text(self.size, item.size.name)

        self.group_row.setVisible(False)
        self.seed_hint.setVisible(False)
        self.positions.setVisible(False)
        form = self.layout().itemAt(0).layout()
        for row in range(form.rowCount()):
            label = form.itemAt(row, form.ItemRole.LabelRole)
            if label is not None and label.widget() is not None:
                if label.widget().text().startswith("Characteristic group"):
                    label.widget().setVisible(False)

    def reload_reference(self, keep_group: str | None = None) -> None:
        """Перечитать справочники и список групп."""
        with session_scope(self._engine) as session:
            item_types = [value.name for value in list_values(session, RefItemType)]
            connections = [value.name for value in list_values(session, RefConnectionType)]
            sizes = [value.name for value in list_values(session, RefSize)]
            groups = [group.name for group in list_groups(session)]

        _fill(self.item_type, [NO_TYPE, *item_types], NO_TYPE)
        _fill(self.connection_type, connections, GENERAL)
        _fill(self.size, sizes, GENERAL)
        _fill(self.group, [NO_GROUP, *groups], keep_group or NO_GROUP)
        self.reload_positions()

    def reload_positions(self) -> None:
        """Показать g-позиции выбранной группы с предзаполненными номерами."""
        self.positions.setRowCount(0)
        name = self.group.currentText()
        if name == NO_GROUP:
            return

        with session_scope(self._engine) as session:
            group = session.scalar(
                select(CharacteristicGroup).where(CharacteristicGroup.name == name)
            )
            rows = [
                (
                    position.g_index,
                    _format_number(position.nominal),
                    tolerance_label(position.tol_plus, position.tol_minus),
                )
                for position in sorted(group.positions, key=lambda p: p.g_index)
            ]

        self.positions.setRowCount(len(rows))
        for row, (g_index, nominal, tolerance) in enumerate(rows):
            self.positions.setItem(row, 0, _readonly(f"g{g_index}", g_index))
            # номер размера не подставляется: он с чертежа детали и с g_index
            # совпадает редко (решение Cowork по заметке Б наряда 0002)
            self.positions.setItem(row, 1, QTableWidgetItem(""))
            self.positions.setItem(row, 2, _readonly(nominal))
            self.positions.setItem(row, 3, _readonly(tolerance))

    def local_numbers(self) -> dict[int, str]:
        numbers: dict[int, str] = {}
        for row in range(self.positions.rowCount()):
            g_index = self.positions.item(row, 0).data(Qt.ItemDataRole.UserRole)
            cell = self.positions.item(row, 1)
            numbers[g_index] = cell.text() if cell else ""
        return numbers

    # --- действия --------------------------------------------------------------

    def create_group(self) -> None:
        """R3 — недостающую группу можно завести прямо отсюда."""
        dialog = CgDialog(self._engine, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_name:
            self.reload_reference(keep_group=dialog.created_name)

    def save(self) -> None:
        item_type_name = self.item_type.currentText()
        group_name = self.group.currentText()
        try:
            with session_scope(self._engine) as session:
                fields = dict(
                    item_number=self.number_edit.text(),
                    item_type=(
                        None
                        if item_type_name == NO_TYPE
                        else _by_name(session, RefItemType, item_type_name)
                    ),
                    connection_type=_by_name(
                        session, RefConnectionType, self.connection_type.currentText()
                    ),
                    size=_by_name(session, RefSize, self.size.currentText()),
                )
                if self._item_id is None:
                    item = create_item(session, **fields)
                    if group_name != NO_GROUP:
                        group = session.scalar(
                            select(CharacteristicGroup).where(
                                CharacteristicGroup.name == group_name
                            )
                        )
                        seed_cg_characteristics(session, item, group, self.local_numbers())
                else:
                    item = update_item(session, session.get(Item, self._item_id), **fields)
                self.created_number = item.item_number
        except Exception as error:
            kit.show_error(self, error)
            return
        self.accept()


# --- мелкие помощники ------------------------------------------------------------


def _combo():
    from PySide6.QtWidgets import QComboBox

    return QComboBox()


def _fill(combo, names: list[str], preselect: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(names)
    index = combo.findText(preselect)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def _select_text(combo, text: str) -> None:
    """Отметить значение по подписи; нет такого — оставить как есть."""
    index = combo.findText(text)
    if index >= 0:
        combo.setCurrentIndex(index)


def _readonly(text: str, payload=None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if payload is not None:
        item.setData(Qt.ItemDataRole.UserRole, payload)
    return item


def _format_number(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _by_name(session, model: type, name: str):
    return session.scalar(select(model).where(model.name == name))
