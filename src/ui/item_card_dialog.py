"""Карточка детали — что известно о детали и по каким чертежам (QMS-017, наряд 0025).

**Зачем отдельный экран.** До неё двойной щелчок по строке `Items` открывал привязку:
жест «посмотреть, что это за деталь» выполнял операцию правки канона. Карточка занимает
это место и делает то, чего от жеста и ждут — показывает.

Симметрия с карточкой отклонения намеренная: там тоже шапка только читает, а правка
уходит в отдельную форму по кнопке. Двух образцов показа записи в одном приложении быть
не должно.

**Просмотр и назначение — разные органы управления** (решение 15). Выпадающий список
ревизий переключает только то, что показано, и в базу не пишет ничего. Сделать ревизию
действующей можно единственным способом — кнопкой, и она закрыта подтверждением: смена
действующей редка, последствие у неё отложенное (против неё пойдут будущие отклонения),
и случаться от промаха мышью она не должна.

**Чего здесь нет.** Таблицы привязок — она живёт в своём диалоге, и дублировать её
значит завести второе место, где привязку правят. Фильтров в списке отклонений — они
часть фильтровой машинерии (часть 2 `Q-14`, после S6).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)
from sqlalchemy import Engine

from db.models import Item
from db.session import session_scope
from domain.items import groups_of
from domain.revisions import current_revision, list_revisions, set_current

from . import kit
from .common import iso, joined
from .kit import tokens

#: Подпись действующей ревизии в списке — та же, что в форме отклонения.
CURRENT_SUFFIX = " (current)"

DIMENSION_COLUMNS = ("Local number", "Canon", "State")
DIMENSION_NUMERIC_COLUMNS = (0,)

STATE_BOUND = "linked"
STATE_UNBOUND = "not bound"

#: Ширины поимённо (§7 наряда 0020). Без объявления таблица садится по содержимому
#: и повисает узкой полосой посреди диалога — видно только на снимке.
#: `Canon` шире прочих: там `Implant_Con_375_C1_g13 · g13`, а не одно `g13`, —
#: и это жёсткий формат, а не свободный текст (наряд `0034` §2).
DIMENSION_WIDTHS = (
    kit.fixed("10375-12"),
    kit.fixed("Implant_Con_375_C1_g13 · g13"),
    kit.closed((STATE_BOUND, STATE_UNBOUND)),
)


EMPTY_TITLE = "This revision has no characteristics yet"
EMPTY_BODY = (
    "Characteristics appear with the mapping dialog, or on their own, when a "
    "finding names a number that does not exist yet."
)

SET_CURRENT_TITLE = "Make this revision current?"
SET_CURRENT_BODY = (
    "New deviations on {item} will be registered against revision {revision} "
    "from now on. Deviations already recorded keep the revision they carry."
)


class ItemCardDialog(QDialog):
    """Карточка детали: классификаторы, лента ревизий, размеры выбранной ревизии."""

    def __init__(
        self, engine: Engine, item_id: int, *, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._item_id = item_id
        self.resize(tokens.DIALOG_MEDIUM, tokens.DIALOG_HEIGHT_MEDIUM)

        # --- шапка: только чтение, правка уходит в форму ---
        # Значения шапки — простые надписи, как в карточке отклонения: там же
        # ратифицировано, что шапка читает, а правка уходит в форму.
        self.number_label = QLabel()
        self.type_label = QLabel()
        self.connection_label = QLabel()
        self.size_label = QLabel()
        self.groups_label = QLabel()

        self.edit_button = kit.secondary("Edit…")
        self.edit_button.clicked.connect(self.edit_item)

        # --- ревизии: список смотрит, кнопка назначает ---
        self.revision = QComboBox()
        self.revision.currentIndexChanged.connect(self._revision_shown_changed)
        self.set_current_button = kit.secondary("Set as current")
        self.set_current_button.clicked.connect(self.set_as_current)
        self.mapping_button = kit.secondary("Mapping…")
        self.mapping_button.clicked.connect(self.open_mapping)
        self.deviations_button = kit.secondary("Deviations…")
        self.deviations_button.clicked.connect(self.open_deviations)

        revision_row = QHBoxLayout()
        revision_row.setSpacing(tokens.GAP_CONTROL)
        revision_row.addWidget(self.revision, 1)
        revision_row.addWidget(self.set_current_button)
        revision_row.addWidget(self.mapping_button)

        header = kit.stretching_form()
        header.addRow("Item number:", self.number_label)
        header.addRow("Item type:", self.type_label)
        header.addRow("Connection type:", self.connection_label)
        header.addRow("Size class:", self.size_label)
        header.addRow("Groups:", self.groups_label)
        header.addRow("Revision:", kit.boxed(revision_row))

        self.table = kit.data_table(
            DIMENSION_COLUMNS,
            numeric_columns=DIMENSION_NUMERIC_COLUMNS,
            widths=DIMENSION_WIDTHS,
        )
        # Правка в строке заперта самим `kit.data_table` (§7): по умолчанию
        # таблица данных нередактируема, отказываются от этого только диалоги,
        # существующие ради ввода.
        self.empty = kit.empty_state(EMPTY_TITLE, EMPTY_BODY)
        self.status = kit.status_label()

        self.buttons = kit.dialog_buttons(accept="Close", reject="Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(self.buttons.StandardButton.Cancel).setVisible(False)

        layout = kit.dialog_layout(self)
        layout.addLayout(header)
        layout.addLayout(kit.button_row(self.edit_button, self.deviations_button))
        layout.addWidget(
            kit.hint(
                "The revision list only changes what is shown. Making a revision "
                "current is a separate, confirmed action."
            )
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.reload()

    @classmethod
    def run(cls, engine: Engine, item_id: int, parent: QWidget | None = None) -> None:
        cls(engine, item_id, parent=parent).exec()

    # --- наполнение ------------------------------------------------------------

    def shown_revision_id(self) -> int | None:
        """Ревизия, которую сейчас показывают. Это **не** обязательно действующая."""
        return self.revision.currentData()

    def reload(self, *, keep_shown: int | None = None) -> None:
        """Перечитать деталь целиком, сохранив показанную ревизию.

        `keep_shown` держит выбор оператора: перезагрузка после правки детали или
        после привязки не имеет права молча вернуть показ на действующую — он
        смотрел не её.
        """
        if keep_shown is None:
            keep_shown = self.shown_revision_id()

        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            self.setWindowTitle(f"Item — {item.item_number}")
            self.number_label.setText(iso(item.item_number))
            self.type_label.setText(iso(item.item_type.name if item.item_type else "—"))
            self.connection_label.setText(iso(item.connection_type.name))
            self.size_label.setText(iso(item.size.name))
            self.groups_label.setText(
                joined(*(group.name for group in groups_of(item)), sep=", ") or "—"
            )

            rows = [
                (
                    revision.revision_id,
                    revision.designation
                    + (CURRENT_SUFFIX if revision.is_current else ""),
                )
                for revision in list_revisions(item)
            ]
            current = current_revision(item)
            current_id = current.revision_id if current else None

        with kit.filling(self.revision):
            self.revision.clear()
            for revision_id, label in rows:
                self.revision.addItem(label, revision_id)
            index = self.revision.findData(keep_shown)
            if index < 0:
                index = self.revision.findData(current_id)
            self.revision.setCurrentIndex(max(index, 0))

        self._reload_dimensions()

    def _reload_dimensions(self) -> None:
        """Показать размеры выбранной ревизии.

        Меняется только то, чем ревизия владеет. `Item type`, `Connection type` и
        `Size class` принадлежат детали и при переключении показа не трогаются —
        иначе список ревизий выглядел бы фильтром по другой детали.
        """
        from domain.precedents import canon_labels  # noqa: PLC0415

        revision_id = self.shown_revision_id()
        rows: list[tuple[str, str, str]] = []
        is_current = False
        designation = ""
        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            revision = next(
                (r for r in item.revisions if r.revision_id == revision_id), None
            )
            if revision is not None:
                designation = revision.designation
                is_current = revision.is_current
                characteristics = sorted(
                    revision.characteristics, key=lambda c: c.local_number
                )
                labels = canon_labels(session, characteristics)
                rows = [
                    (
                        iso(characteristic.local_number),
                        iso(labels.get(characteristic.characteristic_id, "—")),
                        STATE_BOUND
                        if characteristic.mapping is not None
                        else STATE_UNBOUND,
                    )
                    for characteristic in characteristics
                ]

        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        # Кнопка молчит о том, что и так видно: действующую назначать незачем.
        self.set_current_button.setEnabled(bool(designation) and not is_current)
        bound = sum(1 for row in rows if row[2] == STATE_BOUND)
        self.status.setText(
            f"Revision {designation}: {len(rows)} characteristics, {bound} bound to "
            "the canon." if designation else "This item has no revisions."
        )

    def _revision_shown_changed(self) -> None:
        """Переключение показа. **В базу не пишет ничего** (решение 15)."""
        self._reload_dimensions()

    # --- действия --------------------------------------------------------------

    def edit_item(self) -> None:
        """Правка — той же формой, что и с экрана деталей: одна форма, одно место."""
        from .item_dialog import ItemDialog  # noqa: PLC0415

        if ItemDialog.run(self._engine, self._item_id, parent=self):
            self.reload()

    def set_as_current(self) -> None:
        """Сделать показанную ревизию действующей — через подтверждение.

        Подтверждение здесь не формальность: действие редкое, а последствие
        отложенное — оно проявится на следующей регистрации отклонения, когда
        оператор уже забудет, что нажал. Отказ по умолчанию: кнопка `No` — та,
        на которой стоит фокус.
        """
        revision_id = self.shown_revision_id()
        if revision_id is None:
            return

        with session_scope(self._engine) as session:
            item = session.get(Item, self._item_id)
            revision = next(
                (r for r in item.revisions if r.revision_id == revision_id), None
            )
            if revision is None or revision.is_current:
                return
            item_number, designation = item.item_number, revision.designation

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(SET_CURRENT_TITLE)
        box.setText(SET_CURRENT_TITLE)
        box.setInformativeText(
            SET_CURRENT_BODY.format(item=item_number, revision=designation)
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # Отказ по умолчанию: промах по Enter не должен менять действующую ревизию.
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        try:
            with session_scope(self._engine) as session:
                item = session.get(Item, self._item_id)
                target = next(
                    r for r in item.revisions if r.revision_id == revision_id
                )
                set_current(session, target)
        except Exception as error:
            kit.show_error(self, error, title="Revision not changed")
            return
        self.reload(keep_shown=revision_id)

    def open_mapping(self) -> None:
        """Привязка — для **показанной** ревизии, а не для действующей."""
        from .item_dialog import open_mapping  # noqa: PLC0415
        from .pickers import choose_cg_for_item  # noqa: PLC0415

        cg_id = choose_cg_for_item(self, self._engine, self._item_id)
        if cg_id is None:
            return
        open_mapping(self._engine, self, self._item_id, cg_id)
        self.reload()

    def open_deviations(self) -> None:
        """Все отклонения этой детали — по всем ревизиям, без фильтров."""
        from .item_deviations_dialog import ItemDeviationsDialog  # noqa: PLC0415

        ItemDeviationsDialog.run(self._engine, self._item_id, parent=self)
